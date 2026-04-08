"""
migration: 新增 aftersale_keyword_candidate 表
用于关键词候选池，记录 n-gram 在各原因下的出现次数，达到阈值后晋升到原因 keywords 字段。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app import create_app
from database.base import db

DDL = """
CREATE TABLE IF NOT EXISTS aftersale_keyword_candidate (
    id        INT          NOT NULL AUTO_INCREMENT PRIMARY KEY,
    reason_id INT          NOT NULL,
    keyword   VARCHAR(20)  NOT NULL,
    count     INT          NOT NULL DEFAULT 1,
    UNIQUE KEY uq_keyword_candidate (reason_id, keyword),
    KEY        idx_reason_id (reason_id),
    CONSTRAINT fk_kw_candidate_reason
        FOREIGN KEY (reason_id) REFERENCES aftersale_reason(id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

if __name__ == '__main__':
    app = create_app()
    with app.app_context():
        db.session.execute(db.text(DDL))
        db.session.commit()
        print('OK: aftersale_keyword_candidate 表已创建')
