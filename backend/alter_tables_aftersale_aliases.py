"""
数据库变更脚本：新建发货物料简称库表 + 售后物料简称库表

  aftersale_shipping_alias  —— 发货物料简称库
  aftersale_return_alias    —— 售后物料简称库

在 backend/ 目录下执行：python alter_tables_aftersale_aliases.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from database.base import db

app = create_app()

NEW_TABLES = [
    (
        "aftersale_shipping_alias",
        """
        CREATE TABLE aftersale_shipping_alias (
            id         INT          NOT NULL AUTO_INCREMENT,
            name       VARCHAR(200) NOT NULL UNIQUE,
            sort_order INT          NOT NULL DEFAULT 0,
            created_at DATETIME     NOT NULL,
            PRIMARY KEY (id)
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """,
    ),
    (
        "aftersale_return_alias",
        """
        CREATE TABLE aftersale_return_alias (
            id         INT          NOT NULL AUTO_INCREMENT,
            name       VARCHAR(200) NOT NULL UNIQUE,
            sort_order INT          NOT NULL DEFAULT 0,
            created_at DATETIME     NOT NULL,
            PRIMARY KEY (id)
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """,
    ),
]

with app.app_context():
    for table_name, create_sql in NEW_TABLES:
        check_sql = db.text("""
            SELECT COUNT(*) FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME   = :tbl
        """)
        count = db.session.execute(check_sql, {'tbl': table_name}).scalar()
        if count:
            print(f'  [SKIP] {table_name} 已存在，跳过。')
            continue
        try:
            db.session.execute(db.text(create_sql))
            db.session.commit()
            print(f'  [OK]   {table_name} 已创建')
        except Exception as e:
            db.session.rollback()
            print(f'  [WARN] {table_name}: {e}')
    print('迁移完成。')
