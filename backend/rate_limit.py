from flask import current_app, make_response, request
from flask_limiter import Limiter
from limits import parse

from result import Result


LOGIN_ACCOUNT_LIMIT = "5 per 5 minutes"
LOGIN_IP_LIMIT = "20 per 5 minutes"
REGISTER_IP_LIMIT = "5 per hour"
LOGIN_ACCOUNT_SCOPE = "login-account"


def get_client_ip() -> str:
    """读取 nginx 覆盖写入的真实 IP；本地直连时回退到 remote_addr。"""
    return request.headers.get("X-Real-IP", "").strip() or request.remote_addr or "unknown"


def get_login_username() -> str:
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return "<missing>"
    username = body.get("username")
    return username.strip() if isinstance(username, str) and username.strip() else "<missing>"


def deduct_failed_login(response) -> bool:
    return response.status_code != 200


def rate_limit_response(_request_limit):
    return make_response(Result.fail("尝试次数过多，请稍后重试").to_response(429))


limiter = Limiter(
    key_func=get_client_ip,
    default_limits=[],
    storage_uri="memory://",
    on_breach=rate_limit_response,
)


def clear_login_account_failures(username: str) -> None:
    """成功登录后只清除当前账号的失败计数，不影响 IP 维度计数。"""
    normalized = username.strip() if isinstance(username, str) else ""
    if normalized and "limiter" in current_app.extensions:
        limiter.limiter.clear(
            parse(LOGIN_ACCOUNT_LIMIT),
            normalized,
            LOGIN_ACCOUNT_SCOPE,
        )
