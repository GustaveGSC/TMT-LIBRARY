from flask import Blueprint, request
from services.product.finished import finished_service
from result import Result

finished_bp = Blueprint('finished', __name__)


# ── 成品列表 ──────────────────────────────────────────────────────────────
@finished_bp.get('/finished')
def list_finished():
    page         = int(request.args.get('page',         1))
    size         = int(request.args.get('size',         20))
    search_field = request.args.get('search_field', '').strip()
    search_value = request.args.get('search_value', '').strip()
    status       = request.args.get('status',       '').strip()
    return finished_service.get_finished_list(
        page, size, search_field, search_value, status
    ).to_response()


# ── 保存成品信息（新增或更新）────────────────────────────────────────────
@finished_bp.post('/finished')
def save_finished():
    body = request.get_json() or {}
    code = (body.pop('code', '') or '').strip()
    if not code:
        return Result.fail('code 不能为空').to_response()
    return finished_service.save_finished(code, **body).to_response()


# ── 产成品候选（不分页，用于下拉选项）───────────────────────────────────
@finished_bp.get('/packaged/candidates/all')
def list_packaged_candidates_all():
    return finished_service.get_all_packaged_candidate_codes().to_response()


# ── 全量产成品（供前端预加载）────────────────────────────────────────────
@finished_bp.get('/packaged/all')
def list_packaged_all():
    return finished_service.get_all_packaged().to_response()


# ── 产成品候选列表 ────────────────────────────────────────────────────────
@finished_bp.get('/packaged/candidates')
def list_packaged_candidates():
    search = request.args.get('search', '').strip()
    page   = int(request.args.get('page', 1))
    size   = int(request.args.get('size', 20))
    return finished_service.get_packaged_candidates(search, page, size).to_response()


# ── 保存产成品信息 ────────────────────────────────────────────────────────
@finished_bp.post('/packaged')
def save_packaged():
    body = request.get_json() or {}
    code = (body.pop('code', '') or '').strip()
    name = (body.pop('name', '') or '').strip()
    if not code or not name:
        return Result.fail('code 和 name 不能为空').to_response()
    return finished_service.save_packaged(code, name, **body).to_response()


# ── 某成品关联的产成品列表 ────────────────────────────────────────────────
@finished_bp.get('/finished/<int:finished_id>/packaged')
def get_packaged_by_finished(finished_id: int):
    return finished_service.get_packaged_by_finished(finished_id).to_response()


# ── 添加关联 ──────────────────────────────────────────────────────────────
@finished_bp.post('/finished/<int:finished_id>/packaged/<int:packaged_id>')
def add_packaged_relation(finished_id: int, packaged_id: int):
    return finished_service.add_packaged_relation(finished_id, packaged_id).to_response()


# ── 移除关联 ──────────────────────────────────────────────────────────────
@finished_bp.delete('/finished/<int:finished_id>/packaged/<int:packaged_id>')
def remove_packaged_relation(finished_id: int, packaged_id: int):
    return finished_service.remove_packaged_relation(finished_id, packaged_id).to_response()