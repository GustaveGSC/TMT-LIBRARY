"""
内置角色初始化脚本：创建固定角色并绑定权限。
在 backend/ 目录下执行：python seed_roles.py
已存在的角色会跳过（不重复创建）。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from database.base import db
from database.models.account import Role, Permission

# 内置角色定义：(name, description, [权限码列表])
BUILTIN_ROLES = [
    (
        "guest",
        "游客（内置）——仅可查看产品库",
        ["product:view"],
    ),
]

app = create_app()

with app.app_context():
    for name, description, perm_codes in BUILTIN_ROLES:
        role = Role.query.filter_by(name=name).first()
        if role:
            print(f"  跳过（已存在）: {name}")
        else:
            role = Role(name=name, description=description)
            db.session.add(role)
            db.session.flush()  # 获取 id
            print(f"  创建角色: {name}")

        # 绑定权限（幂等）
        for code in perm_codes:
            perm = Permission.query.filter_by(code=code).first()
            if not perm:
                print(f"    ! 权限码不存在，跳过: {code}  （请先运行 seed_permissions.py）")
                continue
            if perm not in role.permissions:
                role.permissions.append(perm)
                print(f"    绑定权限: {code}")
            else:
                print(f"    已绑定（跳过）: {code}")

    db.session.commit()
    print("\n完成。")
