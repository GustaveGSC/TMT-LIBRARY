from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import List, Dict
from database.base import db
from database.models.product.import_raw import ImportProductRaw

CST = timezone(timedelta(hours=8))


class ImportProductRepository:

    @staticmethod
    def bulk_upsert(rows: List[Dict], imported_at: datetime) -> Dict[str, int]:
        """批量新增或更新 ERP 权威字段；完全相同的行不写库。"""
        codes = [row['code'] for row in rows]
        existing = {
            row.code: row for row in ImportProductRaw.query
            .filter(ImportProductRaw.code.in_(codes)).all()
        }
        to_insert = [
            ImportProductRaw(
                code        = row['code'],
                name        = row['name'],
                spec        = row.get('spec'),
                group_code  = row['group_code'],
                group_name  = row['group_name'],
                imported_at = imported_at,
            )
            for row in rows
            if row['code'] not in existing
        ]
        to_update = []
        fields = ('name', 'spec', 'group_code', 'group_name')
        for row in rows:
            current = existing.get(row['code'])
            if current is None or all(getattr(current, key) == row.get(key) for key in fields):
                continue
            to_update.append({
                'id': current.id,
                **{key: row.get(key) for key in fields},
                'imported_at': imported_at,
            })
        if to_insert:
            db.session.bulk_save_objects(to_insert)
        if to_update:
            db.session.bulk_update_mappings(ImportProductRaw, to_update)
        if to_insert or to_update:
            db.session.commit()
        return {
            'inserted': len(to_insert),
            'updated': len(to_update),
            'unchanged': len(rows) - len(to_insert) - len(to_update),
        }

    @staticmethod
    def get_stats() -> Dict:
        """获取概览统计：成品总数、待处理、最近导入、成品分类（均排除 ignored）"""
        from database.models.product.erp_code_rules import ErpCodeRule
        from database.models.product.finished import ProductFinished

        # 最近导入时间
        latest = db.session.query(db.func.max(ImportProductRaw.imported_at)).scalar()
        last_imported_at = latest.strftime('%Y-%m-%d') if latest else None
        days_since_import = None
        if latest:
            now = datetime.now(CST).replace(tzinfo=None)
            days_since_import = (now - latest).days

        # 获取所有 type='finished' 且未禁用的编码规则（禁用规则对应的成品不统计）
        finished_rules = ErpCodeRule.query.filter_by(type='finished', is_disabled=False).all()
        prefix_desc = [(r.prefix, r.description or '') for r in finished_rules]
        # 禁用规则的前缀集合，用于过滤 finished_count
        disabled_prefixes = [
            r.prefix for r in ErpCodeRule.query.filter_by(type='finished', is_disabled=True).all()
        ]

        # 已标记为 ignored 的品号集合，统计时排除
        ignored_codes = {
            row[0] for row in db.session.query(ProductFinished.code)
            .filter(ProductFinished.status == 'ignored').all()
        }

        # 已处理品号集合：在 product_finished 且状态为 recorded（非 unrecorded/ignored）
        processed_codes = {
            row[0] for row in db.session.query(ProductFinished.code)
            .filter(ProductFinished.status == 'recorded').all()
        }

        # 遍历 import 表，按 description 分组计数（跳过 ignored）
        all_codes = [r.code for r in db.session.query(ImportProductRaw.code).all()]
        desc_counts      = defaultdict(int)
        desc_unprocessed = defaultdict(int)
        total_finished = 0
        for code in all_codes:
            if code in ignored_codes:
                continue
            matched_descs = set()
            for prefix, desc in prefix_desc:
                if code.startswith(prefix):
                    matched_descs.add(desc)
            if matched_descs:
                total_finished += 1
                is_unprocessed = code not in processed_codes
                for desc in matched_descs:
                    desc_counts[desc] += 1
                    if is_unprocessed:
                        desc_unprocessed[desc] += 1

        # 待处理 = 成品总数(排除ignored) - product_finished 非ignored记录数
        # 同时排除禁用前缀对应的成品
        finished_q = ProductFinished.query.filter(ProductFinished.status != 'ignored')
        if disabled_prefixes:
            from sqlalchemy import and_, not_, or_
            finished_q = finished_q.filter(
                not_(or_(*[ProductFinished.code.like(p + '%') for p in disabled_prefixes]))
            )
        finished_count = finished_q.count()
        unprocessed = max(0, total_finished - finished_count)

        categories = [
            {'description': desc, 'count': count, 'unprocessed': desc_unprocessed.get(desc, 0)}
            for desc, count in sorted(desc_counts.items(), key=lambda x: -x[1])
        ]

        return {
            'total_finished':   total_finished,
            'unprocessed':      unprocessed,
            'last_imported_at': last_imported_at,
            'days_since_import': days_since_import,
            'categories':       categories,
        }
