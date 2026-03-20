from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import List, Dict
from database.base import db
from database.models.product.import_raw import ImportProductRaw

CST = timezone(timedelta(hours=8))


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
        """获取概览统计：成品总数、待处理、最近导入、成品分类"""
        from database.models.product.erp_code_rules import ErpCodeRule
        from database.models.product.finished import ProductFinished

        # 最近导入时间
        latest = db.session.query(db.func.max(ImportProductRaw.imported_at)).scalar()
        last_imported_at = latest.strftime('%Y-%m-%d') if latest else None
        days_since_import = None
        if latest:
            now = datetime.now(CST).replace(tzinfo=None)
            days_since_import = (now - latest).days

        # 获取所有 type='finished' 的编码规则
        finished_rules = ErpCodeRule.query.filter_by(type='finished').all()
        prefix_desc = [(r.prefix, r.description or '') for r in finished_rules]

        # 遍历 import 表，按 description 分组计数
        all_codes = [r.code for r in db.session.query(ImportProductRaw.code).all()]
        desc_counts = defaultdict(int)
        total_finished = 0
        for code in all_codes:
            matched_descs = set()
            for prefix, desc in prefix_desc:
                if code.startswith(prefix):
                    matched_descs.add(desc)
            if matched_descs:
                total_finished += 1
                for desc in matched_descs:
                    desc_counts[desc] += 1

        # 待处理 = 成品总数 - product_finished 表已有的记录数
        finished_count = ProductFinished.query.count()
        unprocessed = max(0, total_finished - finished_count)

        categories = [
            {'description': desc, 'count': count}
            for desc, count in sorted(desc_counts.items(), key=lambda x: -x[1])
        ]

        return {
            'total_finished':   total_finished,
            'unprocessed':      unprocessed,
            'last_imported_at': last_imported_at,
            'days_since_import': days_since_import,
            'categories':       categories,
        }
