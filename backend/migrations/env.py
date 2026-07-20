import os
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import URL


BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / '.env', override=True)

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)


def _database_url() -> str:
    explicit = os.getenv('DATABASE_URL')
    if explicit:
        return explicit
    return URL.create(
        drivername='mysql+pymysql',
        username=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        host=os.getenv('DB_HOST', '127.0.0.1'),
        port=int(os.getenv('DB_PORT', '3306')),
        database=os.getenv('DB_NAME'),
    ).render_as_string(hide_password=False)


config.set_main_option('sqlalchemy.url', _database_url().replace('%', '%%'))

# Alembic autogenerate 必须显式加载全部模型，不能依赖 Flask 路由的偶然导入顺序。
from database.base import db  # noqa: E402
import database.models.account  # noqa: E402,F401
import database.models.aftersale  # noqa: E402,F401
import database.models.shipping  # noqa: E402,F401
import database.models.version  # noqa: E402,F401
import database.models.rd  # noqa: E402,F401
import database.models.rd.cost  # noqa: E402,F401
import database.models.product.category  # noqa: E402,F401
import database.models.product.erp_code_rules  # noqa: E402,F401
import database.models.product.finished  # noqa: E402,F401
import database.models.product.import_raw  # noqa: E402,F401
import database.models.product.param  # noqa: E402,F401
import database.models.product.resource  # noqa: E402,F401

target_metadata = db.metadata

# 这些表对应的功能已在 7736296 中从业务代码移除，但生产数据仍待归档。
# Alembic 暂不管理它们，避免 autogenerate 静默生成 DROP TABLE。
LEGACY_UNMANAGED_TABLES = frozenset({
    'aftersale_reason_component_term',
    'aftersale_reason_fault_term',
    'aftersale_reason_synonym_rule',
})
LEGACY_UNMANAGED_COLUMNS = frozenset({
    ('cost_bom_node', 'is_virtual_semi'),
})
MODEL_ONLY_FOREIGN_KEYS = frozenset({
    ('aftersale_case_reason', 'model_id'),
    ('aftersale_case_reason', 'reason_category_id'),
})


def include_object(obj, name, type_, reflected, compare_to):
    table_name = name if type_ == 'table' else getattr(getattr(obj, 'table', None), 'name', None)
    if table_name in LEGACY_UNMANAGED_TABLES:
        return False
    if type_ == 'column' and reflected and (table_name, name) in LEGACY_UNMANAGED_COLUMNS:
        return False
    if type_ == 'foreign_key_constraint' and not reflected:
        local_columns = tuple(column.name for column in obj.columns)
        if len(local_columns) == 1 and (table_name, local_columns[0]) in MODEL_ONLY_FOREIGN_KEYS:
            return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option('sqlalchemy.url'),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={'paramstyle': 'named'},
        compare_type=True,
        compare_comments=False,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix='sqlalchemy.',
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_comments=False,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
