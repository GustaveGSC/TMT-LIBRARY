from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory


ROOT = Path(__file__).resolve().parents[2]
BASELINE_REVISION = '20260720_01'


def _config(database_url: str) -> Config:
    config = Config(str(ROOT / 'alembic.ini'))
    config.set_main_option('sqlalchemy.url', database_url)
    return config


def test_baseline_is_the_only_head_and_has_no_parent():
    scripts = ScriptDirectory.from_config(_config('sqlite://'))

    assert scripts.get_heads() == [BASELINE_REVISION]
    assert scripts.get_revision(BASELINE_REVISION).down_revision is None


def test_stamp_then_upgrade_head_does_not_change_existing_schema(tmp_path, monkeypatch):
    database_path = tmp_path / 'existing.db'
    database_url = f'sqlite:///{database_path.as_posix()}'
    engine = sa.create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(sa.text('CREATE TABLE existing_business_data (id INTEGER PRIMARY KEY)'))

    monkeypatch.setenv('DATABASE_URL', database_url)
    config = _config(database_url)
    command.stamp(config, BASELINE_REVISION)

    before_upgrade = set(sa.inspect(engine).get_table_names())
    command.upgrade(config, 'head')
    after_upgrade = set(sa.inspect(engine).get_table_names())

    assert before_upgrade == {'alembic_version', 'existing_business_data'}
    assert after_upgrade == before_upgrade
    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
    assert current == BASELINE_REVISION
