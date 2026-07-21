import time
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Dict, Set, Tuple
from database.base import db
from database.models.shipping import (
    ShippingBatch, ShippingRecord, ReturnRecord, ReturnWarehouseFilter,
    ShippingOperatorType, ShippingOrderFinished, ShippingTask,
    ShippingFinanceCustomerMapping,
)
from utils import now_cst

# ── FTP finished_code 缓存（避免 trade_type 过滤时反复 JOIN 产品表）──
_ftp_codes_cache: set = set()
_ftp_codes_cache_at: float = 0.0
_FTP_CACHE_TTL = 300  # 5 分钟


def _get_ftp_finished_codes() -> set:
    """返回所有属于 FTP 系列（code LIKE '%-FTP'）的 finished_code 集合，带缓存。"""
    global _ftp_codes_cache, _ftp_codes_cache_at
    if time.time() - _ftp_codes_cache_at < _FTP_CACHE_TTL:
        return _ftp_codes_cache
    from database.models.product.category import ProductSeries, ProductModel
    from database.models.product.finished import ProductFinished
    rows = db.session.query(ProductFinished.code).join(
        ProductModel,  ProductFinished.model_id  == ProductModel.id
    ).join(
        ProductSeries, ProductModel.series_id == ProductSeries.id
    ).filter(ProductSeries.code.like('%-FTP')).all()
    _ftp_codes_cache    = {r[0] for r in rows}
    _ftp_codes_cache_at = time.time()
    return _ftp_codes_cache


# ── chart_options 缓存（渠道/省份/活跃产品，仅导入新数据时才变）──
_chart_options_cache: dict = {}
_CHART_OPTIONS_TTL = 300  # 5 分钟


def _invalidate_chart_options_cache():
    """导入新数据后调用，清空 chart_options 缓存。"""
    _chart_options_cache.clear()


