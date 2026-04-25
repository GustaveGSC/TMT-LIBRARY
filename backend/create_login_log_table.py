"""
一次性脚本：创建 user_login_log 表（登录记录）
用法：python create_login_log_table.py
"""
import os
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

from app import create_app
from database.base import db

DDL = """
CREATE TABLE IF NOT EXISTS `user_login_log` (
  `id`           INT          NOT NULL AUTO_INCREMENT,
  `user_id`      INT          NULL,
  `username`     VARCHAR(64)  NOT NULL,
  `display_name` VARCHAR(64)  NULL,
  `status`       ENUM('success','failed') NOT NULL DEFAULT 'success',
  `login_at`     DATETIME     NOT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_login_log_user_id`  (`user_id`),
  KEY `ix_login_log_login_at` (`login_at`),
  CONSTRAINT `fk_login_log_user`
    FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

def main():
    app = create_app()
    with app.app_context():
        db.session.execute(db.text(DDL))
        db.session.commit()
        print("user_login_log OK")

if __name__ == '__main__':
    main()
