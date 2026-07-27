from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.autogenerate.api import AutogenContext
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory


ROOT = Path(__file__).resolve().parents[2]
BASELINE_REVISION = '20260720_01'
TASK_REVISION = '20260720_02'
PERMISSION_REVISION = '20260721_01'
CUSTOMER_MAPPING_REVISION = '20260721_02'
ORDER_ALIAS_REVISION = '20260721_03'
MAPPING_STATUS_REVISION = '20260721_04'
GUEST_REMOVAL_REVISION = '20260723_01'
PERMISSION_DOMAIN_REVISION = '20260723_02'
SHIPPING_TASK_LEASE_REVISION = '20260724_01'
LIFECYCLE_TASK_REVISION = '20260724_02'
SHIPPING_CANCEL_REVISION = '20260724_03'
SHIPPING_RESOLVE_STAGING_REVISION = '20260725_01'
SHIPPING_GENERATION_REVISION = '20260726_01'
SHIPPING_SCOPED_STALE_INDEX_REVISION = '20260727_01'
AFTERSALE_CASE_MEDIA_REVISION = '20260727_02'
HEAD_REVISION = AFTERSALE_CASE_MEDIA_REVISION
CRITICAL_INDEXES = {
    'shipping_order_finished': {
        'ix_sof_source',
        'ix_sof_source_date',
        'ix_sof_source_finished_code',
        'ix_sof_source_customer_alias',
        'ix_sof_finished_code_date',
        'ix_sof_source_order',
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


def test_baseline_has_linear_history_and_task_lease_is_the_only_head():
    scripts = ScriptDirectory.from_config(_config('sqlite://'))

    assert scripts.get_heads() == [HEAD_REVISION]
    assert scripts.get_revision(BASELINE_REVISION).down_revision is None
    assert scripts.get_revision(TASK_REVISION).down_revision == BASELINE_REVISION
    assert scripts.get_revision(PERMISSION_REVISION).down_revision == TASK_REVISION
    assert scripts.get_revision(CUSTOMER_MAPPING_REVISION).down_revision == PERMISSION_REVISION
    assert scripts.get_revision(ORDER_ALIAS_REVISION).down_revision == CUSTOMER_MAPPING_REVISION
    assert scripts.get_revision(MAPPING_STATUS_REVISION).down_revision == ORDER_ALIAS_REVISION
    assert scripts.get_revision(GUEST_REMOVAL_REVISION).down_revision == MAPPING_STATUS_REVISION
    assert scripts.get_revision(PERMISSION_DOMAIN_REVISION).down_revision == GUEST_REMOVAL_REVISION
    assert (
        scripts.get_revision(SHIPPING_TASK_LEASE_REVISION).down_revision
        == PERMISSION_DOMAIN_REVISION
    )
    assert (
        scripts.get_revision(LIFECYCLE_TASK_REVISION).down_revision
        == SHIPPING_TASK_LEASE_REVISION
    )
    assert (
        scripts.get_revision(SHIPPING_CANCEL_REVISION).down_revision
        == LIFECYCLE_TASK_REVISION
    )
    assert (
        scripts.get_revision(SHIPPING_RESOLVE_STAGING_REVISION).down_revision
        == SHIPPING_CANCEL_REVISION
    )
    assert (
        scripts.get_revision(SHIPPING_GENERATION_REVISION).down_revision
        == SHIPPING_RESOLVE_STAGING_REVISION
    )
    assert (
        scripts.get_revision(SHIPPING_SCOPED_STALE_INDEX_REVISION).down_revision
        == SHIPPING_GENERATION_REVISION
    )
    assert (
        scripts.get_revision(AFTERSALE_CASE_MEDIA_REVISION).down_revision
        == SHIPPING_SCOPED_STALE_INDEX_REVISION
    )


def test_performance_critical_production_indexes_are_declared_in_metadata():
    from database.base import db
    import database.models.account  # noqa: F401
    import database.models.shipping  # noqa: F401

    for table_name, expected_indexes in CRITICAL_INDEXES.items():
        actual_indexes = {index.name for index in db.metadata.tables[table_name].indexes}
        assert expected_indexes <= actual_indexes


def test_shipping_standby_schema_tracks_live_schema_exactly():
    from database.base import db
    import database.models.shipping  # noqa: F401

    live = db.metadata.tables['shipping_order_finished']
    standby = db.metadata.tables['shipping_order_finished_next']
    assert [
        (
            column.name,
            str(column.type),
            column.nullable,
            column.primary_key,
        )
        for column in live.columns
    ] == [
        (
            column.name,
            str(column.type),
            column.nullable,
            column.primary_key,
        )
        for column in standby.columns
    ]
    assert {
        (index.name, tuple(column.name for column in index.columns))
        for index in live.indexes
    } == {
        (index.name, tuple(column.name for column in index.columns))
        for index in standby.indexes
    }


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


def test_production_foreign_key_delete_behaviour_is_preserved():
    from database.base import db
    import database.models.product.finished  # noqa: F401

    expected = {
        ('product_finished', 'model_id'): ('fk_finished_model', 'SET NULL'),
        ('product_finished_packaged', 'finished_id'): ('fk_fp_finished', 'CASCADE'),
        ('product_finished_packaged', 'packaged_id'): ('fk_fp_packaged', 'CASCADE'),
    }
    for (table_name, column_name), (constraint_name, ondelete) in expected.items():
        foreign_key, = db.metadata.tables[table_name].c[column_name].foreign_keys
        assert foreign_key.constraint.name == constraint_name
        assert foreign_key.ondelete == ondelete


def test_alembic_comment_plugin_is_disabled_but_structure_plugins_remain_enabled():
    plugins = ['alembic.autogenerate.*', '~alembic.autogenerate.comments']
    context = MigrationContext.configure(
        dialect_name='mysql',
        opts={'autogenerate_plugins': plugins},
    )
    autogen_context = AutogenContext(context, sa.MetaData())
    comparator_labels = {
        label
        for entries in autogen_context.comparators._registry.values()
        for _function, label in entries
    }

    assert 'comments' not in comparator_labels
    assert {'types', 'indexes', 'foreignkeys', 'nullable'} <= comparator_labels


def test_baseline_upgrade_adds_only_task_schemas(tmp_path, monkeypatch):
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
    assert after_upgrade == before_upgrade | {
        'shipping_task',
        'product_lifecycle_task',
        'shipping_resolve_target',
        'shipping_order_finished_staging',
        'shipping_order_finished_next',
        'shipping_order_finished_generation',
        'shipping_order_finished_generation_next',
        'aftersale_case_media',
        'aftersale_media_upload_session',
        'aftersale_media_cleanup_failure',
    }
    inspector = sa.inspect(engine)
    shipping_task_columns = {
        column['name'] for column in inspector.get_columns('shipping_task')
    }
    shipping_task_uniques = {
        tuple(constraint['column_names'])
        for constraint in inspector.get_unique_constraints('shipping_task')
    }
    assert 'lease_key' in shipping_task_columns
    assert 'cancel_requested_at' in shipping_task_columns
    assert 'cancel_requested_by' in shipping_task_columns
    assert ('lease_key',) in shipping_task_uniques
    lifecycle_task_columns = {
        column['name']
        for column in inspector.get_columns('product_lifecycle_task')
    }
    lifecycle_task_uniques = {
        tuple(constraint['column_names'])
        for constraint in inspector.get_unique_constraints('product_lifecycle_task')
    }
    assert 'lease_key' in lifecycle_task_columns
    assert ('lease_key',) in lifecycle_task_uniques
    standby_indexes = {
        index['name']
        for index in inspector.get_indexes(
            'shipping_order_finished_next'
        )
    }
    assert CRITICAL_INDEXES['shipping_order_finished'] <= standby_indexes
    with engine.connect() as connection:
        for marker_table in (
            'shipping_order_finished_generation',
            'shipping_order_finished_generation_next',
        ):
            assert connection.execute(sa.text(
                f'SELECT COUNT(*) FROM {marker_table} WHERE id = 1'
            )).scalar_one() == 1
    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
    assert current == HEAD_REVISION


def test_guest_role_migration_removes_role_and_associations(tmp_path, monkeypatch):
    database_path = tmp_path / 'guest-role.db'
    database_url = f'sqlite:///{database_path.as_posix()}'
    engine = sa.create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(sa.text(
            'CREATE TABLE roles (id INTEGER PRIMARY KEY, name VARCHAR(64), description VARCHAR(255))'
        ))
        connection.execute(sa.text(
            'CREATE TABLE user_roles (user_id INTEGER, role_id INTEGER)'
        ))
        connection.execute(sa.text(
            'CREATE TABLE role_permissions (role_id INTEGER, permission_id INTEGER)'
        ))
        connection.execute(sa.text(
            "INSERT INTO roles (id, name) VALUES (1, 'guest'), (2, 'admin')"
        ))
        connection.execute(sa.text(
            'INSERT INTO user_roles (user_id, role_id) VALUES (7, 1), (8, 2)'
        ))
        connection.execute(sa.text(
            'INSERT INTO role_permissions (role_id, permission_id) VALUES (1, 10), (2, 11)'
        ))

    monkeypatch.setenv('DATABASE_URL', database_url)
    config = _config(database_url)
    command.stamp(config, MAPPING_STATUS_REVISION)
    command.upgrade(config, GUEST_REMOVAL_REVISION)

    with engine.connect() as connection:
        assert connection.execute(
            sa.text("SELECT COUNT(*) FROM roles WHERE name = 'guest'")
        ).scalar_one() == 0
        assert connection.execute(
            sa.text('SELECT COUNT(*) FROM user_roles WHERE role_id = 1')
        ).scalar_one() == 0
        assert connection.execute(
            sa.text('SELECT COUNT(*) FROM role_permissions WHERE role_id = 1')
        ).scalar_one() == 0
        assert connection.execute(
            sa.text("SELECT COUNT(*) FROM roles WHERE name = 'admin'")
        ).scalar_one() == 1


def test_permission_domain_migration_prepares_roles_and_compatibility_mappings(
    tmp_path, monkeypatch
):
    database_path = tmp_path / 'permission-domains.db'
    database_url = f'sqlite:///{database_path.as_posix()}'
    engine = sa.create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(sa.text(
            'CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(64), '
            'token_version INTEGER NOT NULL DEFAULT 0)'
        ))
        connection.execute(sa.text(
            'CREATE TABLE roles (id INTEGER PRIMARY KEY, name VARCHAR(64), description VARCHAR(255))'
        ))
        connection.execute(sa.text(
            'CREATE TABLE permissions (id INTEGER PRIMARY KEY, code VARCHAR(64), '
            'name VARCHAR(255), description VARCHAR(255))'
        ))
        connection.execute(sa.text(
            'CREATE TABLE user_roles (user_id INTEGER, role_id INTEGER, '
            'PRIMARY KEY (user_id, role_id))'
        ))
        connection.execute(sa.text(
            'CREATE TABLE role_permissions (role_id INTEGER, permission_id INTEGER, '
            'PRIMARY KEY (role_id, permission_id))'
        ))
        connection.execute(sa.text(
            "INSERT INTO users (id, username) VALUES (1, 'author'), (2, 'staff')"
        ))
        connection.execute(sa.text(
            "INSERT INTO roles (id, name) VALUES (1, 'admin'), (2, 'existing-role')"
        ))
        connection.execute(sa.text(
            "INSERT INTO permissions (id, code) VALUES (1, 'product:view')"
        ))
        connection.execute(sa.text(
            'INSERT INTO user_roles (user_id, role_id) VALUES (1, 1), (2, 2)'
        ))
        connection.execute(sa.text(
            'INSERT INTO role_permissions (role_id, permission_id) VALUES (1, 1), (2, 1)'
        ))

    monkeypatch.setenv('DATABASE_URL', database_url)
    config = _config(database_url)
    command.stamp(config, GUEST_REMOVAL_REVISION)
    command.upgrade(config, PERMISSION_DOMAIN_REVISION)

    expected = {
        'developer': {'developer:analytics:view'},
        'manager': {
            'account:users:view',
            'account:users:edit',
            'account:roles:view',
            'account:roles:edit',
        },
        'ops': {'ops:login-config:edit'},
    }
    with engine.connect() as connection:
        rows = connection.execute(sa.text(
            'SELECT r.name, p.code FROM roles r '
            'JOIN role_permissions rp ON rp.role_id = r.id '
            'JOIN permissions p ON p.id = rp.permission_id'
        )).fetchall()
        actual = {}
        for role_name, permission_code in rows:
            actual.setdefault(role_name, set()).add(permission_code)

        for role_name, permission_codes in expected.items():
            assert actual[role_name] == permission_codes
        all_codes = {
            row[0] for row in connection.execute(
                sa.text('SELECT code FROM permissions')
            ).fetchall()
        }
        assert actual['admin'] == all_codes
        assert 'ops:release:edit' not in all_codes

        author_roles = {
            row[0] for row in connection.execute(sa.text(
                "SELECT r.name FROM roles r JOIN user_roles ur ON ur.role_id = r.id "
                "JOIN users u ON u.id = ur.user_id WHERE u.username = 'author'"
            )).fetchall()
        }
        assert author_roles == {'admin', 'developer'}
        assert connection.execute(sa.text(
            'SELECT COUNT(*) FROM user_roles WHERE user_id = 2 AND role_id = 2'
        )).scalar_one() == 1
        versions = dict(connection.execute(sa.text(
            'SELECT username, token_version FROM users'
        )).fetchall())
        assert versions == {'author': 1, 'staff': 0}
