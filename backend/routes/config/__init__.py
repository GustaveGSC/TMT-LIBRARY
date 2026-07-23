"""站点配置 HTTP 接口。"""

from flask import Blueprint, request, g

from auth import has_permission, require_auth
from result import Result
from services.config import config_service


config_bp = Blueprint('config', __name__)


@config_bp.get('/login-mottos')
def get_login_mottos():
    """公开接口：获取登录页轮播语句列表。"""
    return Result.ok(config_service.get_login_mottos()).to_response()


@config_bp.put('/login-mottos')
@require_auth
def update_login_mottos():
    """需 ops:login-config:edit：更新登录页轮播语句列表。"""
    user = g.current_user
    if not has_permission(user, 'ops:login-config:edit'):
        return Result.fail('无权限').to_response(403)
    try:
        mottos = config_service.update_login_mottos(request.get_json(silent=True) or {})
    except ValueError as exc:
        return Result.fail(str(exc)).to_response()
    return Result.ok(mottos, message='保存成功').to_response()
