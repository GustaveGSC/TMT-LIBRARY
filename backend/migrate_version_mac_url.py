"""
迁移：app_version 表新增 mac_download_url 列
运行：python migrate_version_mac_url.py
"""
from app import create_app
from database.base import db

app = create_app()
with app.app_context():
    try:
        with db.engine.connect() as conn:
            conn.execute(db.text(
                "ALTER TABLE app_version ADD COLUMN mac_download_url VARCHAR(500) NULL AFTER download_url"
            ))
            conn.commit()
        print("✅ mac_download_url 列添加成功")
    except Exception as e:
        if 'Duplicate column' in str(e) or '1060' in str(e):
            print("ℹ️  列已存在，跳过")
        else:
            raise