class ShippingRepository:

    # ── 持久化后台任务（独立事务，不得提交导入业务 session）──

    @staticmethod
    def get_finance_customer_aliases(keyword=None, page=1, per_page=100) -> Dict:
        """合并发货/销退客户简称计数，并一次性关联人工映射，避免 N+1。"""
        def counts_for(model):
            # shipping_record 表整体排序规则是 utf8mb4_unicode_ci，return_record 是
            # utf8mb4_0900_ai_ci（历史遗留，两表建表时字符集默认值不同），
            # customer_alias 列各自继承所在表的排序规则，UNION ALL 时 MySQL 直接报
            # "Illegal mix of collations"，必须显式统一。
            query = db.session.query(
                model.customer_alias.collate('utf8mb4_unicode_ci').label('customer_alias'),
                db.func.count(model.id).label('occurrences'),
            ).filter(
                model.customer_alias.isnot(None),
                model.customer_alias != '',
            )
            if model is ShippingRecord:
                query = query.filter(ShippingRecord.source == 'finance')
            if keyword:
                query = query.filter(model.customer_alias.contains(keyword, autoescape=True))
            return query.group_by(model.customer_alias)

        combined = counts_for(ShippingRecord).union_all(counts_for(ReturnRecord)).subquery()
        totals = db.session.query(
            combined.c.customer_alias,
            db.func.sum(combined.c.occurrences).label('occurrences'),
        ).group_by(combined.c.customer_alias).subquery()
        query = db.session.query(
            totals.c.customer_alias,
            totals.c.occurrences,
            ShippingFinanceCustomerMapping,
        ).outerjoin(
            ShippingFinanceCustomerMapping,
            ShippingFinanceCustomerMapping.customer_alias.collate('utf8mb4_unicode_ci') == totals.c.customer_alias,
        ).order_by(totals.c.occurrences.desc(), totals.c.customer_alias.asc())

        total = query.count()
        rows = query.offset((page - 1) * per_page).limit(per_page).all()
        return {
            'items': [
                {
                    'customer_alias': customer_alias,
                    'occurrences': int(occurrences),
                    'mapping': mapping.to_dict() if mapping else None,
                }
                for customer_alias, occurrences, mapping in rows
            ],
            'page': page,
            'per_page': per_page,
            'total': total,
        }

    @staticmethod
    def save_finance_customer_mapping(customer_alias, is_export, country=None,
                                      brand=None, note=None) -> Dict:
        mapping = ShippingFinanceCustomerMapping.query.filter_by(
            customer_alias=customer_alias,
        ).first()
        if mapping is None:
            mapping = ShippingFinanceCustomerMapping(customer_alias=customer_alias)
            db.session.add(mapping)
        mapping.is_export = is_export
        mapping.country = country
        mapping.brand = brand
        mapping.note = note
        mapping.updated_at = now_cst()
        db.session.commit()
        return mapping.to_dict()

    @staticmethod
    def create_task(task_id: str, task_type: str, filename: str = None):
        now = now_cst()
        with db.engine.begin() as connection:
            connection.execute(
                db.delete(ShippingTask).where(
                    ShippingTask.finished_at < now - timedelta(days=7)
                )
            )
            connection.execute(db.insert(ShippingTask).values(
                id=task_id,
                task_type=task_type,
                status='pending',
                filename=filename,
                progress={},
                created_at=now,
                updated_at=now,
            ))

    @staticmethod
    def update_task(task_id: str, *, status=None, progress=None, result=None, message=None):
        values = {'updated_at': now_cst()}
        if status is not None:
            values['status'] = status
        if progress is not None:
            values['progress'] = progress
        if result is not None:
            values['result'] = result
        if message is not None:
            values['message'] = message
        if status in ('done', 'error', 'cancelled', 'interrupted'):
            values['finished_at'] = values['updated_at']
        with db.engine.begin() as connection:
            connection.execute(
                db.update(ShippingTask)
                .where(ShippingTask.id == task_id)
                .values(**values)
            )

    @staticmethod
    def get_task(task_id: str):
        # SSE 轮询必须每次开启新事务，否则 MySQL REPEATABLE READ 会看不到终态。
        db.session.remove()
        task = db.session.get(ShippingTask, task_id)
        if task is not None:
            db.session.expunge(task)
        db.session.remove()
        return task

    @staticmethod
    def interrupt_running_tasks():
        """新 worker 启动时，将上一进程未完成的任务标记为已中断。"""
        now = now_cst()
        with db.engine.begin() as connection:
            result = connection.execute(
                db.update(ShippingTask)
                .where(ShippingTask.status.in_(('pending', 'running')))
                .values(
                    status='interrupted',
                    message='任务因服务重启或重载中断；导入业务数据已由事务回滚',
                    updated_at=now,
                    finished_at=now,
                )
            )
        return result.rowcount

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
    def get_existing_finance_keys(keys: List[Tuple]) -> Set[Tuple]:
        """
        给定 (ecommerce_order_no, product_code, shipped_date) 三元组列表，
        返回 shipping_record 中已存在的财务端记录子集（用于财务导入去重）。
        """
        if not keys:
            return set()
        existing = set()
        CHUNK = 500
        for i in range(0, len(keys), CHUNK):
            chunk = keys[i:i + CHUNK]
            rows = db.session.query(
                ShippingRecord.ecommerce_order_no,
                ShippingRecord.product_code,
                ShippingRecord.shipped_date,
            ).filter(
                db.tuple_(
                    ShippingRecord.ecommerce_order_no,
                    ShippingRecord.product_code,
                    ShippingRecord.shipped_date,
                ).in_(chunk),
                ShippingRecord.source == 'finance',
            ).all()
            for r in rows:
                existing.add((r.ecommerce_order_no, r.product_code, r.shipped_date))
        return existing

    @staticmethod
    def bulk_insert_shipping(batch_id: int, rows: List[Dict],
                              progress_cb=None, record_type: str = 'shipping',
                              source: str = 'shipping', commit_chunks: bool = True) -> int:
        """分块 UPSERT；重复键更新可更正字段，返回处理行数。"""
        if not rows:
            return 0
        from sqlalchemy import func, bindparam
        from sqlalchemy.dialects.mysql import insert as mysql_insert

        CHUNK = 100
        total = len(rows)

        _COLUMNS = (
            'batch_id', 'record_type', 'source', 'ecommerce_order_no', 'line_no',
            'shipped_date', 'channel_name', 'channel_code', 'channel_org_name',
            'operator', 'product_code', 'product_name', 'spec', 'quantity',
            'country', 'province', 'city', 'district', 'street', 'address',
            'buyer_remark', 'seller_remark', 'customer_alias',
        )

        def _make_param(row):
            return {
                'batch_id':           batch_id,
                'record_type':        record_type,
                'source':             source,
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
                'customer_alias':     row.get('customer_alias'),
            }

        # mysql_insert(Model) 不带 .values() 时，SQLAlchemy 会按 executemany 第一行参数里
        # "非 None" 的键动态推导 INSERT 列表，同一批次首行若某列恰好是 None 就会被整体漏掉；
        # 但 on_duplicate_key_update 里 stmt.inserted.<col> 引用的列是固定的，
        # 漏掉的列在 MySQL 端就会报 "Unknown column 'new.<col>'"。显式 .values() +
        # bindparam 强制列集合固定，不再随首行数据内容变化。
        stmt = mysql_insert(ShippingRecord).values({c: bindparam(c) for c in _COLUMNS})
        stmt = stmt.on_duplicate_key_update(
            shipped_date=stmt.inserted.shipped_date,
            channel_name=stmt.inserted.channel_name,
            product_name=stmt.inserted.product_name,
            spec=stmt.inserted.spec,
            quantity=stmt.inserted.quantity,
            province=stmt.inserted.province,
            city=stmt.inserted.city,
            district=stmt.inserted.district,
            customer_alias=func.coalesce(
                stmt.inserted.customer_alias, ShippingRecord.customer_alias,
            ),
        )
        for i in range(0, total, CHUNK):
            chunk = rows[i:i + CHUNK]
            db.session.execute(stmt, [_make_param(r) for r in chunk])
            if commit_chunks:
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
    def bulk_insert_return(batch_id: int, rows: List[Dict], progress_cb=None,
                           commit_chunks: bool = True) -> int:
        """分块 UPSERT 写入 return_record，返回处理行数。"""
        if not rows:
            return 0
        from sqlalchemy import func, bindparam
        from sqlalchemy.dialects.mysql import insert as mysql_insert

        CHUNK = 100
        total = len(rows)

        _COLUMNS = (
            'batch_id', 'ecommerce_order_no', 'shipped_date', 'product_code',
            'quantity', 'warehouse_name', 'customer_alias',
        )

        def _make_param(row):
            return {
                'batch_id':           batch_id,
                'ecommerce_order_no': row.get('ecommerce_order_no'),
                'shipped_date':       row.get('shipped_date'),
                'product_code':       row.get('product_code'),
                'quantity':           row.get('quantity'),
                'warehouse_name':     row.get('warehouse_name'),
                'customer_alias':     row.get('customer_alias'),
            }

        # 同 bulk_insert_shipping：显式 .values() + bindparam 固定 INSERT 列集合，
        # 避免首行某列为 None 时被 SQLAlchemy 自动推导逻辑漏掉，导致
        # ON DUPLICATE KEY UPDATE 里 "Unknown column 'new.<col>'"。
        stmt = mysql_insert(ReturnRecord).values({c: bindparam(c) for c in _COLUMNS})
        stmt = stmt.on_duplicate_key_update(
            quantity=stmt.inserted.quantity,
            warehouse_name=stmt.inserted.warehouse_name,
            customer_alias=func.coalesce(
                stmt.inserted.customer_alias, ReturnRecord.customer_alias,
            ),
        )
        for i in range(0, total, CHUNK):
            chunk = rows[i:i + CHUNK]
            db.session.execute(stmt, [_make_param(r) for r in chunk])
            if commit_chunks:
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
    def get_new_order_nos_by_source(batch_id: int, source: str) -> List[str]:
        """返回本批次新增的、且该 source 下尚未写入 shipping_order_finished 的订单号"""
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
            ShippingOrderFinished.ecommerce_order_no.in_(batch_order_set),
            ShippingOrderFinished.source == source,
        ).distinct().all()
        existing_set = {r.ecommerce_order_no for r in existing}

        return [o for o in batch_order_set if o not in existing_set]

    @staticmethod
    def get_stale_order_nos() -> List[Tuple[str, str]]:
        """返回所有标记为 is_stale=True 的 (order_no, source) 对"""
        rows = db.session.query(
            ShippingOrderFinished.ecommerce_order_no,
            ShippingOrderFinished.source,
        ).filter_by(is_stale=True).distinct().all()
        return [(r.ecommerce_order_no, r.source) for r in rows]

    @staticmethod
    def get_order_products(order_nos: List[str], source: str = 'shipping') -> Dict[str, Dict]:
        """
        返回 {order_no: {'product_codes': {code: qty}, 'meta': {...}}}
        meta 取该订单第一行的基础字段；customer_alias 取首个非空值。
        """
        records = ShippingRecord.query.filter(
            ShippingRecord.ecommerce_order_no.in_(order_nos),
            ShippingRecord.record_type == 'shipping',
            ShippingRecord.source == source,
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
                        'customer_alias':   r.customer_alias,
                    },
                }
            elif not result[on]['meta'].get('customer_alias') and r.customer_alias:
                result[on]['meta']['customer_alias'] = r.customer_alias
            qty = float(r.quantity) if r.quantity else 0
            if r.product_code and qty > 0:
                result[on]['product_codes'][r.product_code] = (
                    result[on]['product_codes'].get(r.product_code, 0) + qty
                )
        return result

    @staticmethod
    def delete_order_finished(order_nos: List[str], source: str = 'shipping',
                              commit_chunks: bool = True):
        """删除这些订单指定来源的旧结果；导入事务中禁止分块提交。"""
        if order_nos:
            chunk_size = 500
            for i in range(0, len(order_nos), chunk_size):
                chunk = order_nos[i:i + chunk_size]
                ShippingOrderFinished.query.filter(
                    ShippingOrderFinished.ecommerce_order_no.in_(chunk),
                    ShippingOrderFinished.source == source,
                ).delete(synchronize_session=False)
                if commit_chunks:
                    db.session.commit()

    @staticmethod
    def bulk_insert_order_finished(rows: List[Dict], progress_cb=None,
                                   commit_chunks: bool = True):
        """批量写入组合结果，分块 commit 避免大事务持锁超时"""
        chunk_size = 200
        total = len(rows)
        for i in range(0, total, chunk_size):
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
                    customer_alias     = r.get('customer_alias'),
                    source             = r.get('source', 'shipping'),
                    is_stale           = False,
                    resolved_at        = r.get('resolved_at'),
                )
                for r in chunk
            ]
            db.session.bulk_save_objects(objects)
            if commit_chunks:
                db.session.commit()
            if progress_cb:
                progress_cb('saving', current=min(i + chunk_size, total), total=total)

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
        """返回 shipping_record 中所有不重复的订单号（仅发货端发货记录，向后兼容）"""
        rows = db.session.query(ShippingRecord.ecommerce_order_no).filter(
            ShippingRecord.ecommerce_order_no.isnot(None),
            ShippingRecord.record_type == 'shipping',
            ShippingRecord.source == 'shipping',
        ).distinct().all()
        return [r.ecommerce_order_no for r in rows]

    @staticmethod
    def get_all_order_nos_by_source(source: str) -> List[str]:
        """返回指定 source 下所有不重复的订单号（仅发货记录）"""
        rows = db.session.query(ShippingRecord.ecommerce_order_no).filter(
            ShippingRecord.ecommerce_order_no.isnot(None),
            ShippingRecord.record_type == 'shipping',
            ShippingRecord.source == source,
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
    def get_chart_options(date_start=None, date_end=None, source: str = 'shipping') -> Dict:
        """返回渠道层级、省份层级、active产品ID，均按日期范围和数据来源过滤"""
        # ── 缓存：chart_options 仅在导入新数据时变化，可安全缓存 ──
        cache_key = (source, date_start, date_end)
        cached = _chart_options_cache.get(cache_key)
        if cached and time.time() - cached['_at'] < _CHART_OPTIONS_TTL:
            return {k: v for k, v in cached.items() if k != '_at'}

        from database.models.product.category import ProductCategory, ProductSeries, ProductModel
        from database.models.product.finished import ProductFinished
        from datetime import datetime as _dt
        from sqlalchemy import func as sa_func, not_, or_ as sa_or_

        sof = ShippingOrderFinished
        has_date = bool(date_start or date_end)

        def _parse_date(s):
            try: return _dt.strptime(s, '%Y-%m-%d').date()
            except: return None

        d_start = _parse_date(date_start) if date_start else None
        d_end   = _parse_date(date_end)   if date_end   else None

        def _add_date(q):
            if d_start: q = q.filter(sof.shipped_date >= d_start)
            if d_end:   q = q.filter(sof.shipped_date <= d_end)
            return q

        # 索引策略：有日期范围用 ix_sof_source_date（效果更好），否则用 ix_sof_source
        idx_hint = 'ix_sof_source_date' if has_date else 'ix_sof_source'

        # 渠道/省份不再要求 finished_code IS NOT NULL（避免回表，index 覆盖更多）
        # aftersale 操作人排除仅 chart_data 里做，options 不必区分（全量渠道供筛选）
        base = [sof.source == source]

        # 渠道：channel_name → [{code, org_name}]
        ch_q = db.session.query(
            sof.channel_name, sof.channel_code, sof.channel_org_name
        ).with_hint(sof, f'USE INDEX ({idx_hint})', dialect_name='mysql'
        ).filter(*base, sof.channel_name.isnot(None), sof.channel_name != '')
        ch_rows = _add_date(ch_q).distinct().order_by(sof.channel_name, sof.channel_code).all()

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
        ).with_hint(sof, f'USE INDEX ({idx_hint})', dialect_name='mysql'
        ).filter(*base, sof.province.isnot(None), sof.province != '')
        prov_rows = _add_date(prov_q).distinct().order_by(sof.province, sof.city, sof.district).all()

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

        # 活跃产品 ID（需要 finished_code IS NOT NULL + JOIN 产品表）
        from database.models.product.erp_code_rules import ErpCodeRule
        disabled_pfs = [
            r.prefix for r in ErpCodeRule.query.filter_by(type='finished', is_disabled=True).all()
        ]
        prod_base = [sof.finished_code.isnot(None), sof.source == source]
        prod_q = db.session.query(
            ProductCategory.id.label('cat_id'),
            ProductSeries.id.label('ser_id'),
            ProductModel.id.label('mod_id'),
        ).select_from(sof).with_hint(sof, 'USE INDEX (ix_sof_source_finished_code)', dialect_name='mysql'
        ).join(ProductFinished,  sof.finished_code    == ProductFinished.code
        ).join(ProductModel,     ProductFinished.model_id  == ProductModel.id
        ).join(ProductSeries,    ProductModel.series_id    == ProductSeries.id
        ).join(ProductCategory,  ProductSeries.category_id == ProductCategory.id
        ).filter(*prod_base)
        if disabled_pfs:
            prod_q = prod_q.filter(
                not_(sa_or_(*[sof.finished_code.like(p + '%') for p in disabled_pfs]))
            )
        prod_rows = _add_date(prod_q).distinct().all()

        # 日期范围（全表 MIN/MAX，只过滤 source，不加 finished_code 条件 → 索引覆盖扫描 ~1ms）
        date_range_row = db.session.query(
            sa_func.min(sof.shipped_date),
            sa_func.max(sof.shipped_date),
        ).with_hint(sof, 'USE INDEX (ix_sof_source_date)', dialect_name='mysql'
        ).filter(sof.source == source).one()
        min_date = date_range_row[0].strftime('%Y-%m-%d') if date_range_row[0] else None
        max_date = date_range_row[1].strftime('%Y-%m-%d') if date_range_row[1] else None

        # 已配置为发货分析维度的标签分类（及其纳入统计的标签）
        from database.models.product.finished import ProductTagCategory, ProductTag
        tag_cats = ProductTagCategory.query.filter_by(is_shipping_dim=True).order_by(
            ProductTagCategory.sort_order, ProductTagCategory.name
        ).all()
        tag_dimensions = [
            {
                'category_id': cat.id,
                'name':        cat.name,
                'color':       cat.color,
                'tags':        [
                    {'id': t.id, 'name': t.name}
                    for t in cat.tags.filter_by(shipping_dim_enabled=True).order_by(ProductTag.name).all()
                ],
            }
            for cat in tag_cats
        ]

        result = {
            'channels':            channels,
            'provinces':           provinces,
            'active_category_ids': list({r.cat_id for r in prod_rows}),
            'active_series_ids':   list({r.ser_id for r in prod_rows}),
            'active_model_ids':    list({r.mod_id for r in prod_rows}),
            'data_date_min':       min_date,
            'data_date_max':       max_date,
            'tag_dimensions':      tag_dimensions,
        }
        _chart_options_cache[cache_key] = {**result, '_at': time.time()}
        return result

    @staticmethod
    def get_chart_data(params: Dict) -> Dict:
        """
        按过滤条件聚合 shipping_order_finished，返回 summary + 分组明细。
        params keys: group_by, date_start, date_end, channel_names, provinces,
                     category_id, series_id, model_id
        """
        from database.models.product.category import ProductCategory, ProductSeries, ProductModel
        from database.models.product.finished import ProductFinished, ProductTag, ProductTagCategory
        from sqlalchemy import func

        from database.models.product.erp_code_rules import ErpCodeRule
        from database.models.shipping import ShippingFinanceCustomerMapping

        sof = ShippingOrderFinished
        group_by      = params.get('group_by', 'date')
        source        = params.get('source', 'shipping')
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
        trade_type    = params.get('trade_type', 'all')  # 'all'|'domestic'|'foreign'
        tag_filters   = params.get('tag_filters') or []  # [{category_id, tag_ids}]，与 group_by 的标签维度相互独立

        # 禁用的 finished 类型编码前缀，查询时排除对应发货记录
        disabled_prefixes = [
            r.prefix for r in ErpCodeRule.query.filter_by(type='finished', is_disabled=True).all()
        ]

        def _f(v):
            return float(v) if v is not None else 0.0

        # 标签维度：group_by 形如 'tag:<category_id>'
        is_tag_group_by = isinstance(group_by, str) and group_by.startswith('tag:')
        tag_category_id = int(group_by.split(':', 1)[1]) if is_tag_group_by else None
        finance_mapping_field = None
        if source == 'finance' and is_tag_group_by:
            tag_category_name = db.session.query(ProductTagCategory.name).filter(
                ProductTagCategory.id == tag_category_id,
            ).scalar()
            if tag_category_name == '地域':
                finance_mapping_field = ShippingFinanceCustomerMapping.country
            elif tag_category_name == '品牌':
                finance_mapping_field = ShippingFinanceCustomerMapping.brand
        is_finance_mapping_group = finance_mapping_field is not None

        # 保留前端既有 tag_filters 契约：财务端「地域/品牌」标签 ID
        # 只用来查出其显示名，实际筛选改走人工客户映射，不再碰产品标签关系。
        finance_mapping_filters = []
        product_tag_filters = []
        for tag_filter in tag_filters:
            filter_category_id = tag_filter.get('category_id')
            filter_tag_ids = tag_filter.get('tag_ids') or []
            if not filter_category_id or not filter_tag_ids:
                continue
            filter_category_name = None
            if source == 'finance':
                filter_category_name = db.session.query(ProductTagCategory.name).filter(
                    ProductTagCategory.id == filter_category_id,
                ).scalar()
            mapping_field = {
                '地域': ShippingFinanceCustomerMapping.country,
                '品牌': ShippingFinanceCustomerMapping.brand,
            }.get(filter_category_name)
            if mapping_field is None:
                product_tag_filters.append(tag_filter)
                continue
            tag_names = [
                row[0] for row in db.session.query(ProductTag.name).filter(
                    ProductTag.category_id == filter_category_id,
                    ProductTag.id.in_(filter_tag_ids),
                ).all()
            ]
            finance_mapping_filters.append((mapping_field, tag_names))

        # 根据 group_by 判断需要 JOIN 到哪一层产品表
        # 注意：trade_type 过滤已改为用缓存的 finished_code 集合，不再需要 JOIN 产品表
        needs_trade_filter = trade_type in ('domestic', 'foreign')
        needs_finance_mapping = source == 'finance' and (
            needs_trade_filter or is_finance_mapping_group or finance_mapping_filters
        )
        product_group_by  = group_by in ('category', 'series', 'model')
        needs_model_join  = product_group_by or (
            is_tag_group_by and not is_finance_mapping_group
        ) or bool(category_ids or series_ids or model_ids)
        needs_series_join = group_by in ('category', 'series') or bool(category_ids or series_ids)
        needs_cat_join    = group_by == 'category' or bool(category_ids)
        # 预取 FTP finished_code（带缓存，仅 trade_type 过滤时需要）
        ftp_codes = _get_ftp_finished_codes() if (
            needs_trade_filter and source != 'finance'
        ) else set()

        # 售后操作人子查询（在整个 get_chart_data 调用中复用，仅发货端需要）
        aftersale_ops_sub = db.session.query(ShippingOperatorType.operator).filter_by(type='aftersale').subquery()

        def _apply_filters(q):
            """将所有过滤条件应用到查询对象，返回新查询"""
            # 强制使用复合索引：(source, shipped_date) 或 (source, finished_code)
            # MySQL 优化器对 source 选择性低（50%）时不会自动选复合索引
            if date_start or date_end:
                q = q.with_hint(sof, 'USE INDEX (ix_sof_source_date)', dialect_name='mysql')
            elif needs_finance_mapping:
                q = q.with_hint(sof, 'USE INDEX (ix_sof_source_customer_alias)', dialect_name='mysql')
            else:
                q = q.with_hint(sof, 'USE INDEX (ix_sof_source_finished_code)', dialect_name='mysql')
            base_conditions = [
                sof.finished_code.isnot(None),
                sof.source == source,
            ]
            if source == 'shipping':
                base_conditions.append(db.or_(sof.operator.is_(None), ~sof.operator.in_(aftersale_ops_sub)))
            q = q.filter(*base_conditions)
            if needs_model_join:
                q = q.join(ProductFinished,
                           sof.finished_code == ProductFinished.code)
                q = q.join(ProductModel, ProductFinished.model_id == ProductModel.id)
            if needs_series_join:
                q = q.join(ProductSeries, ProductModel.series_id == ProductSeries.id)
            if needs_cat_join:
                q = q.join(ProductCategory, ProductSeries.category_id == ProductCategory.id)
            if needs_finance_mapping:
                q = q.join(
                    ShippingFinanceCustomerMapping,
                    sof.customer_alias == ShippingFinanceCustomerMapping.customer_alias,
                )
            if is_tag_group_by and not is_finance_mapping_group:
                from database.models.product.finished import ProductTag, finished_tag
                q = q.join(finished_tag, ProductFinished.id == finished_tag.c.finished_id
                ).join(ProductTag, db.and_(
                    finished_tag.c.tag_id == ProductTag.id,
                    ProductTag.category_id == tag_category_id,
                    ProductTag.shipping_dim_enabled == True,
                ))
            # 应用产品过滤
            if model_ids:
                q = q.filter(ProductModel.id.in_(model_ids))
            if series_ids:
                q = q.filter(ProductSeries.id.in_(series_ids))
            if category_ids:
                q = q.filter(ProductCategory.id.in_(category_ids))
            # 标签筛选（与 group_by 的标签维度相互独立，可同时叠加多个分类）
            # 先取出符合条件的 finished_code 集合再用 IN 过滤，而非 JOIN：
            # 避免一个产品在同一分类下命中多个已选标签时导致 sof 行重复计入（JOIN 会 fan-out）
            if product_tag_filters:
                from database.models.product.finished import ProductTag, finished_tag as ft_tbl
                for tf in product_tag_filters:
                    f_cat_id = tf.get('category_id')
                    f_tag_ids = tf.get('tag_ids') or []
                    if not f_cat_id or not f_tag_ids:
                        continue
                    matched_codes = {
                        r[0] for r in db.session.query(ProductFinished.code).join(
                            ft_tbl, ProductFinished.id == ft_tbl.c.finished_id
                        ).join(ProductTag, ft_tbl.c.tag_id == ProductTag.id
                        ).filter(ProductTag.category_id == f_cat_id, ProductTag.id.in_(f_tag_ids)).all()
                    }
                    q = q.filter(sof.finished_code.in_(matched_codes))
            for mapping_field, selected_names in finance_mapping_filters:
                q = q.filter(
                    ShippingFinanceCustomerMapping.is_export.is_(True),
                    mapping_field.in_(selected_names),
                )
            # 内外销过滤：使用缓存的 ftp_codes 集合，避免 JOIN 产品表
            if needs_trade_filter:
                if source == 'finance':
                    q = q.filter(
                        ShippingFinanceCustomerMapping.is_export.is_(trade_type == 'foreign')
                    )
                elif ftp_codes:
                    if trade_type == 'domestic':
                        q = q.filter(~sof.finished_code.in_(ftp_codes))
                    elif trade_type == 'foreign':
                        q = q.filter(sof.finished_code.in_(ftp_codes))
                elif trade_type == 'foreign':
                    q = q.filter(db.false())
            if is_finance_mapping_group:
                q = q.filter(
                    ShippingFinanceCustomerMapping.is_export.is_(True),
                    finance_mapping_field.isnot(None),
                    finance_mapping_field != '',
                )
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
            # 排除被禁用编码规则对应的发货记录
            if disabled_prefixes:
                from sqlalchemy import not_, or_ as sa_or_
                q = q.filter(
                    not_(sa_or_(*[sof.finished_code.like(p + '%') for p in disabled_prefixes]))
                )
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
            name_expr  = func.max(sof.channel_org_name)
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
        elif is_finance_mapping_group:
            label_expr = finance_mapping_field
            name_expr  = None
            order_expr = func.sum(sof.actual_quantity).desc()
        elif is_tag_group_by:
            from database.models.product.finished import ProductTag
            label_expr = ProductTag.name
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
            sof.finished_code == ProductFinished.code,
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
    def get_product_monthly(code: str, source: str = 'shipping') -> list:
        """按月聚合指定成品的发货/销退/实际数量，source='shipping'(发货端) 或 'finance'(财务端)"""
        from sqlalchemy import func
        sof = ShippingOrderFinished
        q = (
            db.session.query(
                func.date_format(sof.shipped_date, '%Y-%m').label('month'),
                func.sum(sof.quantity).label('shipped'),
                func.sum(sof.return_quantity).label('returned'),
                func.sum(sof.actual_quantity).label('actual'),
            )
            .filter(
                sof.source == source,
                sof.finished_code == code,
                sof.shipped_date.isnot(None),
            )
        )
        # 发货端排除售后操作人
        if source == 'shipping':
            aftersale_ops = db.session.query(ShippingOperatorType.operator).filter_by(type='aftersale').subquery()
            q = q.filter(db.or_(sof.operator.is_(None), ~sof.operator.in_(aftersale_ops)))
        rows = q.group_by('month').order_by('month').all()

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
