"""
权限初始化脚本：写入所有标准权限项。
在 backend/ 目录下执行：python seed_permissions.py
已存在的权限码会跳过（不重复创建）。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from database.base import db
from database.models.account import Permission

# 所有标准权限项：(code, description)
# Permission 模型只有 code + description，无 name 字段
PERMISSIONS = [
    # 产品库
    ("product:view",   "查看产品列表、成品详情"),
    ("product:edit",   "录入/编辑成品信息、导入ERP数据、管理分类/标签/参数"),
    ("product:delete", "删除产品记录"),
    # 发货数据
    ("shipping:view",   "查看发货看板与统计图表"),
    ("shipping:edit",   "导入发货/销退清单、配置操作人与仓库过滤"),
    ("shipping:export", "导出发货统计报表"),
    # 售后数据（预留）
    ("aftersale:view",   "查看售后记录与统计"),
    ("aftersale:edit",   "录入/编辑售后记录"),
    ("aftersale:export", "导出售后统计报表"),
    # 研发数据（预留）
    ("rd:view", "查看研发相关数据"),
    ("rd:edit", "编辑研发相关数据"),
]

app = create_app()

with app.app_context():
    created = 0
    skipped = 0
    for code, description in PERMISSIONS:
        exists = db.session.query(Permission).filter_by(code=code).first()
        if exists:
            print(f"  跳过（已存在）: {code}")
            skipped += 1
        else:
            perm = Permission(code=code, description=description)
            db.session.add(perm)
            print(f"  创建: {code}")
            created += 1
    db.session.commit()
    print(f"\n完成：新建 {created} 条，跳过 {skipped} 条。")
