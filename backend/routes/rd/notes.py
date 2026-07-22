"""研发个人笔记 HTTP 接口。"""

from flask import g, request

from result import Result
from services.rd.notes import rd_note_service

from . import rd_bp


def _current_username() -> str:
    return g.current_user.get('username', '')


@rd_bp.get('/notes')
def list_notes():
    """返回当前用户的笔记列表（按创建时间倒序）。"""
    return Result.ok(rd_note_service.list_notes(_current_username())).to_response()


@rd_bp.post('/notes')
def create_note():
    """新建一条笔记。"""
    try:
        note = rd_note_service.create_note(
            _current_username(), request.get_json(silent=True) or {},
        )
    except ValueError as exc:
        return Result.fail(str(exc)).to_response()
    return Result.ok(note).to_response()


@rd_bp.put('/notes/<int:nid>')
def update_note(nid):
    """编辑笔记内容（只能改自己的）。"""
    try:
        note = rd_note_service.update_note(
            nid, _current_username(), request.get_json(silent=True) or {},
        )
    except ValueError as exc:
        return Result.fail(str(exc)).to_response()
    if note is None:
        return Result.fail('笔记不存在或无权限').to_response()
    return Result.ok(note).to_response()


@rd_bp.delete('/notes/<int:nid>')
def delete_note(nid):
    """删除一条笔记（只能删自己的）。"""
    if not rd_note_service.delete_note(nid, _current_username()):
        return Result.fail('笔记不存在或无权限').to_response()
    return Result.ok(None).to_response()
