import os
from collections.abc import Mapping


DEFAULT_JWT_SECRET = 'tmt-dev-secret-change-in-production'
DEFAULT_SHARE_SECRET = 'tmt-share-key-2024'
_NON_PRODUCTION_ENVS = {'dev', 'development', 'local', 'test', 'testing'}


def validate_security_config(environ: Mapping[str, str] | None = None) -> None:
    """拒绝以缺失或公开默认密钥启动生产环境。"""
    values = os.environ if environ is None else environ
    app_env = values.get('APP_ENV', 'production').strip().lower()
    if app_env in _NON_PRODUCTION_ENVS:
        return

    invalid = []
    if values.get('JWT_SECRET', '') in ('', DEFAULT_JWT_SECRET):
        invalid.append('JWT_SECRET')
    if values.get('SHARE_SECRET', '') in ('', DEFAULT_SHARE_SECRET):
        invalid.append('SHARE_SECRET')
    if invalid:
        names = ', '.join(invalid)
        raise RuntimeError(f'生产环境安全配置无效：请设置非默认强密钥 {names}')
