from flask import Blueprint, request, g
from services.product.import_raw import import_product_service
from auth import make_blueprint_guard
from result import Result
import openpyxl
import io
from upload_validation import (
    read_spreadsheet_upload, ensure_spreadsheet_row_limit, UploadValidationError,
)
from error_handling import internal_error_response

product_bp = Blueprint('product', __name__)
product_bp.before_request(make_blueprint_guard('product:view', 'product:edit'))

_HEADER_ALIASES = {
    'code':       {'品号', '物料编码', '编码'},
    'name':       {'品名', '物料名称', '名称'},
    'spec':       {'规格', '规格型号'},
    'group_code': {'分组编码', '物料分组编码', '分组代码'},
    'group_name': {'分组名称', '物料分组名称'},
}
_REQUIRED_HEADERS = {'code', 'name', 'group_code', 'group_name'}


def _header_map(header_row):
    normalized = {
        str(value).strip().replace('\n', '').replace(' ', ''): index
        for index, value in enumerate(header_row)
        if value is not None and str(value).strip()
    }
    result = {}
    for field, aliases in _HEADER_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                result[field] = normalized[alias]
                break
    missing = sorted(_REQUIRED_HEADERS - result.keys())
    if missing:
        labels = {'code': '品号', 'name': '品名', 'group_code': '分组编码', 'group_name': '分组名称'}
        raise UploadValidationError('Excel 缺少必需表头：' + '、'.join(labels[x] for x in missing))
    return result


def _parse_excel(file_bytes: bytes) -> list:
    """解析 Excel，返回原始行数据列表"""
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    ws = wb.active
    iterator = ws.iter_rows(values_only=True)
    header = next(iterator, None)
    if not header:
        wb.close()
        raise UploadValidationError('Excel 没有表头')
    columns = _header_map(header)
    rows = []
    for i, row in enumerate(iterator, start=1):
        ensure_spreadsheet_row_limit(i)
        def value(field):
            index = columns.get(field)
            return row[index] if index is not None and index < len(row) else None
        rows.append({
            'code': value('code'), 'name': value('name'), 'spec': value('spec'),
            'group_code': value('group_code'), 'group_name': value('group_name'),
        })
    wb.close()
    return rows


@product_bp.post("/import/preview")
def preview():
    """预览：解析 Excel，返回行数和前 5 行样本，不写库"""
    file = request.files.get('file')
    if not file:
        return Result.fail('未收到文件').to_response()
    try:
        raw_rows = _parse_excel(read_spreadsheet_upload(file, label='产品 Excel'))
    except UploadValidationError as e:
        return Result.fail(str(e)).to_response(413 if '不能超过' in str(e) else 400)
    except Exception:
        return internal_error_response('产品导入预览解析失败', '文件解析失败')
    return Result.ok(data={
        'total':  len(raw_rows),
        'sample': raw_rows[:5],
    }).to_response()


@product_bp.post("/import")
def import_data():
    """正式导入：解析 Excel → 写入 import_product_raw"""
    file = request.files.get('file')
    if not file:
        return Result.fail('未收到文件').to_response()
    try:
        raw_rows = _parse_excel(read_spreadsheet_upload(file, label='产品 Excel'))
        result   = import_product_service.import_rows(raw_rows)
    except UploadValidationError as e:
        return Result.fail(str(e)).to_response(413 if '不能超过' in str(e) else 400)
    except Exception:
        return internal_error_response('产品数据导入失败', '导入失败')
    return Result.ok(data=result).to_response()


@product_bp.get("/stats")
def get_stats():
    """获取导入数据统计（供概览页使用）"""
    return Result.ok(data=import_product_service.get_stats()).to_response()
