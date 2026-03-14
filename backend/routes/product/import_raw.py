from flask import Blueprint, request
from services.product.import_raw import import_product_service
from result import Result
import openpyxl
import io

product_bp = Blueprint('product', __name__)

# Excel 固定列索引（0-based）
_COL_CODE       = 0
_COL_NAME       = 1
_COL_SPEC       = 2
_COL_GROUP_CODE = 7
_COL_GROUP_NAME = 8


def _parse_excel(file_bytes: bytes) -> list:
    """解析 Excel，返回原始行数据列表"""
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    ws = wb.active
    rows = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            continue  # 跳过表头
        rows.append({
            'code':       row[_COL_CODE],
            'name':       row[_COL_NAME],
            'spec':       row[_COL_SPEC],
            'group_code': row[_COL_GROUP_CODE],
            'group_name': row[_COL_GROUP_NAME],
        })
    wb.close()
    return rows


@product_bp.post("/import/preview")
def preview():
    """预览：解析 Excel，返回行数和前 5 行样本，不写库"""
    file = request.files.get('file')
    if not file:
        return Result.fail('未收到文件').to_response()
    if not file.filename.endswith(('.xlsx', '.xls')):
        return Result.fail('请上传 Excel 文件（.xlsx / .xls）').to_response()
    try:
        raw_rows = _parse_excel(file.read())
    except Exception as e:
        return Result.fail(f'文件解析失败：{str(e)}').to_response()
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
    if not file.filename.endswith(('.xlsx', '.xls')):
        return Result.fail('请上传 Excel 文件（.xlsx / .xls）').to_response()
    try:
        raw_rows = _parse_excel(file.read())
        result   = import_product_service.import_rows(raw_rows)
    except Exception as e:
        return Result.fail(f'导入失败：{str(e)}').to_response()
    return Result.ok(data=result).to_response()


@product_bp.get("/stats")
def get_stats():
    """获取导入数据统计（供概览页使用）"""
    return Result.ok(data=import_product_service.get_stats()).to_response()
