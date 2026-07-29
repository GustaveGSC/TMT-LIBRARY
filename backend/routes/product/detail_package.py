from flask import Blueprint, request

from auth import make_blueprint_guard
from result import Result
from services.product.detail_package import detail_package_service


detail_package_bp = Blueprint('detail_package', __name__)
detail_package_bp.before_request(make_blueprint_guard('product:view', 'product:edit'))


@detail_package_bp.get('')
def list_packages():
    try:
        page = max(1, int(request.args.get('page', 1)))
        size = max(1, min(100, int(request.args.get('size', 50))))
    except ValueError:
        return Result.fail('page 和 size 必须为整数').to_response()
    return detail_package_service.list(request.args.get('search', '').strip() or None, page, size).to_response()


@detail_package_bp.post('')
def create_package():
    return detail_package_service.create((request.get_json() or {}).get('name')).to_response()


@detail_package_bp.get('/<int:package_id>')
def get_package(package_id):
    return detail_package_service.get_one(package_id).to_response()


@detail_package_bp.put('/<int:package_id>')
def update_package(package_id):
    return detail_package_service.update(package_id, (request.get_json() or {}).get('name')).to_response()


@detail_package_bp.delete('/<int:package_id>')
def delete_package(package_id):
    return detail_package_service.delete(package_id).to_response()


@detail_package_bp.put('/<int:package_id>/tags')
def set_tags(package_id):
    body = request.get_json() or {}
    return detail_package_service.set_tags(package_id, body.get('tag_ids', []), body.get('tag_condition')).to_response()


@detail_package_bp.put('/<int:package_id>/models')
def set_models(package_id):
    return detail_package_service.set_models(package_id, (request.get_json() or {}).get('model_ids', [])).to_response()


@detail_package_bp.put('/<int:package_id>/series')
def set_series(package_id):
    return detail_package_service.set_series(package_id, (request.get_json() or {}).get('series_ids', [])).to_response()


@detail_package_bp.put('/<int:package_id>/categories')
def set_categories(package_id):
    return detail_package_service.set_categories(package_id, (request.get_json() or {}).get('category_ids', [])).to_response()


@detail_package_bp.post('/<int:package_id>/media/presign')
def presign_media(package_id):
    return detail_package_service.presign_media(package_id, (request.get_json() or {}).get('files')).to_response()


@detail_package_bp.post('/<int:package_id>/media/confirm')
def confirm_media(package_id):
    return detail_package_service.confirm_media(package_id, (request.get_json() or {}).get('files')).to_response()


@detail_package_bp.delete('/<int:package_id>/media/<int:media_id>')
def delete_media(package_id, media_id):
    return detail_package_service.delete_media(package_id, media_id).to_response()


@detail_package_bp.get('/finished/<string:code>')
def get_finished_packages(code):
    return detail_package_service.for_finished(code).to_response()
