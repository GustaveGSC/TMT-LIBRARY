"""
权限初始化脚本：写入所有标准权限项。
在项目根目录执行：python backend/scripts/seed_permissions.py
已存在的权限码会跳过（不重复创建）。
"""
import sys
import os
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

from app import create_app
from database.base import db
from database.models.account import Permission

# 所有标准权限项：(code, description)
# Permission 模型只有 code + description，无 name 字段
PERMISSIONS = [
    # 产品库
    ("product:view",   "查看产品列表、成品详情"),
    ("product:edit",   "录入/编辑成品信息、导入ERP数据、管理分类/标签/参数"),
    # 物料库（独立于产品库，2026-09-04 起不再借用 product:view/edit）
    ("material:view",  "查看物料清单、组合套餐、编码规则"),
    ("material:edit",  "编辑物料信息、分组默认大类/编码前缀例外、组合套餐、导入物料ERP数据"),
    ("material:price", "查看/编辑物料成本价格与供应商信息"),
    # 发货数据
    ("shipping:view",   "查看发货看板与统计图表"),
    ("shipping:edit",   "导入发货/销退清单、配置操作人与仓库过滤"),
    ("shipping:export", "导出发货统计报表"),
    # 售后数据（预留）
    ("aftersale:view",   "查看售后记录与统计"),
    ("aftersale:edit",   "录入/编辑售后记录"),
    ("aftersale:export", "导出售后统计报表"),
    # 研发数据
    ("rd:view",  "查看研发相关数据"),
    ("rd:edit",  "编辑研发相关数据"),
    ("rd:admin", "研发部管理员：管理物料门禁条目"),
    # 外贸工具（2026-09-27 起，先只有查看；产品改制方案确认后再加编辑/建码权限）
    ("trade:view", "查看外贸工具（产品改制等）"),
    # 开发者
    ("developer:analytics:view", "查看登录日志、DAU 和用户登录统计"),
    ("developer:tasks:view", "查看/创建/编辑/关闭开发任务"),
    # 管理者
    ("account:users:view", "查看用户列表和用户详情"),
    ("account:users:edit", "创建、编辑、禁用、删除、重置密码和分配角色"),
    ("account:roles:view", "查看角色和权限清单"),
    ("account:roles:edit", "创建删除角色、维护权限项和调整角色权限"),
    # 运维
    ("ops:login-config:edit", "修改登录页轮播文案"),
    ("ops:department:edit", "新增/编辑/删除部门"),
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
