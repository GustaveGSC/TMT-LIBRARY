from datetime import datetime
from typing import List, Dict, Set, Tuple
from database.base import db
from database.models.shipping import (
    ShippingBatch, ShippingRecord,
    ShippingOperatorType, ShippingOrderFinished,
)


class ShippingRepository:

    # ── 批次 ────────────────────────────────────────

    @staticmethod
    def create_batch(type_: str, filename: str, row_count: int, imported_at: datetime) -> ShippingBatch:
        batch = ShippingBatch(
            type        = type_,
            filename    = filename,
            row_count   = row_count,
            imported_at = imported_at,
        )
        db.session.add(batch)
        db.session.flush()  # 获取 batch.id，尚未 commit
        return batch

    # ── 查询已存在键 ──────────────────────────────────

    @staticmethod
    def get_existing_keys(keys: List[Tuple]) -> Set[Tuple]:
        """
        给定 (ecommerce_order_no, line_no, product_code) 三元组列表，
        返回数据库中已存在的子集（Set of tuple）。
        """
        if not keys:
            return set()
        existing = set()
        # 分批查询，避免 IN 子句过长
        CHUNK = 500
        for i in range(0, len(keys), CHUNK):
            chunk = keys[i:i + CHUNK]
            rows = db.session.query(
                ShippingRecord.ecommerce_order_no,
                ShippingRecord.line_no,
                ShippingRecord.product_code,
            ).filter(
                db.tuple_(
                    ShippingRecord.ecommerce_order_no,
                    ShippingRecord.line_no,
                    ShippingRecord.product_code,
                ).in_(chunk)
            ).all()
            for r in rows:
                existing.add((r.ecommerce_order_no, r.line_no, r.product_code))
        return existing

    @staticmethod
    def delete_batch(batch_id: int):
        """回滚：删除批次及其关联的所有 ShippingRecord"""
        db.session.query(ShippingRecord).filter_by(batch_id=batch_id).delete(synchronize_session=False)
        db.session.query(ShippingBatch).filter_by(id=batch_id).delete(synchronize_session=False)
        db.session.commit()

    # ── 去重插入 ─────────────────────────────────────

    @staticmethod
    def bulk_insert_shipping(batch_id: int, rows: List[Dict], progress_cb=None) -> int:
        """
        分块 INSERT IGNORE，已存在行静默跳过，返回实际新增行数。
        progress_cb(current, total)：每完成一块调用一次。
        """
        if not rows:
            return 0
        from sqlalchemy import insert as sa_insert

        CHUNK = 100   # 每 100 行通知一次进度
        total = len(rows)

        def _make_param(row):
            return {
                'batch_id':           batch_id,
                'ecommerce_order_no': row.get('ecommerce_order_no'),
                'line_no':            row.get('line_no'),
                'shipped_date':       row.get('shipped_date'),
                'channel_name':       row.get('channel_name'),
                'channel_code':       row.get('channel_code'),
                'channel_org_name':   row.get('channel_org_name'),
                'operator':           row.get('operator'),
                'product_code':       row.get('product_code'),
                'product_name':       row.get('product_name'),
                'spec':               row.get('spec'),
                'quantity':           row.get('quantity'),
                'country':            row.get('country'),
                'province':           row.get('province'),
                'city':               row.get('city'),
                'district':           row.get('district'),
                'street':             row.get('street'),
                'address':            row.get('address'),
                'buyer_remark':       row.get('buyer_remark'),
                'seller_remark':      row.get('seller_remark'),
            }

        stmt = sa_insert(ShippingRecord).prefix_with('IGNORE')
        for i in range(0, total, CHUNK):
            chunk = rows[i:i + CHUNK]
            db.session.execute(stmt, [_make_param(r) for r in chunk])
            db.session.commit()
            if progress_cb:
                progress_cb(min(i + len(chunk), total), total)

        return total

    # ── 操作人 ───────────────────────────────────────

    @staticmethod
    def get_all_operators() -> List[Dict]:
        """从 shipping_record 中收集所有不重复操作人，与 shipping_operator_type 合并返回"""
        # 已分类的操作人
        classified = {
            r.operator: r.type
            for r in ShippingOperatorType.query.all()
        }
        # 所有出现过的操作人
        rows = db.session.query(ShippingRecord.operator).distinct().filter(
            ShippingRecord.operator.isnot(None),
            ShippingRecord.operator != '',
        ).all()
        operators = []
        for r in rows:
            op = r.operator.strip()
            if op:
                operators.append({
                    'operator': op,
                    'type':     classified.get(op, 'unknown'),
                })
        operators.sort(key=lambda x: x['operator'])
        return operators

    @staticmethod
    def classify_operators(items: List[Dict]) -> int:
        """批量 upsert 操作人分类，返回更新数量"""
        from database.models.shipping import now_cst
        count = 0
        for item in items:
            op   = (item.get('operator') or '').strip()
            type_ = item.get('type', 'unknown')
            if not op:
                continue
            existing = ShippingOperatorType.query.filter_by(operator=op).first()
            if existing:
                existing.type       = type_
                existing.updated_at = now_cst()
            else:
                db.session.add(ShippingOperatorType(operator=op, type=type_))
            count += 1
        db.session.commit()
        return count

    @staticmethod
    def get_shipping_operator_set() -> Set[str]:
        """返回所有 type='shipping' 的操作人集合"""
        rows = ShippingOperatorType.query.filter_by(type='shipping').all()
        return {r.operator for r in rows}

    # ── 成品组合 ─────────────────────────────────────

    @staticmethod
    def get_new_order_nos(batch_id: int) -> List[str]:
        """返回本批次新增的、且尚未写入 shipping_order_finished 的订单号"""
        # 本批次的订单号
        batch_orders = db.session.query(
            ShippingRecord.ecommerce_order_no
        ).filter(
            ShippingRecord.batch_id == batch_id,
            ShippingRecord.ecommerce_order_no.isnot(None),
        ).distinct().all()
        batch_order_set = {r.ecommerce_order_no for r in batch_orders}

        # 已有结果的订单号
        existing = db.session.query(
            ShippingOrderFinished.ecommerce_order_no
        ).filter(
            ShippingOrderFinished.ecommerce_order_no.in_(batch_order_set)
        ).distinct().all()
        existing_set = {r.ecommerce_order_no for r in existing}

        return [o for o in batch_order_set if o not in existing_set]

    @staticmethod
    def get_stale_order_nos() -> List[str]:
        """返回所有标记为 is_stale=True 的订单号"""
        rows = db.session.query(
            ShippingOrderFinished.ecommerce_order_no
        ).filter_by(is_stale=True).distinct().all()
        return [r.ecommerce_order_no for r in rows]

    @staticmethod
    def get_order_products(order_nos: List[str]) -> Dict[str, Dict]:
        """
        返回 {order_no: {'product_codes': {code: qty}, 'meta': {...}}}
        meta 取该订单第一行的 shipped_date/operator/channel_name/province
        """
        records = ShippingRecord.query.filter(
            ShippingRecord.ecommerce_order_no.in_(order_nos)
        ).all()
        result: Dict[str, Dict] = {}
        for r in records:
            on = r.ecommerce_order_no
            if on not in result:
                result[on] = {
                    'product_codes': {},
                    'meta': {
                        'shipped_date': r.shipped_date,
                        'operator':     r.operator,
                        'channel_name': r.channel_name,
                        'province':     r.province,
                    },
                }
            qty = float(r.quantity) if r.quantity else 0
            if r.product_code:
                result[on]['product_codes'][r.product_code] = (
                    result[on]['product_codes'].get(r.product_code, 0) + qty
                )
        return result

    @staticmethod
    def delete_order_finished(order_nos: List[str]):
        """删除这些订单的旧结果（刷新前清除）"""
        if order_nos:
            ShippingOrderFinished.query.filter(
                ShippingOrderFinished.ecommerce_order_no.in_(order_nos)
            ).delete(synchronize_session=False)

    @staticmethod
    def bulk_insert_order_finished(rows: List[Dict]):
        """批量写入组合结果"""
        objects = [
            ShippingOrderFinished(
                ecommerce_order_no = r['ecommerce_order_no'],
                finished_code      = r.get('finished_code'),
                finished_name      = r.get('finished_name'),
                quantity           = r.get('quantity'),
                shipped_date       = r.get('shipped_date'),
                operator           = r.get('operator'),
                channel_name       = r.get('channel_name'),
                province           = r.get('province'),
                is_stale           = False,
                resolved_at        = r.get('resolved_at'),
            )
            for r in rows
        ]
        if objects:
            db.session.bulk_save_objects(objects)
        db.session.commit()

    # ── 统计 ─────────────────────────────────────────

    @staticmethod
    def get_stats() -> Dict:
        total_records   = db.session.query(db.func.count(ShippingRecord.id)).scalar() or 0
        total_resolved  = db.session.query(db.func.count(ShippingOrderFinished.id)).scalar() or 0
        stale_count     = db.session.query(db.func.count(ShippingOrderFinished.id)).filter_by(is_stale=True).scalar() or 0
        latest_import       = db.session.query(db.func.max(ShippingBatch.imported_at)).scalar()
        last_shipped_date   = db.session.query(db.func.max(ShippingRecord.shipped_date)).scalar()
        return {
            'total_records':    total_records,
            'total_resolved':   total_resolved,
            'stale_count':      stale_count,
            'last_import':      latest_import.strftime('%Y-%m-%d') if latest_import else None,
            'last_shipped_date': last_shipped_date.strftime('%Y-%m-%d') if last_shipped_date else None,
        }

    @staticmethod
    def get_all_order_nos() -> List[str]:
        """返回 shipping_record 中所有不重复的订单号"""
        rows = db.session.query(ShippingRecord.ecommerce_order_no).filter(
            ShippingRecord.ecommerce_order_no.isnot(None)
        ).distinct().all()
        return [r.ecommerce_order_no for r in rows]

    @staticmethod
    def get_distinct_shipped_dates() -> List[str]:
        """返回所有已存在的 shipped_date（去重，升序）"""
        rows = db.session.query(ShippingRecord.shipped_date).filter(
            ShippingRecord.shipped_date.isnot(None)
        ).distinct().order_by(ShippingRecord.shipped_date).all()
        return [r.shipped_date.strftime('%Y-%m-%d') for r in rows]


shipping_repository = ShippingRepository()