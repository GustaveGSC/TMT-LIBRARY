"""
迁移脚本：将 product_series.code 和 product_model.code 的全局唯一约束
改为在父级范围内唯一（系列code在品类内唯一，型号code在系列内唯一）。

在 backend/ 目录下执行：python alter_tables_category_code.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from database.base import db

app = create_app()

with app.app_context():
    conn = db.engine.connect()
    trans = conn.begin()
    try:
        # ── product_series ────────────────────────────────────────────────
        # 删除旧的单列唯一索引，重建为复合唯一索引
        conn.execute(db.text("ALTER TABLE product_series DROP INDEX uq_series_code"))
        print("  已删除 product_series.uq_series_code 单列索引")

        conn.execute(db.text(
            "ALTER TABLE product_series ADD CONSTRAINT uq_series_code UNIQUE (category_id, code)"
        ))
        print("  已添加 product_series UNIQUE(category_id, code)")

        # ── product_model ─────────────────────────────────────────────────
        conn.execute(db.text("ALTER TABLE product_model DROP INDEX uq_model_code"))
        print("  已删除 product_model.uq_model_code 单列索引")

        conn.execute(db.text(
            "ALTER TABLE product_model ADD CONSTRAINT uq_model_code UNIQUE (series_id, code)"
        ))
        print("  已添加 product_model UNIQUE(series_id, code)")

        trans.commit()
        print("\n迁移完成。")
    except Exception as e:
        trans.rollback()
        print(f"\n迁移失败，已回滚：{e}")
        raise
    finally:
        conn.close()
