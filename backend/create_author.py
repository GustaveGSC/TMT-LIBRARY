"""
一次性脚本：创建 author 开发者账号并赋予 admin 角色
用法：python create_author.py <密码>
"""
import sys
import os

# 加载 .env
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

from app import create_app
import bcrypt
from database.base import db
from database.repository.account import UserRepository, RoleRepository

def main():
    if len(sys.argv) < 2:
        print("用法: python create_author.py <密码>")
        sys.exit(1)

    password = sys.argv[1]
    if len(password) < 6:
        print("密码至少 6 位")
        sys.exit(1)

    app = create_app()
    with app.app_context():
        if UserRepository.get_by_username('author'):
            print("author 用户已存在，跳过创建")
            return

        pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        user = UserRepository.create('author', pw_hash, '开发者')

        admin_role = RoleRepository.get_by_name('admin')
        if admin_role:
            UserRepository.assign_role(user, admin_role)
            print("author created with admin role")
        else:
            print("author created (admin role not found, assign manually)")

if __name__ == '__main__':
    main()
