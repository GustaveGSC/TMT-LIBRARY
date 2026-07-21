import secrets

from flask import current_app

from result import Result


def report_internal_error(context: str) -> str:
    """记录当前异常的完整堆栈，返回可安全展示的短错误编号。"""
    error_id = secrets.token_hex(6)
    current_app.logger.exception('%s [error_id=%s]', context, error_id)
    return error_id


def internal_error_response(context: str, public_message: str = '服务器内部错误'):
    error_id = report_internal_error(context)
    return Result.fail(
        f'{public_message}（错误编号：{error_id}）',
        data={'error_id': error_id},
    ).to_response(500)


def internal_error_result(context: str, public_message: str = '服务器内部错误') -> Result:
    error_id = report_internal_error(context)
    return Result.fail(
        f'{public_message}（错误编号：{error_id}）',
        data={'error_id': error_id},
    )


def internal_task_error(context: str, public_message: str = '任务执行失败') -> str:
    error_id = report_internal_error(context)
    return f'{public_message}（错误编号：{error_id}）'
