import pytest

from app import create_app
from security_config import (
    DEFAULT_JWT_SECRET,
    DEFAULT_SHARE_SECRET,
    validate_security_config,
)


@pytest.mark.parametrize(
    'environ',
    [
        {},
        {'APP_ENV': 'production'},
        {
            'APP_ENV': 'production',
            'JWT_SECRET': DEFAULT_JWT_SECRET,
            'SHARE_SECRET': 'strong-share-secret',
        },
        {
            'APP_ENV': 'production',
            'JWT_SECRET': 'strong-jwt-secret',
            'SHARE_SECRET': DEFAULT_SHARE_SECRET,
        },
    ],
)
def test_production_rejects_missing_or_default_secrets(environ):
    with pytest.raises(RuntimeError):
        validate_security_config(environ)


def test_production_accepts_explicit_strong_secrets():
    validate_security_config({
        'APP_ENV': 'production',
        'JWT_SECRET': 'strong-jwt-secret',
        'SHARE_SECRET': 'strong-share-secret',
    })


def test_application_fails_before_initialization_without_production_secrets(monkeypatch):
    monkeypatch.setenv('APP_ENV', 'production')
    monkeypatch.delenv('JWT_SECRET', raising=False)
    monkeypatch.delenv('SHARE_SECRET', raising=False)

    with pytest.raises(RuntimeError, match='JWT_SECRET, SHARE_SECRET'):
        create_app()


@pytest.mark.parametrize('app_env', ['development', 'dev', 'local', 'test', 'testing'])
def test_non_production_environments_allow_local_defaults(app_env):
    validate_security_config({'APP_ENV': app_env})
