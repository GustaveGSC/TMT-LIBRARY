"""研发变更提醒 HTTP 接口。"""

from flask import request

from auth import is_rd_admin, require_auth
from result import Result
from services.rd.reminders import rd_reminder_service

from . import rd_bp


def _permission_denied_response():
    return Result.fail('权限不足：需要研发部管理员权限').to_response()


@rd_bp.get('/reminders')
def list_reminders():
    """返回所有在架的变更提醒（所有 RD 用户可读）。"""
    return Result.ok(rd_reminder_service.list_active()).to_response()


@rd_bp.get('/reminders/all')
@require_auth
def list_reminders_all():
    """返回全部提醒（含下架历史），仅 rd:admin 可用。"""
    if not is_rd_admin():
        return _permission_denied_response()
    return Result.ok(rd_reminder_service.list_all()).to_response()


@rd_bp.post('/reminders')
@require_auth
def create_reminder():
    """新建变更提醒，仅 rd:admin 可用。"""
    if not is_rd_admin():
        return _permission_denied_response()
    try:
        reminder = rd_reminder_service.create(request.get_json() or {})
    except ValueError as exc:
        return Result.fail(str(exc)).to_response()
    return Result.ok(reminder).to_response()


@rd_bp.put('/reminders/<int:rid>')
@require_auth
def update_reminder(rid):
    """编辑提醒内容和备注，仅 rd:admin 可用。"""
    if not is_rd_admin():
        return _permission_denied_response()
    try:
        reminder = rd_reminder_service.update(rid, request.get_json() or {})
    except ValueError as exc:
        return Result.fail(str(exc)).to_response()
    if reminder is None:
        return Result.fail('提醒不存在').to_response()
    return Result.ok(reminder).to_response()


def _set_reminder_active(rid: int, is_active: bool):
    if not is_rd_admin():
        return _permission_denied_response()
    reminder = rd_reminder_service.set_active(rid, is_active)
    if reminder is None:
        return Result.fail('提醒不存在').to_response()
    return Result.ok(reminder).to_response()


@rd_bp.put('/reminders/<int:rid>/deactivate')
@require_auth
def deactivate_reminder(rid):
    """下架指定提醒，仅 rd:admin 可用。"""
    return _set_reminder_active(rid, False)


@rd_bp.put('/reminders/<int:rid>/activate')
@require_auth
def activate_reminder(rid):
    """重新上架指定提醒，仅 rd:admin 可用。"""
    return _set_reminder_active(rid, True)
