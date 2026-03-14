from datetime import datetime
from typing import List, Dict
from database.base import db
from database.models.product.import_raw import ImportProductRaw


class ImportProductRepository:

    @staticmethod
    def get_existing_codes() -> set:
        """获取所有已存在的品号"""
        rows = db.session.query(ImportProductRaw.code).all()
        return {r.code for r in rows}

    @staticmethod
    def bulk_insert(rows: List[Dict], imported_at: datetime) -> int:
        """批量插入，跳过已存在的 code，返回实际插入行数"""
        existing = ImportProductRepository.get_existing_codes()
        to_insert = [
            ImportProductRaw(
                code        = row['code'],
                name        = row['name'],
                group_code  = row['group_code'],
                group_name  = row['group_name'],
                imported_at = imported_at,
            )
            for row in rows
            if row['code'] not in existing
        ]
        if to_insert:
            db.session.bulk_save_objects(to_insert)
            db.session.commit()
        return len(to_insert)

    @staticmethod
    def get_stats() -> Dict:
        """获取统计：总数、最近导入时间"""
        total = ImportProductRaw.query.count()
        latest = db.session.query(
            db.func.max(ImportProductRaw.imported_at)
        ).scalar()
        return {
            'total':            total,
            'last_imported_at': latest.strftime('%Y-%m-%d %H:%M') if latest else None,
        }
