"""采购工具接口。

查看入口需要 purchase:view；导入价格（写操作）另外需要 material:price——
价格数据本身归物料成本域管，与物料卡片价格区同一档权限（用户 2026-09-27 定）。
预览也是 POST（上传文件），所以同样按写操作要求 material:price。
"""
from flask import Blueprint, g, request

from auth import make_blueprint_guard
from error_handling import internal_error_response
from result import Result
from services.purchase.price_import import purchase_price_import_service
from upload_validation import UploadValidationError, read_spreadsheet_upload


purchase_bp = Blueprint('purchase', __name__)
purchase_bp.before_request(make_blueprint_guard('purchase:view', 'material:price'))


def _read_file():
    file = request.files.get('file')
    if not file:
        raise UploadValidationError('请选择采购 BOM 文件')
    if not (file.filename or '').lower().endswith('.xlsx'):
        raise UploadValidationError('仅支持 .xlsx 文件')
    return read_spreadsheet_upload(file, label='采购 BOM')


@purchase_bp.post('/price-import/preview')
def preview_price_import():
    try:
        data = _read_file()
        return purchase_price_import_service.preview(
            data, request.form.get('price_date'),
        ).to_response()
    except UploadValidationError as exc:
        return Result.fail(str(exc)).to_response(413 if '不能超过' in str(exc) else 400)
    except Exception:
        return internal_error_response('采购价格导入预览失败', '文件解析失败')


@purchase_bp.post('/price-import')
def run_price_import():
    try:
        data = _read_file()
        return purchase_price_import_service.import_prices(
            data, request.form.get('price_date'), (g.current_user or {}).get('username'),
        ).to_response()
    except UploadValidationError as exc:
        return Result.fail(str(exc)).to_response(413 if '不能超过' in str(exc) else 400)
    except Exception:
        return internal_error_response('采购价格导入失败', '导入失败')


@purchase_bp.get('/price-import/history')
def price_import_history():
    return purchase_price_import_service.history().to_response()
