from datetime import datetime
from decimal import Decimal
from typing import List, Dict, Set, Tuple
from database.base import db
from database.models.shipping import (
    ShippingBatch, ShippingRecord, ReturnRecord, ReturnWarehouseFilter,
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
        db.session.flush()
        return batch

    @staticmethod
    def delete_batch(batch_id: int):
        """回滚：删除批次及其关联记录（ShippingRecord / ReturnRecord 均通过 cascade 删除）"""
        db.session.query(ShippingRecord).filter_by(batch_id=batch_id).delete(synchronize_session=False)
        db.session.query(ReturnRecord).filter_by(batch_id=batch_id).delete(synchronize_session=False)
        db.session.query(ShippingBatch).filter_by(id=batch_id).delete(synchronize_session=False)
        db.session.commit()

    # ── 发货记录去重插入 ──────────────────────────────

    @staticmethod
    def get_existing_keys(keys: List[Tuple], record_type: str = None) -> Set[Tuple]:
        """
        给定 (ecommerce_order_no, line_no, product_code) 三元组列表，
        返回数据库中已存在的子集（Set of tuple）。
        record_type 不为 None 时只检查该类型的记录。
        """
        if not keys:
            return set()
        existing = set()
        CHUNK = 500
        for i in range(0, len(keys), CHUNK):
            chunk = keys[i:i + CHUNK]
            q = db.session.query(
                ShippingRecord.ecommerce_order_no,
                ShippingRecord.line_no,
                ShippingRecord.product_code,
            ).filter(
                db.tuple_(
                    ShippingRecord.ecommerce_order_no,
                    ShippingRecord.line_no,
                    ShippingRecord.product_code,
                ).in_(chunk)
            )
            if record_type is not None:
                q = q.filter(ShippingRecord.record_type == record_type)
            for r in q.all():
                existing.add((r.ecommerce_order_no, r.line_no, r.product_code))
        return existing

    @staticmethod
    def get_existing_order_nos(order_nos: List[str]) -> Set[str]:
        """给定订单号列表，返回已存在于 shipping_record 中的子集（用于销退匹配验证）"""
        if not order_nos:
            return set()
        existing = set()
        CHUNK = 500
        for i in range(0, len(order_nos), CHUNK):
            chunk = order_nos[i:i + CHUNK]
            rows = db.session.query(ShippingRecord.ecommerce_order_no).filter(
                ShippingRecord.ecommerce_order_no.in_(chunk)
            ).distinct().all()
            for r in rows:
                existing.add(r.ecommerce_order_no)
        return existing

    @staticmethod
    def bulk_insert_shipping(batch_id: int, rows: List[Dict],
                              progress_cb=None, record_type: str = 'shipping') -> int:
        """分块 INSERT IGNORE，已存在行静默跳过，返回实际新增行数"""
        if not rows:
            return 0
        from sqlalchemy import insert as sa_insert

        CHUNK = 100
        total = len(rows)

        def _make_param(row):
            return {
                'batch_id':           batch_id,
                'record_type':        record_type,
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

    # ── 销退记录 ─────────────────────────────────────

    @staticmethod
    def get_existing_return_keys(keys: List[Tuple]) -> Set[Tuple]:
        """
        给定 (ecommerce_order_no, product_code, shipped_date) 三元组列表，
        返回 return_record 中已存在的子集（用于去重）。
        """
        if not keys:
            return set()
        existing = set()
        CHUNK = 500
        for i in range(0, len(keys), CHUNK):
            chunk = keys[i:i + CHUNK]
            rows = db.session.query(
                ReturnRecord.ecommerce_order_no,
                ReturnRecord.product_code,
                ReturnRecord.shipped_date,
            ).filter(
                db.tuple_(
                    ReturnRecord.ecommerce_order_no,
                    ReturnRecord.product_code,
                    ReturnRecord.shipped_date,
                ).in_(chunk)
            ).all()
            for r in rows:
                existing.add((r.ecommerce_order_no, r.product_code, r.shipped_date))
        return existing

    @staticmethod
    def bulk_insert_return(batch_id: int, rows: List[Dict], progress_cb=None) -> int:
        """分块 INSERT IGNORE 写入 return_record，返回实际新增行数"""
        if not rows:
            return 0
        from sqlalchemy import insert as sa_insert

        CHUNK = 100
        total = len(rows)

        def _make_param(row):
            return {
                'batch_id':           batch_id,
                'ecommerce_order_no': row.get('ecommerce_order_no'),
                'shipped_date':       row.get('shipped_date'),
                'product_code':       row.get('product_code'),
                'quantity':           row.get('quantity'),
                'warehouse_name':     row.get('warehouse_name'),
            }

        stmt = sa_insert(ReturnRecord).prefix_with('IGNORE')
        for i in range(0, total, CHUNK):
            chunk = rows[i:i + CHUNK]
            db.session.execute(stmt, [_make_param(r) for r in chunk])
            db.session.commit()
            if progress_cb:
                progress_cb(min(i + len(chunk), total), total)

        return total

    @staticmethod
    def get_order_return_products(order_nos: List[str]) -> Dict[str, Dict[str, float]]:
        """
        返回 {order_no: {product_code: abs_return_qty}}
        数量取绝对值，方便成品组合匹配时直接用正数运算。
        计算时动态排除 is_excluded=True 的仓库，不影响 return_record 原始数据。
        """
        if not order_nos:
            return {}
        excluded_warehouses = ShippingRepository.get_excluded_warehouse_set()
        q = ReturnRecord.query.filter(
            ReturnRecord.ecommerce_order_no.in_(order_nos)
        )
        if excluded_warehouses:
            q = q.filter(
                db.or_(
                    ReturnRecord.warehouse_name.is_(None),
                    ReturnRecord.warehouse_name == '',
                    ~ReturnRecord.warehouse_name.in_(excluded_warehouses),
                )
            )
        records = q.all()
        result: Dict[str, Dict[str, float]] = {}
        for r in records:
            on = r.ecommerce_order_no
            if on not in result:
                result[on] = {}
            qty = abs(float(r.quantity)) if r.quantity else 0
            if r.product_code and qty > 0:
                result[on][r.product_code] = result[on].get(r.product_code, 0) + qty
        return result

    @staticmethod
    def get_return_affected_order_nos(batch_id: int) -> List[str]:
        """返回销退批次中涉及的所有订单号"""
        rows = db.session.query(ReturnRecord.ecommerce_order_no).filter(
            ReturnRecord.batch_id == batch_id,
            ReturnRecord.ecommerce_order_no.isnot(None),
        ).distinct().all()
        return [r.ecommerce_order_no for r in rows]

    # ── 仓库过滤配置 ──────────────────────────────────

    @staticmethod
    def get_all_warehouses() -> List[Dict]:
        """从 return_record 收集所有出现过的仓库名，与 return_warehouse_filter 合并返回"""
        configured = {
            r.warehouse_name: r.is_excluded
            for r in ReturnWarehouseFilter.query.all()
        }
        rows = db.session.query(ReturnRecord.warehouse_name).filter(
            ReturnRecord.warehouse_name.isnot(None),
            ReturnRecord.warehouse_name != '',
        ).distinct().all()
        warehouses = []
        for r in rows:
            name = r.warehouse_name.strip()
            if name:
                warehouses.append({
                    'warehouse_name': name,
                    'is_excluded':    configured.get(name, False),
                })
        warehouses.sort(key=lambda x: x['warehouse_name'])
        return warehouses

    @staticmethod
    def save_warehouse_filters(items: List[Dict]) -> int:
        """批量 upsert 仓库过滤配置，返回更新数量"""
        from database.models.shipping import now_cst
        count = 0
        for item in items:
            name = (item.get('warehouse_name') or '').strip()
            if not name:
                continue
            is_excluded = bool(item.get('is_excluded', False))
            existing = ReturnWarehouseFilter.query.filter_by(warehouse_name=name).first()
            if existing:
                existing.is_excluded = is_excluded
            else:
                db.session.add(ReturnWarehouseFilter(
                    warehouse_name = name,
                    is_excluded    = is_excluded,
                    created_at     = now_cst(),
                ))
            count += 1
        db.session.commit()
        return count

    @staticmethod
    def get_excluded_warehouse_set() -> Set[str]:
        """返回所有 is_excluded=True 的仓库名集合"""
        rows = ReturnWarehouseFilter.query.filter_by(is_excluded=True).all()
        return {r.warehouse_name for r in rows}

    # ── 操作人 ───────────────────────────────────────

    @staticmethod
    def get_all_operators() -> List[Dict]:
        """从 shipping_record 中收集所有不重复操作人，与 shipping_operator_type 合并返回"""
        classified = {
            r.operator: r.type
            for r in ShippingOperatorType.query.all()
        }
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
            op    = (item.get('operator') or '').strip()
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
        batch_orders = db.session.query(
            ShippingRecord.ecommerce_order_no
        ).filter(
            ShippingRecord.batch_id == batch_id,
            ShippingRecord.ecommerce_order_no.isnot(None),
        ).distinct().all()
        batch_order_set = {r.ecommerce_order_no for r in batch_orders}

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
            ShippingRecord.ecommerce_order_no.in_(order_nos),
            ShippingRecord.record_type == 'shipping',
        ).all()
        result: Dict[str, Dict] = {}
        for r in records:
            on = r.ecommerce_order_no
            if on not in result:
                result[on] = {
                    'product_codes': {},
                    'meta': {
                        'shipped_date':     r.shipped_date,
                        'operator':         r.operator,
                        'channel_name':     r.channel_name,
                        'channel_code':     r.channel_code,
                        'channel_org_name': r.channel_org_name,
                        'province':         r.province,
                        'city':             r.city,
                        'district':         r.district,
                    },
                }
            qty = float(r.quantity) if r.quantity else 0
            if r.product_code and qty > 0:
                result[on]['product_codes'][r.product_code] = (
                    result[on]['product_codes'].get(r.product_code, 0) + qty
                )
        return result

    @staticmethod
    def delete_order_finished(order_nos: List[str]):
        """删除这些订单的旧结果（刷新前清除），立即 commit 释放锁"""
        if order_nos:
            # 分批删除，避免 IN 子句过大
            chunk_size = 500
            for i in range(0, len(order_nos), chunk_size):
                chunk = order_nos[i:i + chunk_size]
                ShippingOrderFinished.query.filter(
                    ShippingOrderFinished.ecommerce_order_no.in_(chunk)
                ).delete(synchronize_session=False)
                db.session.commit()

    @staticmethod
    def bulk_insert_order_finished(rows: List[Dict]):
        """批量写入组合结果，分块 commit 避免大事务持锁超时"""
        chunk_size = 200
        for i in range(0, len(rows), chunk_size):
            chunk = rows[i:i + chunk_size]
            objects = [
                ShippingOrderFinished(
                    ecommerce_order_no = r['ecommerce_order_no'],
                    finished_code      = r.get('finished_code'),
                    finished_name      = r.get('finished_name'),
                    quantity           = r.get('quantity'),
                    return_quantity    = r.get('return_quantity', 0),
                    actual_quantity    = r.get('actual_quantity'),
                    shipped_date       = r.get('shipped_date'),
                    operator           = r.get('operator'),
                    channel_name       = r.get('channel_name'),
                    channel_code       = r.get('channel_code'),
                    channel_org_name   = r.get('channel_org_name'),
                    province           = r.get('province'),
                    city               = r.get('city'),
                    district           = r.get('district'),
                    is_stale           = False,
                    resolved_at        = r.get('resolved_at'),
                )
                for r in chunk
            ]
            db.session.bulk_save_objects(objects)
            db.session.commit()

    # ── 统计 ─────────────────────────────────────────

    @staticmethod
    def get_stats() -> Dict:
        total_records   = db.session.query(db.func.count(ShippingRecord.id)).scalar() or 0
        total_resolved  = db.session.query(db.func.count(ShippingOrderFinished.id)).scalar() or 0
        stale_count     = db.session.query(db.func.count(ShippingOrderFinished.id)).filter_by(is_stale=True).scalar() or 0
        latest_import     = db.session.query(db.func.max(ShippingBatch.imported_at)).scalar()
        last_shipped_date = db.session.query(db.func.max(ShippingRecord.shipped_date)).filter(
            ShippingRecord.record_type == 'shipping'
        ).scalar()
        last_return_date  = db.session.query(db.func.max(ReturnRecord.shipped_date)).scalar()
        return {
            'total_records':     total_records,
            'total_resolved':    total_resolved,
            'stale_count':       stale_count,
            'last_import':       latest_import.strftime('%Y-%m-%d') if latest_import else None,
            'last_shipped_date': last_shipped_date.strftime('%Y-%m-%d') if last_shipped_date else None,
            'last_return_date':  last_return_date.strftime('%Y-%m-%d') if last_return_date else None,
        }

    @staticmethod
    def get_all_order_nos() -> List[str]:
        """返回 shipping_record 中所有不重复的订单号（仅发货记录）"""
        rows = db.session.query(ShippingRecord.ecommerce_order_no).filter(
            ShippingRecord.ecommerce_order_no.isnot(None),
            ShippingRecord.record_type == 'shipping',
        ).distinct().all()
        return [r.ecommerce_order_no for r in rows]

    @staticmethod
    def get_distinct_shipped_dates() -> List[str]:
        """返回所有发货记录的 shipped_date（去重，升序），不含销退记录"""
        rows = db.session.query(ShippingRecord.shipped_date).filter(
            ShippingRecord.shipped_date.isnot(None),
            ShippingRecord.record_type == 'shipping',
        ).distinct().order_by(ShippingRecord.shipped_date).all()
        return [r.shipped_date.strftime('%Y-%m-%d') for r in rows]


    # ── 图表数据 ─────────────────────────────────────

    @staticmethod
    def get_chart_options(date_start=None, date_end=None) -> Dict:
        """返回渠道层级、省份层级、active产品ID，均按日期范围过滤"""
        from database.models.product.category import ProductCategory, ProductSeries, ProductModel
        from database.models.product.finished import ProductFinished
        from sqlalchemy import collate as sa_collate
        from datetime import datetime as _dt

        sof = ShippingOrderFinished

        def _date_filter(q):
            if date_start:
                try:
                    q = q.filter(sof.shipped_date >= _dt.strptime(date_start, '%Y-%m-%d').date())
                except ValueError:
                    pass
            if date_end:
                try:
                    q = q.filter(sof.shipped_date <= _dt.strptime(date_end, '%Y-%m-%d').date())
                except ValueError:
                    pass
            return q

        # 售后操作人子查询（排除 type='aftersale' 的操作人对应记录）
        aftersale_ops = db.session.query(ShippingOperatorType.operator).filter_by(type='aftersale').subquery()
        base_filter = [
            sof.finished_code.isnot(None),
            db.or_(sof.operator.is_(None), ~sof.operator.in_(aftersale_ops)),
        ]

        # 渠道：channel_name → [{code, org_name}] 层级结构
        ch_q = db.session.query(
            sof.channel_name, sof.channel_code, sof.channel_org_name
        ).filter(*base_filter, sof.channel_name.isnot(None), sof.channel_name != '')
        ch_rows = _date_filter(ch_q).distinct().order_by(sof.channel_name, sof.channel_code).all()

        channels_map: Dict = {}
        for r in ch_rows:
            name = r.channel_name
            if name not in channels_map:
                channels_map[name] = []
            if r.channel_code:
                channels_map[name].append({
                    'code':     r.channel_code,
                    'org_name': r.channel_org_name or r.channel_code,
                })
        channels = [{'name': k, 'orgs': v} for k, v in channels_map.items()]

        # 省份层级：province → city → district
        prov_q = db.session.query(
            sof.province, sof.city, sof.district
        ).filter(*base_filter, sof.province.isnot(None), sof.province != '')
        prov_rows = _date_filter(prov_q).distinct().order_by(sof.province, sof.city, sof.district).all()

        provinces_map: Dict = {}
        for r in prov_rows:
            pname = r.province
            if pname not in provinces_map:
                provinces_map[pname] = {}
            if r.city:
                cname = r.city
                if cname not in provinces_map[pname]:
                    provinces_map[pname][cname] = []
                if r.district:
                    provinces_map[pname][cname].append(r.district)
        provinces = [
            {'name': pname, 'cities': [{'name': cname, 'districts': dists} for cname, dists in cities.items()]}
            for pname, cities in provinces_map.items()
        ]

        # 活跃产品 ID（日期范围内有发货数据的品类/系列/型号）
        prod_q = db.session.query(
            ProductCategory.id.label('cat_id'),
            ProductSeries.id.label('ser_id'),
            ProductModel.id.label('mod_id'),
        ).select_from(sof).join(
            ProductFinished,
            sa_collate(sof.finished_code, 'utf8mb4_unicode_ci') ==
            sa_collate(ProductFinished.code, 'utf8mb4_unicode_ci')
        ).join(ProductModel,    ProductFinished.model_id    == ProductModel.id
        ).join(ProductSeries,   ProductModel.series_id      == ProductSeries.id
        ).join(ProductCategory, ProductSeries.category_id   == ProductCategory.id
        ).filter(*base_filter)
        prod_rows = _date_filter(prod_q).distinct().all()

        return {
            'channels':            channels,
            'provinces':           provinces,
            'active_category_ids': list({r.cat_id for r in prod_rows}),
            'active_series_ids':   list({r.ser_id for r in prod_rows}),
            'active_model_ids':    list({r.mod_id for r in prod_rows}),
        }

    @staticmethod
    def get_chart_data(params: Dict) -> Dict:
        """
        按过滤条件聚合 shipping_order_finished，返回 summary + 分组明细。
        params keys: group_by, date_start, date_end, channel_names, provinces,
                     category_id, series_id, model_id
        """
        from database.models.product.category import ProductCategory, ProductSeries, ProductModel
        from database.models.product.finished import ProductFinished
        from sqlalchemy import func, collate as sa_collate

        sof = ShippingOrderFinished
        group_by      = params.get('group_by', 'date')
        date_start    = params.get('date_start')
        date_end      = params.get('date_end')
        channel_names = params.get('channel_names') or []
        channel_codes = params.get('channel_codes') or []
        provinces     = params.get('provinces') or []
        cities        = params.get('cities') or []
        districts     = params.get('districts') or []
        category_ids  = params.get('category_ids') or []
        series_ids    = params.get('series_ids') or []
        model_ids     = params.get('model_ids') or []

        def _f(v):
            return float(v) if v is not None else 0.0

        # 根据 group_by 判断需要 JOIN 到哪一层产品表
        product_group_by  = group_by in ('category', 'series', 'model')
        needs_model_join  = product_group_by or bool(category_ids or series_ids or model_ids)
        needs_series_join = group_by in ('category', 'series') or bool(category_ids or series_ids)
        needs_cat_join    = group_by == 'category' or bool(category_ids)

        # 售后操作人子查询（在整个 get_chart_data 调用中复用）
        aftersale_ops_sub = db.session.query(ShippingOperatorType.operator).filter_by(type='aftersale').subquery()

        def _apply_filters(q):
            """将所有过滤条件应用到查询对象，返回新查询"""
            q = q.filter(
                sof.finished_code.isnot(None),
                db.or_(sof.operator.is_(None), ~sof.operator.in_(aftersale_ops_sub)),
            )
            if needs_model_join:
                q = q.join(ProductFinished,
                           sa_collate(sof.finished_code, 'utf8mb4_unicode_ci') ==
                           sa_collate(ProductFinished.code, 'utf8mb4_unicode_ci'))
                q = q.join(ProductModel, ProductFinished.model_id == ProductModel.id)
            if needs_series_join:
                q = q.join(ProductSeries, ProductModel.series_id == ProductSeries.id)
            if needs_cat_join:
                q = q.join(ProductCategory, ProductSeries.category_id == ProductCategory.id)
            # 应用产品过滤
            if model_ids:
                q = q.filter(ProductModel.id.in_(model_ids))
            if series_ids:
                q = q.filter(ProductSeries.id.in_(series_ids))
            if category_ids:
                q = q.filter(ProductCategory.id.in_(category_ids))
            # 日期过滤
            if date_start:
                try:
                    from datetime import datetime as _dt
                    q = q.filter(sof.shipped_date >= _dt.strptime(date_start, '%Y-%m-%d').date())
                except ValueError:
                    pass
            if date_end:
                try:
                    from datetime import datetime as _dt
                    q = q.filter(sof.shipped_date <= _dt.strptime(date_end, '%Y-%m-%d').date())
                except ValueError:
                    pass
            if channel_names:
                q = q.filter(sof.channel_name.in_(channel_names))
            if channel_codes:
                q = q.filter(sof.channel_code.in_(channel_codes))
            if provinces:
                q = q.filter(sof.province.in_(provinces))
            if cities:
                q = q.filter(sof.city.in_(cities))
            if districts:
                q = q.filter(sof.district.in_(districts))
            return q

        # ── 分组维度 label 表达式 ─────────────────────────────
        if group_by == 'date':
            period = params.get('period', 'month')
            if period == 'year':
                label_expr = func.date_format(sof.shipped_date, '%Y')
            elif period == 'quarter':
                # 格式：'2024-Q1' / '2024-Q2' ...
                label_expr = func.concat(
                    func.year(sof.shipped_date), '-Q', func.quarter(sof.shipped_date)
                )
            elif period == 'halfyear':
                # 格式：'2024-H1' / '2024-H2'
                from sqlalchemy import case as sa_case
                half_suffix = sa_case(
                    (func.month(sof.shipped_date) <= 6, '-H1'),
                    else_='-H2',
                )
                label_expr = func.concat(func.year(sof.shipped_date), half_suffix)
            else:  # month（默认）
                label_expr = func.date_format(sof.shipped_date, '%Y-%m')
            name_expr  = None
            order_expr = label_expr.asc()
        elif group_by == 'category':
            label_expr = func.coalesce(ProductCategory.name, '未知')
            name_expr  = None
            order_expr = func.sum(sof.actual_quantity).desc()
        elif group_by == 'series':
            label_expr = func.coalesce(ProductSeries.code, '未知')
            name_expr  = func.max(ProductSeries.name)
            order_expr = func.sum(sof.actual_quantity).desc()
        elif group_by == 'model':
            label_expr = func.coalesce(ProductModel.code, '未知')
            name_expr  = func.max(ProductModel.name)
            order_expr = func.sum(sof.actual_quantity).desc()
        elif group_by == 'channel':
            label_expr = func.coalesce(sof.channel_name, '未知')
            name_expr  = None
            order_expr = func.sum(sof.actual_quantity).desc()
        elif group_by == 'channel_code':
            label_expr = func.coalesce(sof.channel_code, '未知')
            name_expr  = None
            order_expr = func.sum(sof.actual_quantity).desc()
        elif group_by == 'province':
            label_expr = func.coalesce(sof.province, '未知')
            name_expr  = None
            order_expr = func.sum(sof.actual_quantity).desc()
        elif group_by == 'city':
            label_expr = func.coalesce(sof.city, '未知')
            name_expr  = None
            order_expr = func.sum(sof.actual_quantity).desc()
        elif group_by == 'district':
            label_expr = func.coalesce(sof.district, '未知')
            name_expr  = None
            order_expr = func.sum(sof.actual_quantity).desc()
        else:
            label_expr = func.coalesce(sof.finished_name, sof.finished_code, '未匹配')
            name_expr  = None
            order_expr = func.sum(sof.actual_quantity).desc()

        select_cols = [
            label_expr.label('label'),
            func.sum(sof.quantity).label('quantity'),
            func.sum(sof.return_quantity).label('return_quantity'),
            func.sum(sof.actual_quantity).label('actual_quantity'),
        ]
        if name_expr is not None:
            select_cols.append(name_expr.label('name'))

        grouped_q = db.session.query(*select_cols)
        grouped_q = _apply_filters(grouped_q)
        grouped_q = grouped_q.group_by(label_expr).order_by(order_expr)
        rows = grouped_q.all()

        has_name = name_expr is not None
        items = [
            {
                'label':           r.label,
                'quantity':        _f(r.quantity),
                'return_quantity': _f(r.return_quantity),
                'actual_quantity': _f(r.actual_quantity),
                **(({'name': r.name}) if has_name else {}),
            }
            for r in rows
        ]

        # ── 汇总查询（同等过滤，不分组）────────────────────────
        summary_q = db.session.query(
            func.sum(sof.quantity).label('quantity'),
            func.sum(sof.return_quantity).label('return_quantity'),
            func.sum(sof.actual_quantity).label('actual_quantity'),
        )
        summary_q = _apply_filters(summary_q)
        sr = summary_q.one()

        return {
            'summary': {
                'quantity':        _f(sr.quantity),
                'return_quantity': _f(sr.return_quantity),
                'actual_quantity': _f(sr.actual_quantity),
            },
            'items': items,
        }


    @staticmethod
    def get_orders(page: int, size: int, filters: Dict, sort_field: str, sort_order: str) -> Dict:
        """分页查询 shipping_order_finished（仅含已匹配成品），LEFT JOIN 产品表取系列/型号"""
        from datetime import datetime as _dt
        from database.models.product.category import ProductSeries, ProductModel
        from database.models.product.finished import ProductFinished
        from sqlalchemy import collate as sa_collate

        sof = ShippingOrderFinished

        # 始终过滤掉未匹配记录，LEFT JOIN 获取品类/系列/型号信息
        from database.models.product.category import ProductCategory
        q = db.session.query(
            sof,
            ProductModel.code.label('model_code'),
            ProductSeries.code.label('series_code'),
            ProductCategory.name.label('category_name'),
        ).outerjoin(
            ProductFinished,
            sa_collate(sof.finished_code, 'utf8mb4_unicode_ci') ==
            sa_collate(ProductFinished.code, 'utf8mb4_unicode_ci'),
        ).outerjoin(
            ProductModel, ProductFinished.model_id == ProductModel.id,
        ).outerjoin(
            ProductSeries, ProductModel.series_id == ProductSeries.id,
        ).outerjoin(
            ProductCategory, ProductSeries.category_id == ProductCategory.id,
        ).filter(
            sof.finished_code.isnot(None)
        )

        # 文本模糊筛选
        if filters.get('ecommerce_order_no'):
            q = q.filter(sof.ecommerce_order_no.like(f"%{filters['ecommerce_order_no']}%"))
        if filters.get('finished_code'):
            q = q.filter(sof.finished_code.like(f"%{filters['finished_code']}%"))
        if filters.get('finished_name'):
            q = q.filter(sof.finished_name.like(f"%{filters['finished_name']}%"))
        if filters.get('category_name'):
            q = q.filter(ProductCategory.name.like(f"%{filters['category_name']}%"))
        if filters.get('series_code'):
            q = q.filter(ProductSeries.code.like(f"%{filters['series_code']}%"))
        if filters.get('model_code'):
            q = q.filter(ProductModel.code.like(f"%{filters['model_code']}%"))
        if filters.get('channel_name'):
            q = q.filter(sof.channel_name.like(f"%{filters['channel_name']}%"))
        if filters.get('channel_code'):
            q = q.filter(sof.channel_code.like(f"%{filters['channel_code']}%"))
        if filters.get('channel_org_name'):
            q = q.filter(sof.channel_org_name.like(f"%{filters['channel_org_name']}%"))
        if filters.get('province'):
            q = q.filter(sof.province.like(f"%{filters['province']}%"))
        if filters.get('city'):
            q = q.filter(sof.city.like(f"%{filters['city']}%"))
        if filters.get('district'):
            q = q.filter(sof.district.like(f"%{filters['district']}%"))

        # 日期范围筛选
        if filters.get('date_start'):
            try:
                q = q.filter(sof.shipped_date >= _dt.strptime(filters['date_start'], '%Y-%m-%d').date())
            except ValueError:
                pass
        if filters.get('date_end'):
            try:
                q = q.filter(sof.shipped_date <= _dt.strptime(filters['date_end'], '%Y-%m-%d').date())
            except ValueError:
                pass

        # 排序（joined 列需单独处理）
        sort_col_map = {
            'shipped_date':       sof.shipped_date,
            'quantity':           sof.quantity,
            'return_quantity':    sof.return_quantity,
            'actual_quantity':    sof.actual_quantity,
            'finished_code':      sof.finished_code,
            'ecommerce_order_no': sof.ecommerce_order_no,
            'model_code':         ProductModel.code,
            'series_code':        ProductSeries.code,
        }
        col = sort_col_map.get(sort_field, sof.shipped_date)
        q = q.order_by(col.asc() if sort_order == 'asc' else col.desc())

        total = q.count()
        rows  = q.offset((page - 1) * size).limit(size).all()

        items = []
        for row in rows:
            d = row.ShippingOrderFinished.to_dict()
            d['model_code']    = row.model_code
            d['series_code']   = row.series_code
            d['category_name'] = row.category_name
            items.append(d)

        return {'items': items, 'total': total}

    @staticmethod
    def get_product_monthly(code: str) -> list:
        """按月聚合指定成品的发货/销退/实际数量，从最早记录月到最新月（排除售后操作人）"""
        from sqlalchemy import func
        sof = ShippingOrderFinished
        aftersale_ops = db.session.query(ShippingOperatorType.operator).filter_by(type='aftersale').subquery()
        rows = (
            db.session.query(
                func.date_format(sof.shipped_date, '%Y-%m').label('month'),
                func.sum(sof.quantity).label('shipped'),
                func.sum(sof.return_quantity).label('returned'),
                func.sum(sof.actual_quantity).label('actual'),
            )
            .filter(
                sof.finished_code == code,
                sof.shipped_date.isnot(None),
                db.or_(sof.operator.is_(None), ~sof.operator.in_(aftersale_ops)),
            )
            .group_by('month')
            .order_by('month')
            .all()
        )

        def _f(v):
            return float(v) if v is not None else 0.0

        return [
            {
                'month':    r.month,
                'shipped':  _f(r.shipped),
                'returned': _f(r.returned),
                'actual':   _f(r.actual),
            }
            for r in rows
        ]


shipping_repository = ShippingRepository()
