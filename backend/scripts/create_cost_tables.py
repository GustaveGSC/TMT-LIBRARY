"""
创建 BOM 成本库相关数据表。
用法：
    python backend/scripts/create_cost_tables.py
"""
import os, sys
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(BACKEND_DIR, '.env'), override=True)

from app import create_app
from database.base import db
from database.models.rd.cost import (
    CostSnapshot, CostSnapshotSku, CostBomNode,
    CostBomLine, CostMaterialRule, CostMaterialPrice,
)

app = create_app()

with app.app_context():
    tables = [
        CostBomNode.__table__,        # 先建节点表（被其他表引用）
        CostSnapshot.__table__,
        CostSnapshotSku.__table__,
        CostBomLine.__table__,
        CostMaterialRule.__table__,
        CostMaterialPrice.__table__,
    ]
    for t in tables:
        t.create(bind=db.engine, checkfirst=True)
        print(f'[OK] 表 {t.name} 已创建或已存在')

    print('\n全部完成。')
