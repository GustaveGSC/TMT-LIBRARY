from routes.account import _registration_enabled


def test_registration_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv('ALLOW_REGISTER', raising=False)
    assert _registration_enabled() is False


def test_registration_requires_explicit_enable(monkeypatch):
    monkeypatch.setenv('ALLOW_REGISTER', 'true')
    assert _registration_enabled() is True

    monkeypatch.setenv('ALLOW_REGISTER', 'false')
    assert _registration_enabled() is False
