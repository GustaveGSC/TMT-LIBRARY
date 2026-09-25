"""研发物料门禁的数据迁移和纯逻辑契约测试。"""

from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from openpyxl import Workbook

from services.rd.change_documents import compare_bom


ROOT = Path(__file__).resolve().parents[2]
PREVIOUS_REVISION = '20260904_02'
MATERIAL_GATE_REVISION = '20260925_01'


def _alembic_config(database_url: str) -> Config:
    config = Config(str(ROOT / 'alembic.ini'))
    config.set_main_option('sqlalchemy.url', database_url)
    return config


def _write_bom(path, rows):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(['层次', '图号', '品名', '规格', '数量', '单位', '状态'])
    for row in rows:
        sheet.append(row)
    workbook.save(path)


def test_compare_bom_returns_sorted_unique_after_codes(tmp_path):
    before_path = tmp_path / 'before.xlsx'
    after_path = tmp_path / 'after.xlsx'
    _write_bom(before_path, [
        ['1', 'ROOT-A01', '整机', 'ROOT_A01', 1, 'PCS', '已发布'],
    ])
    _write_bom(after_path, [
        ['1', 'ROOT-A01', '整机', 'ROOT_A01', 1, 'PCS', '已发布'],
        ['1.1', 'B002-A01', '零件B', 'B002_A01', 1, 'PCS', '已发布'],
        ['1.2', 'A001-A01', '零件A', 'A001_A01', 1, 'PCS', '已发布'],
    ])

    result = compare_bom(before_path, after_path)

    assert result['after_codes'] == ['A001', 'B002', 'ROOT']


def test_material_gate_migration_replaces_legacy_table(tmp_path, monkeypatch):
    database_path = tmp_path / 'material-gate.db'
    database_url = f'sqlite:///{database_path.as_posix()}'
    engine = sa.create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(sa.text(
            'CREATE TABLE ecr_reminder ('
            'id INTEGER PRIMARY KEY, content VARCHAR(500) NOT NULL, notes TEXT, '
            'is_active BOOLEAN NOT NULL, created_by VARCHAR(64), '
            'created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)'
        ))

    monkeypatch.setenv('DATABASE_URL', database_url)
    config = _alembic_config(database_url)
    command.stamp(config, PREVIOUS_REVISION)
    command.upgrade(config, MATERIAL_GATE_REVISION)

    inspector = sa.inspect(engine)
    assert 'material_gate' in inspector.get_table_names()
    assert 'ecr_reminder' not in inspector.get_table_names()
    assert {column['name'] for column in inspector.get_columns('material_gate')} == {
        'id', 'code', 'level', 'reason', 'is_active',
        'created_by', 'created_at', 'updated_at',
    }

    command.downgrade(config, PREVIOUS_REVISION)
    inspector = sa.inspect(engine)
    assert 'material_gate' not in inspector.get_table_names()
    assert 'ecr_reminder' in inspector.get_table_names()
