"""
站点配置接口 — 目前管理登录页轮播语句（login_mottos）。
数据存储于 site_config 表（key-value），自动建表。
"""
import json
from flask import Blueprint, request, g
from auth import require_auth
from result import Result
from database.base import db
from database.models.account import SiteConfig

config_bp = Blueprint('config', __name__)

_MOTTOS_KEY = 'login_mottos'

_DEFAULT_MOTTOS = [
    '享受每一天的好心情',
    '保持你的好奇心',
    '今天也要元气满满',
    '把每件小事做到位',
    '细节决定品质',
    '记录，让知识留存',
]


def _read_mottos() -> list[str]:
    row = SiteConfig.query.get(_MOTTOS_KEY)
    if row:
        try:
            data = json.loads(row.value)
            if isinstance(data, list) and data:
                return data
        except Exception:
            pass
    return list(_DEFAULT_MOTTOS)


@config_bp.get('/login-mottos')
def get_login_mottos():
    """公开接口：获取登录页轮播语句列表。"""
    return Result.ok(_read_mottos()).to_response()


@config_bp.put('/login-mottos')
@require_auth
def update_login_mottos():
    """需登录（author/admin）：更新登录页轮播语句列表。"""
    user = g.current_user
    if 'admin' not in user.get('roles', []) and user.get('username') != 'author':
        return Result.fail('无权限').to_response(403)
    body   = request.get_json() or {}
    mottos = body.get('mottos', [])
    if not isinstance(mottos, list):
        return Result.fail('格式错误，mottos 须为数组').to_response()
    mottos = [str(m).strip() for m in mottos if str(m).strip()]
    if not mottos:
        return Result.fail('语句列表不能为空').to_response()
    row = SiteConfig.query.get(_MOTTOS_KEY)
    if row:
        row.value = json.dumps(mottos, ensure_ascii=False)
    else:
        db.session.add(SiteConfig(key=_MOTTOS_KEY, value=json.dumps(mottos, ensure_ascii=False)))
    db.session.commit()
    return Result.ok(mottos, message='保存成功').to_response()
