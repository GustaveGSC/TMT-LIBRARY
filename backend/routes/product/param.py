from flask import Blueprint, request
from services.product.param import ParamService

param_bp = Blueprint('param', __name__)


# ── 键名管理 ──────────────────────────────────────────────────────────────

@param_bp.get('/keys')
def list_keys():
    return ParamService.get_all_keys().to_response()


@param_bp.post('/keys')
def create_key():
    data = request.get_json() or {}
    return ParamService.create_key(
        name=data.get('name', ''),
        group_name=data.get('group_name', ''),
        sort_order=int(data.get('sort_order', 0)),
    ).to_response()


@param_bp.put('/keys/<int:key_id>')
def update_key(key_id):
    data = request.get_json() or {}
    return ParamService.update_key(
        key_id=key_id,
        name=data.get('name'),
        group_name=data.get('group_name'),
        sort_order=data.get('sort_order'),
    ).to_response()


@param_bp.delete('/keys/<int:key_id>')
def delete_key(key_id):
    return ParamService.delete_key(key_id).to_response()


# ── 成品参数值 ────────────────────────────────────────────────────────────

@param_bp.get('/finished/<int:finished_id>')
def get_finished_params(finished_id):
    return ParamService.get_params_for_finished(finished_id).to_response()


@param_bp.post('/finished/<int:finished_id>')
def save_finished_params(finished_id):
    groups = request.get_json() or {}
    return ParamService.save_params_for_finished(finished_id, groups).to_response()
