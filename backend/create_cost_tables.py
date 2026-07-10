"""
创建 BOM 成本库相关数据表。
用法：
    python create_cost_tables.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'), override=True)

from app import create_app
from database.base import db
from database.models.rd.cost import (
    CostSnapshot, CostSnapshotSku, CostBomNode,
    CostBomLine, CostMaterialSupplier, CostMaterialRule, CostMaterialPrice,
)

app = create_app()

with app.app_context():
    tables = [
        CostBomNode.__table__,        # 先建节点表（被其他表引用）
        CostSnapshot.__table__,
        CostSnapshotSku.__table__,
        CostBomLine.__table__,
        CostMaterialSupplier.__table__,
        CostMaterialRule.__table__,
        CostMaterialPrice.__table__,
    ]
    for t in tables:
        t.create(bind=db.engine, checkfirst=True)
        print(f'[OK] 表 {t.name} 已创建或已存在')

    print('\n全部完成。')
