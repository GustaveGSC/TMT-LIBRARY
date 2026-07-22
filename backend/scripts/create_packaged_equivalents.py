"""
建表脚本：创建产成品通用件表 packaged_equivalent。
在项目根目录执行：python3.11 backend/scripts/create_packaged_equivalents.py
表已存在时跳过，不会重复创建或清空数据。
"""
import sys
import os
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

from app import create_app
from database.base import db

app = create_app()

with app.app_context():
    from sqlalchemy import text, inspect
    inspector = inspect(db.engine)
    if 'packaged_equivalent' in inspector.get_table_names():
        print('表 packaged_equivalent 已存在，跳过。')
    else:
        with db.engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE packaged_equivalent (
                    id         INTEGER      NOT NULL AUTO_INCREMENT,
                    code_a     VARCHAR(64)  NOT NULL,
                    code_b     VARCHAR(64)  NOT NULL,
                    note       VARCHAR(255) NULL,
                    created_at DATETIME     NOT NULL,
                    PRIMARY KEY (id),
                    UNIQUE KEY uq_equiv_pair (code_a, code_b),
                    KEY ix_equiv_code_a (code_a),
                    KEY ix_equiv_code_b (code_b)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """))
            conn.commit()
        print('表 packaged_equivalent 创建成功。')
