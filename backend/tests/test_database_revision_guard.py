from types import SimpleNamespace

import pytest

import app as app_module


class _ConnectionContext:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, exc_type, exc_value, traceback):
        return False


def _database():
    connection = object()
    engine = SimpleNamespace(connect=lambda: _ConnectionContext(connection))
    return SimpleNamespace(engine=engine), connection


def _mock_revisions(monkeypatch, *, expected, current):
    monkeypatch.setattr(
        app_module.ScriptDirectory,
        'from_config',
        lambda _config: SimpleNamespace(get_heads=lambda: tuple(expected)),
    )
    monkeypatch.setattr(
        app_module.MigrationContext,
        'configure',
        lambda _connection: SimpleNamespace(get_current_heads=lambda: tuple(current)),
    )


def test_revision_guard_accepts_database_at_the_only_head(tmp_path, monkeypatch):
    config_path = tmp_path / 'alembic.ini'
    config_path.write_text('[alembic]\nscript_location = migrations\n', encoding='utf-8')
    monkeypatch.setenv('ALEMBIC_CONFIG', str(config_path))
    _mock_revisions(
        monkeypatch,
        expected={'20260720_01'},
        current={'20260720_01'},
    )
    database, _connection = _database()

    app_module._validate_database_revision(database)


@pytest.mark.parametrize('current', [set(), {'older_revision'}])
def test_revision_guard_rejects_unstamped_or_outdated_database(tmp_path, monkeypatch, current):
    config_path = tmp_path / 'alembic.ini'
    config_path.write_text('[alembic]\nscript_location = migrations\n', encoding='utf-8')
    monkeypatch.setenv('ALEMBIC_CONFIG', str(config_path))
    _mock_revisions(
        monkeypatch,
        expected={'20260720_01'},
        current=current,
    )
    database, _connection = _database()

    with pytest.raises(RuntimeError, match='数据库迁移版本不匹配'):
        app_module._validate_database_revision(database)


def test_revision_guard_rejects_missing_config(tmp_path, monkeypatch):
    monkeypatch.setenv('ALEMBIC_CONFIG', str(tmp_path / 'missing.ini'))
    database, _connection = _database()

    with pytest.raises(RuntimeError, match='Alembic 配置不存在'):
        app_module._validate_database_revision(database)


def test_revision_guard_rejects_multiple_heads(tmp_path, monkeypatch):
    config_path = tmp_path / 'alembic.ini'
    config_path.write_text('[alembic]\nscript_location = migrations\n', encoding='utf-8')
    monkeypatch.setenv('ALEMBIC_CONFIG', str(config_path))
    _mock_revisions(
        monkeypatch,
        expected={'head_a', 'head_b'},
        current={'head_a'},
    )
    database, _connection = _database()

    with pytest.raises(RuntimeError, match='只能有一个 head'):
        app_module._validate_database_revision(database)


def test_application_fails_fast_when_database_revision_is_invalid(monkeypatch):
    monkeypatch.setattr(app_module, 'validate_security_config', lambda: None)
    monkeypatch.setattr(app_module.db, 'init_app', lambda _app: None)
    monkeypatch.setattr(
        app_module,
        '_validate_database_revision',
        lambda _database: (_ for _ in ()).throw(RuntimeError('revision mismatch')),
    )

    with pytest.raises(RuntimeError, match='revision mismatch'):
        app_module.create_app()


def test_application_startup_contains_no_implicit_schema_mutation():
    source = (app_module.Path(app_module.__file__)).read_text(encoding='utf-8')

    assert '_run_migrations' not in source
    assert 'ALTER TABLE' not in source
    assert '.create(bind=' not in source
