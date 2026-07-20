from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory


ROOT = Path(__file__).resolve().parents[2]
BASELINE_REVISION = '20260720_01'
CRITICAL_INDEXES = {
    'shipping_order_finished': {
        'ix_sof_source',
        'ix_sof_source_date',
        'ix_sof_source_finished_code',
        'ix_sof_finished_code_date',
    },
    'user_login_log': {
        'ix_login_log_user_id',
        'ix_login_log_login_at',
    },
}


def _config(database_url: str) -> Config:
    config = Config(str(ROOT / 'alembic.ini'))
    config.set_main_option('sqlalchemy.url', database_url)
    return config


def test_baseline_is_the_only_head_and_has_no_parent():
    scripts = ScriptDirectory.from_config(_config('sqlite://'))

    assert scripts.get_heads() == [BASELINE_REVISION]
    assert scripts.get_revision(BASELINE_REVISION).down_revision is None


def test_performance_critical_production_indexes_are_declared_in_metadata():
    from database.base import db
    import database.models.account  # noqa: F401
    import database.models.shipping  # noqa: F401

    for table_name, expected_indexes in CRITICAL_INDEXES.items():
        actual_indexes = {index.name for index in db.metadata.tables[table_name].indexes}
        assert expected_indexes <= actual_indexes


def test_removed_aftersale_dictionary_tables_are_explicitly_unmanaged():
    # env.py 由 Alembic 运行时加载，直接检查清单可避免测试导入触发迁移上下文。
    env_source = (ROOT / 'backend' / 'migrations' / 'env.py').read_text(encoding='utf-8')

    for table_name in (
        'aftersale_reason_component_term',
        'aftersale_reason_fault_term',
        'aftersale_reason_synonym_rule',
    ):
        assert table_name in env_source


def test_known_production_schema_details_are_reflected_in_metadata():
    from sqlalchemy.dialects.mysql import DOUBLE

    from database.base import db
    import database.models.aftersale  # noqa: F401
    import database.models.product.category  # noqa: F401
    import database.models.product.finished  # noqa: F401

    candidate = db.metadata.tables['aftersale_keyword_candidate']
    assert 'idx_reason_id' in {index.name for index in candidate.indexes}

    remark_dict = db.metadata.tables['aftersale_product_remark_dict']
    assert remark_dict.c.value.type.length == 50
    assert remark_dict.c.display.type.length == 50

    packaged = db.metadata.tables['product_packaged']
    assert all(isinstance(packaged.c[name].type, DOUBLE) for name in (
        'volume', 'gross_weight', 'net_weight',
    ))

    product_tag = db.metadata.tables['product_tag']
    assert product_tag.c.color.nullable is False
    assert {fk.constraint.name for fk in product_tag.c.category_id.foreign_keys} == {'fk_tag_category'}

    product_model = db.metadata.tables['product_model']
    model_code_unique_constraints = {
        tuple(column.name for column in constraint.columns)
        for constraint in product_model.constraints
        if isinstance(constraint, sa.UniqueConstraint)
    }
    assert ('model_code',) not in model_code_unique_constraints


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
