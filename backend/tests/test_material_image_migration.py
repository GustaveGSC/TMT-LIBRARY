"""material_image 迁移：建表并把 product_material 的历史单图搬进来。"""

from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config


ROOT = Path(__file__).resolve().parents[2]


def test_material_image_migration_backfills_existing_cover(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'mi.db').as_posix()}"
    engine = sa.create_engine(url)
    with engine.begin() as conn:
        conn.execute(sa.text(
            'CREATE TABLE product_material (id INTEGER PRIMARY KEY, code VARCHAR(255) NOT NULL, '
            'cover_image VARCHAR(500), cover_image_original VARCHAR(500), '
            'created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)'
        ))
        conn.execute(sa.text(
            "INSERT INTO product_material (code, cover_image, cover_image_original, created_at, updated_at) VALUES "
            "('A', 'http://x/a.png', 'http://x/a_orig.png', '2026-09-01', '2026-09-02'),"
            "('B', NULL, NULL, '2026-09-01', '2026-09-01'),"
            "('C', '', NULL, '2026-09-01', '2026-09-01')"
        ))

    monkeypatch.setenv('DATABASE_URL', url)
    config = Config(str(ROOT / 'alembic.ini'))
    config.set_main_option('sqlalchemy.url', url)
    command.stamp(config, '20260927_01')
    command.upgrade(config, '20260927_02')

    with engine.connect() as conn:
        rows = conn.execute(sa.text(
            'SELECT code, url, orig_url, sort_order FROM material_image ORDER BY code'
        )).all()
    assert rows == [('A', 'http://x/a.png', 'http://x/a_orig.png', 0)]

    command.downgrade(config, '20260927_01')
    assert 'material_image' not in sa.inspect(engine).get_table_names()
