"""
数据库变更脚本 v2：
  1. 创建 return_record 表
  2. 创建 return_warehouse_filter 表
  3. shipping_order_finished 加 return_quantity / actual_quantity 列

在 backend/ 目录下执行：python alter_tables_v2.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from database.base import db
import database.models.shipping  # noqa — 确保模型注册到 metadata

app = create_app()

STMTS = [
    # 创建 return_record 表
    """
    CREATE TABLE IF NOT EXISTS return_record (
        id                 INT          NOT NULL AUTO_INCREMENT,
        batch_id           INT          NOT NULL,
        ecommerce_order_no VARCHAR(100),
        shipped_date       DATE,
        product_code       VARCHAR(100),
        quantity           DECIMAL(12,2),
        warehouse_name     VARCHAR(100),
        PRIMARY KEY (id),
        UNIQUE KEY uq_return_order_product_date (ecommerce_order_no, product_code, shipped_date),
        KEY ix_return_record_order_no     (ecommerce_order_no),
        KEY ix_return_record_product_code (product_code),
        KEY ix_return_record_shipped_date (shipped_date),
        CONSTRAINT fk_return_record_batch FOREIGN KEY (batch_id)
            REFERENCES shipping_batch (id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    # 创建 return_warehouse_filter 表
    """
    CREATE TABLE IF NOT EXISTS return_warehouse_filter (
        id             INT          NOT NULL AUTO_INCREMENT,
        warehouse_name VARCHAR(100) NOT NULL,
        is_excluded    TINYINT(1)   NOT NULL DEFAULT 0,
        created_at     DATETIME     NOT NULL,
        PRIMARY KEY (id),
        UNIQUE KEY uq_warehouse_name (warehouse_name)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    # shipping_order_finished 加列（已存在则跳过）
    """
    ALTER TABLE shipping_order_finished
        ADD COLUMN IF NOT EXISTS return_quantity DECIMAL(12,2) DEFAULT 0,
        ADD COLUMN IF NOT EXISTS actual_quantity DECIMAL(12,2)
    """,
]

with app.app_context():
    for sql in STMTS:
        try:
            db.session.execute(db.text(sql.strip()))
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f'[WARN] {e}')
    print('迁移完成：return_record / return_warehouse_filter 已创建，shipping_order_finished 已更新。')
