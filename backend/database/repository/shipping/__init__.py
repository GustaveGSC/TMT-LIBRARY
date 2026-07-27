import time
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Dict, Set, Tuple
from sqlalchemy import (
    bindparam, distinct as sql_distinct, func as sql_func, inspect, text, tuple_,
)
from sqlalchemy.exc import IntegrityError
from database.base import db
from database.models.shipping import (
    ShippingBatch, ShippingRecord, ReturnRecord, ReturnWarehouseFilter,
    ShippingOperatorType, ShippingOrderFinished, ShippingTask,
    ShippingFinanceCustomerMapping,
    ShippingOrderFinishedStaging, ShippingResolveTarget,
    ShippingOrderFinishedNext,
    ShippingOrderFinishedGeneration,
    ShippingOrderFinishedGenerationNext,
)
from utils import now_cst

# ── FTP finished_code 缓存（避免 trade_type 过滤时反复 JOIN 产品表）──
_ftp_codes_cache: set = set()
_ftp_codes_cache_at: float = 0.0
_FTP_CACHE_TTL = 300  # 5 分钟


class ShippingTaskLeaseConflict(Exception):
    """A database-backed task lease is already held by another task."""

    def __init__(self, task_id: str):
        super().__init__(task_id)
        self.task_id = task_id


CANCELLABLE_TASK_TYPES = frozenset({
    'import_shipping', 'import_finance', 'resolve_all', 'resolve_stale',
})

_RESOLVE_CUTOVER_LOCK = 'tmt_shipping_resolve_cutover'
_GENERATION_MARKER_ID = 1
_STAGING_CLEANUP_CHUNK = 5000


def _acquire_resolve_cutover_lock(connection, timeout=30):
    if connection.dialect.name != 'mysql':
        return
    acquired = connection.execute(
        text('SELECT GET_LOCK(:lock_name, :timeout)'),
        {'lock_name': _RESOLVE_CUTOVER_LOCK, 'timeout': timeout},
    ).scalar_one()
    if acquired != 1:
        raise RuntimeError('获取发货重算切换锁超时')


def _release_resolve_cutover_lock(connection):
    if connection.dialect.name != 'mysql':
        return
    try:
        connection.execute(
            text('SELECT RELEASE_LOCK(:lock_name)'),
            {'lock_name': _RESOLVE_CUTOVER_LOCK},
        )
    except Exception:
        # Named locks are connection-scoped and are released when a broken
        # connection closes. Cleanup must not mask the original DB failure.
        pass


def _generation_tables_available(connection):
    return inspect(connection).has_table(
        ShippingOrderFinishedGeneration.name,
    ) and inspect(connection).has_table(
        ShippingOrderFinishedGenerationNext.name,
    )


def _assert_mysql_generation_cutover_safe(connection):
    if connection.dialect.name != 'mysql':
        return
    table_names = (
        'shipping_order_finished',
        'shipping_order_finished_next',
        'shipping_order_finished_generation',
        'shipping_order_finished_generation_next',
    )
    engines = connection.execute(
        text("""
            SELECT TABLE_NAME, ENGINE
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME IN :table_names
        """).bindparams(bindparam('table_names', expanding=True)),
        {'table_names': table_names},
    ).all()
    if len(engines) != len(table_names) or any(
        (engine or '').upper() != 'INNODB'
        for _table, engine in engines
    ):
        raise RuntimeError('全量重算切换要求四张代际表均为 InnoDB')

    referencing_fks = connection.execute(text("""
        SELECT COUNT(*)
        FROM information_schema.KEY_COLUMN_USAGE
        WHERE REFERENCED_TABLE_SCHEMA = DATABASE()
          AND REFERENCED_TABLE_NAME = 'shipping_order_finished'
    """)).scalar_one()
    if referencing_fks:
        raise RuntimeError(
            'shipping_order_finished 存在外键引用，禁止 rename 切换'
        )
    outgoing_fks = connection.execute(text("""
        SELECT COUNT(*)
        FROM information_schema.TABLE_CONSTRAINTS
        WHERE CONSTRAINT_SCHEMA = DATABASE()
          AND TABLE_NAME = 'shipping_order_finished'
          AND CONSTRAINT_TYPE = 'FOREIGN KEY'
    """)).scalar_one()
    if outgoing_fks:
        raise RuntimeError(
            'shipping_order_finished 定义了外键，禁止 rename 切换'
        )
    trigger_count = connection.execute(text("""
        SELECT COUNT(*)
        FROM information_schema.TRIGGERS
        WHERE TRIGGER_SCHEMA = DATABASE()
          AND EVENT_OBJECT_TABLE = 'shipping_order_finished'
    """)).scalar_one()
    if trigger_count:
        raise RuntimeError(
            'shipping_order_finished 存在触发器，禁止 rename 切换'
        )

    def column_signature(table_name):
        return connection.execute(text("""
            SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE,
                   COLUMN_DEFAULT, EXTRA,
                   CHARACTER_SET_NAME, COLLATION_NAME
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = :table_name
            ORDER BY ORDINAL_POSITION
        """), {'table_name': table_name}).all()

    def index_signature(table_name):
        return connection.execute(text("""
            SELECT INDEX_NAME, NON_UNIQUE, SEQ_IN_INDEX,
                   COLUMN_NAME, SUB_PART, COLLATION, INDEX_TYPE
            FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = :table_name
            ORDER BY INDEX_NAME, SEQ_IN_INDEX
        """), {'table_name': table_name}).all()

    if (
        column_signature('shipping_order_finished')
        != column_signature('shipping_order_finished_next')
        or index_signature('shipping_order_finished')
        != index_signature('shipping_order_finished_next')
    ):
        raise RuntimeError('正式表与 standby 表结构或索引不一致，拒绝切换')

    for swap_table in (
        'shipping_order_finished_swap',
        'shipping_order_finished_generation_swap',
    ):
        if inspect(connection).has_table(swap_table):
            raise RuntimeError(
                f'检测到未清理的 cutover 临时表 {swap_table}，拒绝切换'
            )


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


# ── chart_options 缓存（导入、图表维度或客户映射变化时失效）──
_chart_options_cache: dict = {}
_CHART_OPTIONS_TTL = 300  # 5 分钟


def _invalidate_chart_options_cache():
    """Clear cached chart filter options after any contributing data changes."""
    _chart_options_cache.clear()


class ShippingRepository:

    # ── 持久化后台任务（独立事务，不得提交导入业务 session）──

    @staticmethod
    def get_finance_customer_aliases(keyword=None, status=None, page=1, per_page=100) -> Dict:
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
        )
        if status == 'pending':
            query = query.filter(db.or_(
                ShippingFinanceCustomerMapping.id.is_(None),
                ShippingFinanceCustomerMapping.status == 'pending',
            ))
        elif status:
            query = query.filter(ShippingFinanceCustomerMapping.status == status)
        query = query.order_by(totals.c.occurrences.desc(), totals.c.customer_alias.asc())

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
            'status': status,
        }

    @staticmethod
    def save_finance_customer_mapping(customer_alias, status, country=None,
                                      brand=None, note=None) -> Dict:
        mapping = ShippingFinanceCustomerMapping.query.filter_by(
            customer_alias=customer_alias,
        ).first()
        if mapping is None:
            mapping = ShippingFinanceCustomerMapping(customer_alias=customer_alias)
            db.session.add(mapping)
        mapping.status = status
        mapping.country = country
        mapping.brand = brand
        mapping.note = note
        mapping.updated_at = now_cst()
        db.session.commit()
        return mapping.to_dict()

    @staticmethod
    def create_task(task_id: str, task_type: str, filename: str = None,
                    lease_key: str = None):
        now = now_cst()
        try:
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
                    lease_key=lease_key,
                    created_at=now,
                    updated_at=now,
                ))
        except IntegrityError:
            if lease_key is None:
                raise
            with db.engine.connect() as connection:
                holder = connection.execute(
                    db.select(ShippingTask.id).where(
                        ShippingTask.lease_key == lease_key,
                    )
                ).scalar_one_or_none()
            if holder is None:
                raise
            raise ShippingTaskLeaseConflict(holder) from None

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
            values['lease_key'] = None
        with db.engine.begin() as connection:
            connection.execute(
                db.update(ShippingTask)
                .where(ShippingTask.id == task_id)
                .values(**values)
            )

    @staticmethod
    def request_task_cancel(task_id: str, requested_by: int):
        """
        原子登记取消请求。

        返回 (outcome, task_snapshot)，outcome 为：
        requested/already_requested/not_found/unsupported/committing/finished。
        """
        now = now_cst()
        table = ShippingTask.__table__
        with db.engine.begin() as connection:
            result = connection.execute(
                db.update(table)
                .where(
                    table.c.id == task_id,
                    table.c.task_type.in_(CANCELLABLE_TASK_TYPES),
                    table.c.status.in_(('pending', 'running')),
                    table.c.cancel_requested_at.is_(None),
                )
                .values(
                    cancel_requested_at=now,
                    cancel_requested_by=requested_by,
                    updated_at=now,
                )
            )
            row = connection.execute(
                db.select(
                    table.c.id,
                    table.c.task_type,
                    table.c.status,
                    table.c.cancel_requested_at,
                ).where(table.c.id == task_id)
            ).mappings().one_or_none()

        if row is None:
            return 'not_found', None
        snapshot = {
            'task_id': row['id'],
            'task_type': row['task_type'],
            'status': row['status'],
            'cancel_requested': row['cancel_requested_at'] is not None,
            'cancellable': (
                row['task_type'] in CANCELLABLE_TASK_TYPES
                and row['status'] in ('pending', 'running')
                and row['cancel_requested_at'] is None
            ),
        }
        if result.rowcount == 1:
            return 'requested', snapshot
        if row['task_type'] not in CANCELLABLE_TASK_TYPES:
            return 'unsupported', snapshot
        if row['status'] == 'committing':
            return 'committing', snapshot
        if row['status'] not in ('pending', 'running'):
            return 'finished', snapshot
        return 'already_requested', snapshot

    @staticmethod
    def is_cancel_requested(task_id: str) -> bool:
        """独立短事务读取取消请求，供 A2 的业务长事务检查。"""
        table = ShippingTask.__table__
        with db.engine.connect() as connection:
            value = connection.execute(
                db.select(table.c.cancel_requested_at).where(table.c.id == task_id)
            ).scalar_one_or_none()
        return value is not None

    @staticmethod
    def try_begin_commit(task_id: str) -> bool:
        """
        与取消请求竞争最终提交权。

        仅当任务仍活跃且尚未请求取消时，原子切换到 committing。
        """
        table = ShippingTask.__table__
        with db.engine.begin() as connection:
            result = connection.execute(
                db.update(table)
                .where(
                    table.c.id == task_id,
                    table.c.status.in_(('pending', 'running')),
                    table.c.cancel_requested_at.is_(None),
                )
                .values(status='committing', updated_at=now_cst())
            )
        return result.rowcount == 1

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
        """
        新 worker 启动时恢复已发布代，并中断其余遗留任务。

        RENAME TABLE 与任务状态更新不能处在同一事务内。正式代标记随数据表
        一起 rename；若进程恰好在 rename 后退出，启动恢复会据此把 committing
        任务补写为 done，而不是误报 interrupted。
        """
        now = now_cst()
        with db.engine.connect() as connection:
            _acquire_resolve_cutover_lock(connection)
            try:
                published_task_id = None
                if _generation_tables_available(connection):
                    published_task_id = connection.execute(
                        db.select(
                            ShippingOrderFinishedGeneration.c.task_id
                        ).where(
                            ShippingOrderFinishedGeneration.c.id
                            == _GENERATION_MARKER_ID,
                        )
                    ).scalar_one_or_none()
                    if published_task_id:
                        published = connection.execute(
                            db.select(
                                ShippingTask.status,
                                ShippingTask.result,
                            ).where(ShippingTask.id == published_task_id)
                        ).mappings().one_or_none()
                        if published and published['status'] == 'committing':
                            result_data = published['result'] or {}
                            connection.execute(
                                db.update(ShippingTask)
                                .where(
                                    ShippingTask.id == published_task_id,
                                    ShippingTask.status == 'committing',
                                )
                                .values(
                                    status='done',
                                    progress={
                                        'step': 'done',
                                        'data': result_data,
                                    },
                                    result=result_data,
                                    message='',
                                    updated_at=now,
                                    finished_at=now,
                                    lease_key=None,
                                )
                            )
                            connection.commit()

                result = connection.execute(
                    db.update(ShippingTask)
                    .where(
                        ShippingTask.status.in_(
                            ('pending', 'running', 'committing')
                        )
                    )
                    .values(
                        status='interrupted',
                        message='任务因服务重启或重载中断',
                        updated_at=now,
                        finished_at=now,
                        lease_key=None,
                    )
                )
                interrupted = result.rowcount
                connection.commit()

                if _generation_tables_available(connection):
                    standby_owner = connection.execute(
                        db.select(
                            ShippingOrderFinishedGenerationNext.c.task_id
                        ).where(
                            ShippingOrderFinishedGenerationNext.c.id
                            == _GENERATION_MARKER_ID,
                        )
                    ).scalar_one_or_none()
                    owner_status = None
                    if standby_owner:
                        owner_status = connection.execute(
                            db.select(ShippingTask.status).where(
                                ShippingTask.id == standby_owner,
                            )
                        ).scalar_one_or_none()
                    if owner_status in (
                        'error', 'cancelled', 'interrupted',
                    ):
                        if connection.dialect.name == 'mysql':
                            connection.execute(text(
                                'TRUNCATE TABLE '
                                'shipping_order_finished_next'
                            ))
                            connection.commit()
                        else:
                            connection.execute(
                                db.delete(ShippingOrderFinishedNext)
                            )
                            connection.commit()
                        connection.execute(
                            db.update(
                                ShippingOrderFinishedGenerationNext
                            )
                            .where(
                                ShippingOrderFinishedGenerationNext.c.id
                                == _GENERATION_MARKER_ID,
                            )
                            .values(
                                task_id=None,
                                row_count=None,
                                published_at=None,
                            )
                        )
                        connection.commit()
                return interrupted
            finally:
                _release_resolve_cutover_lock(connection)

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
    def get_existing_keys(keys: List[Tuple], record_type: str = None,
                          cancel_check=None) -> Set[Tuple]:
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
            if cancel_check and cancel_check():
                raise InterruptedError('用户已请求取消任务')
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
            if cancel_check and cancel_check():
                raise InterruptedError('用户已请求取消任务')
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
    def get_finance_shipping_snapshots(keys: List[Tuple],
                                       cancel_check=None) -> Dict[Tuple, Dict]:
        """Return fields that determine whether a finance shipping row changed."""
        if not keys:
            return {}
        snapshots = {}
        columns = (
            ShippingRecord.ecommerce_order_no,
            ShippingRecord.product_code,
            ShippingRecord.shipped_date,
            ShippingRecord.channel_name,
            ShippingRecord.product_name,
            ShippingRecord.spec,
            ShippingRecord.quantity,
            ShippingRecord.province,
            ShippingRecord.city,
            ShippingRecord.district,
            ShippingRecord.customer_alias,
        )
        for i in range(0, len(keys), 500):
            if cancel_check and cancel_check():
                raise InterruptedError('用户已请求取消任务')
            rows = db.session.query(*columns).filter(
                db.tuple_(
                    ShippingRecord.ecommerce_order_no,
                    ShippingRecord.product_code,
                    ShippingRecord.shipped_date,
                ).in_(keys[i:i + 500]),
                ShippingRecord.source == 'finance',
            ).all()
            for row in rows:
                key = (row.ecommerce_order_no, row.product_code, row.shipped_date)
                snapshots[key] = {
                    'channel_name': row.channel_name,
                    'product_name': row.product_name,
                    'spec': row.spec,
                    'quantity': row.quantity,
                    'province': row.province,
                    'city': row.city,
                    'district': row.district,
                    'customer_alias': row.customer_alias,
                }
            if cancel_check and cancel_check():
                raise InterruptedError('用户已请求取消任务')
        return snapshots

    @staticmethod
    def bulk_insert_shipping(batch_id: int, rows: List[Dict],
                              progress_cb=None, record_type: str = 'shipping',
                              source: str = 'shipping', commit_chunks: bool = True,
                              cancel_check=None) -> int:
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
            if cancel_check and cancel_check():
                raise InterruptedError('用户已请求取消任务')
            chunk = rows[i:i + CHUNK]
            db.session.execute(stmt, [_make_param(r) for r in chunk])
            if cancel_check and cancel_check():
                raise InterruptedError('用户已请求取消任务')
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
    def get_finance_return_snapshots(keys: List[Tuple],
                                     cancel_check=None) -> Dict[Tuple, Dict]:
        """Return fields that determine whether a finance return row changed."""
        if not keys:
            return {}
        snapshots = {}
        columns = (
            ReturnRecord.ecommerce_order_no,
            ReturnRecord.product_code,
            ReturnRecord.shipped_date,
            ReturnRecord.quantity,
            ReturnRecord.warehouse_name,
            ReturnRecord.customer_alias,
        )
        for i in range(0, len(keys), 500):
            if cancel_check and cancel_check():
                raise InterruptedError('用户已请求取消任务')
            rows = db.session.query(*columns).filter(
                db.tuple_(
                    ReturnRecord.ecommerce_order_no,
                    ReturnRecord.product_code,
                    ReturnRecord.shipped_date,
                ).in_(keys[i:i + 500]),
            ).all()
            for row in rows:
                key = (row.ecommerce_order_no, row.product_code, row.shipped_date)
                snapshots[key] = {
                    'quantity': row.quantity,
                    'warehouse_name': row.warehouse_name,
                    'customer_alias': row.customer_alias,
                }
            if cancel_check and cancel_check():
                raise InterruptedError('用户已请求取消任务')
        return snapshots

    @staticmethod
    def get_finance_customer_alias_conflicts(order_nos: List[str], *,
                                             limit: int = 100,
                                             cancel_check=None) -> Tuple[int, List[str]]:
        """
        返回指定财务订单中存在多个非空客户简称的订单总数及前 limit 个订单号。

        查询运行在导入业务事务内，因此能看到本批尚未提交的 UPSERT 结果。
        """
        normalized_order_nos = sorted({
            order_no for order_no in order_nos if order_no
        })
        if not normalized_order_nos:
            return 0, []

        total = 0
        samples = []
        # 与 resolve 的订单加载分块一致，控制 IN 参数规模同时避免大文件产生数百次往返。
        chunk_size = 2000
        for index in range(0, len(normalized_order_nos), chunk_size):
            if cancel_check and cancel_check():
                raise InterruptedError('用户已请求取消任务')
            chunk = normalized_order_nos[index:index + chunk_size]
            rows = db.session.query(
                ShippingRecord.ecommerce_order_no,
            ).filter(
                ShippingRecord.ecommerce_order_no.in_(chunk),
                ShippingRecord.record_type == 'shipping',
                ShippingRecord.source == 'finance',
                ShippingRecord.customer_alias.isnot(None),
                sql_func.trim(ShippingRecord.customer_alias) != '',
            ).group_by(
                ShippingRecord.ecommerce_order_no,
            ).having(
                sql_func.count(
                    sql_distinct(sql_func.trim(ShippingRecord.customer_alias))
                ) > 1
            ).order_by(
                ShippingRecord.ecommerce_order_no,
            ).all()
            total += len(rows)
            if len(samples) < limit:
                samples.extend(
                    row.ecommerce_order_no
                    for row in rows[:limit - len(samples)]
                )
            if cancel_check and cancel_check():
                raise InterruptedError('用户已请求取消任务')
        return total, samples

    @staticmethod
    def bulk_insert_return(batch_id: int, rows: List[Dict], progress_cb=None,
                           commit_chunks: bool = True, cancel_check=None) -> int:
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
            if cancel_check and cancel_check():
                raise InterruptedError('用户已请求取消任务')
            chunk = rows[i:i + CHUNK]
            db.session.execute(stmt, [_make_param(r) for r in chunk])
            if cancel_check and cancel_check():
                raise InterruptedError('用户已请求取消任务')
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
        return count

    @staticmethod
    def get_warehouse_filter_states(names: Set[str]) -> Dict[str, bool]:
        """Return persisted exclusion states for the supplied warehouse names."""
        if not names:
            return {}
        rows = ReturnWarehouseFilter.query.filter(
            ReturnWarehouseFilter.warehouse_name.in_(names),
        ).all()
        return {row.warehouse_name: bool(row.is_excluded) for row in rows}

    @staticmethod
    def _mark_stale_pairs(pair_query) -> int:
        """Mark existing derived order/source pairs stale and return their count.

        The caller owns the surrounding transaction so configuration and this
        marker can commit (or roll back) as one unit.
        """
        pairs = pair_query.distinct().subquery()
        count = db.session.query(sql_func.count()).select_from(pairs).scalar() or 0
        if count:
            db.session.query(ShippingOrderFinished).filter(
                tuple_(
                    ShippingOrderFinished.source,
                    ShippingOrderFinished.ecommerce_order_no,
                ).in_(
                    db.session.query(pairs.c.source, pairs.c.ecommerce_order_no),
                ),
            ).update({ShippingOrderFinished.is_stale: True}, synchronize_session=False)
        return int(count)

    @staticmethod
    def mark_stale_for_component_codes(component_codes: Set[str], finished_codes: Set[str]) -> int:
        """Mark derived orders affected by an exact component/finished rule change."""
        component_codes = {code for code in component_codes if code}
        finished_codes = {code for code in finished_codes if code}
        if not component_codes and not finished_codes:
            return 0
        pair_queries = []
        if component_codes:
            pair_queries.append(db.session.query(
                ShippingOrderFinished.source.label('source'),
                ShippingOrderFinished.ecommerce_order_no.label('ecommerce_order_no'),
            ).join(
                ShippingRecord,
                (ShippingRecord.source == ShippingOrderFinished.source)
                & (ShippingRecord.ecommerce_order_no == ShippingOrderFinished.ecommerce_order_no),
            ).filter(
                ShippingRecord.record_type == 'shipping',
                ShippingRecord.ecommerce_order_no.isnot(None),
                ShippingRecord.product_code.in_(component_codes),
            ))
            pair_queries.append(db.session.query(
                ShippingOrderFinished.source.label('source'),
                ShippingOrderFinished.ecommerce_order_no.label('ecommerce_order_no'),
            ).join(
                ReturnRecord,
                ReturnRecord.ecommerce_order_no == ShippingOrderFinished.ecommerce_order_no,
            ).filter(ReturnRecord.product_code.in_(component_codes)))
        if finished_codes:
            pair_queries.append(db.session.query(
                ShippingOrderFinished.source.label('source'),
                ShippingOrderFinished.ecommerce_order_no.label('ecommerce_order_no'),
            ).filter(ShippingOrderFinished.finished_code.in_(finished_codes)))
        pair_query = pair_queries[0]
        for query in pair_queries[1:]:
            pair_query = pair_query.union(query)
        return ShippingRepository._mark_stale_pairs(pair_query)

    @staticmethod
    def mark_stale_for_warehouse_names(warehouse_names: Set[str]) -> int:
        """Mark all source/order pairs whose return quantity uses changed warehouses."""
        names = {name for name in warehouse_names if name}
        if not names:
            return 0
        pairs = db.session.query(
            ShippingOrderFinished.source.label('source'),
            ShippingOrderFinished.ecommerce_order_no.label('ecommerce_order_no'),
        ).join(
            ReturnRecord,
            ReturnRecord.ecommerce_order_no == ShippingOrderFinished.ecommerce_order_no,
        ).filter(ReturnRecord.warehouse_name.in_(names))
        return ShippingRepository._mark_stale_pairs(pairs)

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
        meta 取完成发货代表行（日期降序、同日 id 降序）；
        customer_alias 若代表行为空，则按相同确定性顺序回退首个非空值。
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
                    'meta': None,
                    '_meta_key': None,
                    '_alias_key': None,
                    '_fallback_alias': None,
                }
            row_key = (
                r.shipped_date is not None,
                r.shipped_date,
                r.id or 0,
            )
            if result[on]['_meta_key'] is None or row_key > result[on]['_meta_key']:
                result[on]['_meta_key'] = row_key
                result[on]['meta'] = {
                    'shipped_date':     r.shipped_date,
                    'operator':         r.operator,
                    'channel_name':     r.channel_name,
                    'channel_code':     r.channel_code,
                    'channel_org_name': r.channel_org_name,
                    'province':         r.province,
                    'city':             r.city,
                    'district':         r.district,
                    'customer_alias':   r.customer_alias,
                }
            if (
                r.customer_alias
                and (
                    result[on]['_alias_key'] is None
                    or row_key > result[on]['_alias_key']
                )
            ):
                result[on]['_alias_key'] = row_key
                result[on]['_fallback_alias'] = r.customer_alias
            qty = float(r.quantity) if r.quantity else 0
            if r.product_code and qty > 0:
                result[on]['product_codes'][r.product_code] = (
                    result[on]['product_codes'].get(r.product_code, 0) + qty
                )
        for data in result.values():
            if not data['meta'].get('customer_alias'):
                data['meta']['customer_alias'] = data['_fallback_alias']
            del data['_meta_key']
            del data['_alias_key']
            del data['_fallback_alias']
        return result

    @staticmethod
    def delete_order_finished(order_nos: List[str], source: str = 'shipping',
                              commit_chunks: bool = True, cancel_check=None):
        """删除这些订单指定来源的旧结果；导入事务中禁止分块提交。"""
        if order_nos:
            chunk_size = 500
            for i in range(0, len(order_nos), chunk_size):
                if cancel_check and cancel_check():
                    raise InterruptedError('用户已请求取消任务')
                chunk = order_nos[i:i + chunk_size]
                ShippingOrderFinished.query.filter(
                    ShippingOrderFinished.ecommerce_order_no.in_(chunk),
                    ShippingOrderFinished.source == source,
                ).delete(synchronize_session=False)
                if cancel_check and cancel_check():
                    raise InterruptedError('用户已请求取消任务')
                if commit_chunks:
                    db.session.commit()

    @staticmethod
    def bulk_insert_order_finished(rows: List[Dict], progress_cb=None,
                                   commit_chunks: bool = True, cancel_check=None):
        """批量写入组合结果，分块 commit 避免大事务持锁超时"""
        chunk_size = 200
        total = len(rows)
        for i in range(0, total, chunk_size):
            if cancel_check and cancel_check():
                raise InterruptedError('用户已请求取消任务')
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
            if cancel_check and cancel_check():
                raise InterruptedError('用户已请求取消任务')
            if commit_chunks:
                db.session.commit()
            if progress_cb:
                progress_cb('saving', current=min(i + chunk_size, total), total=total)

    @staticmethod
    def create_resolve_targets(task_id: str, pairs: List[Tuple[str, str]],
                               cancel_check=None):
        """Persist the complete cutover scope in bounded committed chunks."""
        unique_pairs = sorted({
            (source, order_no)
            for order_no, source in pairs
            if order_no and source in ('shipping', 'finance')
        })
        chunk_size = 1000
        for index in range(0, len(unique_pairs), chunk_size):
            if cancel_check and cancel_check():
                raise InterruptedError('用户已请求取消任务')
            db.session.bulk_save_objects([
                ShippingResolveTarget(
                    task_id=task_id,
                    source=source,
                    ecommerce_order_no=order_no,
                )
                for source, order_no in unique_pairs[index:index + chunk_size]
            ])
            db.session.commit()
        return len(unique_pairs)

    @staticmethod
    def bulk_insert_order_finished_staging(task_id: str, rows: List[Dict],
                                           progress_cb=None,
                                           cancel_check=None):
        """Write task-isolated resolve output; committed staging is not live data."""
        chunk_size = 200
        total = len(rows)
        for index in range(0, total, chunk_size):
            if cancel_check and cancel_check():
                raise InterruptedError('用户已请求取消任务')
            chunk = rows[index:index + chunk_size]
            db.session.bulk_save_objects([
                ShippingOrderFinishedStaging(
                    task_id             = task_id,
                    ecommerce_order_no = row['ecommerce_order_no'],
                    finished_code      = row.get('finished_code'),
                    finished_name      = row.get('finished_name'),
                    quantity           = row.get('quantity'),
                    return_quantity    = row.get('return_quantity', 0),
                    actual_quantity    = row.get('actual_quantity'),
                    shipped_date       = row.get('shipped_date'),
                    operator           = row.get('operator'),
                    channel_name       = row.get('channel_name'),
                    channel_code       = row.get('channel_code'),
                    channel_org_name   = row.get('channel_org_name'),
                    province           = row.get('province'),
                    city               = row.get('city'),
                    district           = row.get('district'),
                    customer_alias     = row.get('customer_alias'),
                    source             = row.get('source', 'shipping'),
                    is_stale           = False,
                    resolved_at        = row.get('resolved_at'),
                )
                for row in chunk
            ])
            db.session.commit()
            if progress_cb:
                progress_cb(
                    'saving',
                    current=min(index + len(chunk), total),
                    total=total,
                )

    @staticmethod
    def reset_full_resolve_generation(task_id: str):
        """Claim and empty the private standby table before a full rebuild."""
        with db.engine.connect() as connection:
            _acquire_resolve_cutover_lock(connection)
            try:
                _assert_mysql_generation_cutover_safe(connection)
                connection.execute(
                    db.update(ShippingOrderFinishedGenerationNext)
                    .where(
                        ShippingOrderFinishedGenerationNext.c.id
                        == _GENERATION_MARKER_ID,
                    )
                    .values(
                        task_id=task_id,
                        row_count=None,
                        published_at=None,
                    )
                )
                connection.commit()
                if connection.dialect.name == 'mysql':
                    connection.execute(
                        text('TRUNCATE TABLE shipping_order_finished_next')
                    )
                    connection.commit()
                else:
                    connection.execute(
                        db.delete(ShippingOrderFinishedNext)
                    )
                    connection.commit()
            finally:
                _release_resolve_cutover_lock(connection)

    @staticmethod
    def bulk_insert_order_finished_generation(
            task_id: str, rows: List[Dict], progress_cb=None,
            cancel_check=None):
        """
        Append rows to the claimed full-generation standby table.

        The advisory lock makes reset/recovery and a committed insert chunk
        mutually exclusive across graceful reload workers.
        """
        columns = tuple(
            column.name
            for column in ShippingOrderFinishedNext.c
            if column.name != 'id'
        )
        prepared = [
            {
                column: (
                    False if column == 'is_stale'
                    else row.get(column)
                )
                for column in columns
            }
            for row in rows
        ]
        total = len(prepared)
        chunk_size = 1000
        with db.engine.connect() as connection:
            _acquire_resolve_cutover_lock(connection)
            try:
                owner = connection.execute(
                    db.select(
                        ShippingOrderFinishedGenerationNext.c.task_id
                    ).where(
                        ShippingOrderFinishedGenerationNext.c.id
                        == _GENERATION_MARKER_ID,
                    )
                ).scalar_one_or_none()
                if owner != task_id:
                    raise InterruptedError(
                        '全量重算暂存代所有权已失效'
                    )
                for index in range(0, total, chunk_size):
                    if cancel_check and cancel_check():
                        raise InterruptedError('用户已请求取消任务')
                    chunk = prepared[index:index + chunk_size]
                    if chunk:
                        connection.execute(
                            db.insert(ShippingOrderFinishedNext),
                            chunk,
                        )
                        connection.commit()
                    if progress_cb:
                        progress_cb(
                            'saving',
                            current=min(index + len(chunk), total),
                            total=total,
                        )
            finally:
                _release_resolve_cutover_lock(connection)

    @staticmethod
    def get_full_generation_stats(task_id: str) -> Dict:
        with db.engine.connect() as connection:
            owner = connection.execute(
                db.select(
                    ShippingOrderFinishedGenerationNext.c.task_id
                ).where(
                    ShippingOrderFinishedGenerationNext.c.id
                    == _GENERATION_MARKER_ID,
                )
            ).scalar_one_or_none()
            if owner != task_id:
                raise RuntimeError('全量重算暂存代所有权校验失败')
            target_count = connection.execute(
                db.select(sql_func.count()).select_from(
                    ShippingResolveTarget
                ).where(ShippingResolveTarget.task_id == task_id)
            ).scalar_one()
            generation_rows = connection.execute(
                db.select(sql_func.count()).select_from(
                    ShippingOrderFinishedNext
                )
            ).scalar_one()
        return {
            'target_count': int(target_count),
            'staging_count': int(generation_rows),
            'orphan_count': 0,
        }

    @staticmethod
    def get_resolve_staging_stats(task_id: str) -> Dict:
        target = ShippingResolveTarget.__table__
        staging = ShippingOrderFinishedStaging.__table__
        with db.engine.connect() as connection:
            target_count = connection.execute(
                db.select(sql_func.count()).select_from(target).where(
                    target.c.task_id == task_id,
                )
            ).scalar_one()
            staging_count = connection.execute(
                db.select(sql_func.count()).select_from(staging).where(
                    staging.c.task_id == task_id,
                )
            ).scalar_one()
            orphan_count = connection.execute(
                db.select(sql_func.count()).select_from(staging).where(
                    staging.c.task_id == task_id,
                    ~db.exists(
                        db.select(1).select_from(target).where(
                            target.c.task_id == task_id,
                            target.c.source == staging.c.source,
                            target.c.ecommerce_order_no == staging.c.ecommerce_order_no,
                        )
                    ),
                )
            ).scalar_one()
        return {
            'target_count': int(target_count),
            'staging_count': int(staging_count),
            'orphan_count': int(orphan_count),
        }

    @staticmethod
    def _finalize_published_generation(connection, task_id: str, result: Dict):
        finished_at = now_cst()
        update = connection.execute(
            db.update(ShippingTask)
            .where(
                ShippingTask.id == task_id,
                ShippingTask.status == 'committing',
            )
            .values(
                status='done',
                progress={'step': 'done', 'data': result},
                result=result,
                message='',
                finished_at=finished_at,
                updated_at=finished_at,
                lease_key=None,
            )
        )
        if update.rowcount not in (0, 1):
            raise RuntimeError('全量重算任务终态更新数量异常')
        connection.commit()

    @staticmethod
    def _rename_full_generation(connection):
        if connection.dialect.name == 'mysql':
            connection.execute(text("""
                RENAME TABLE
                    shipping_order_finished
                        TO shipping_order_finished_swap,
                    shipping_order_finished_next
                        TO shipping_order_finished,
                    shipping_order_finished_swap
                        TO shipping_order_finished_next,
                    shipping_order_finished_generation
                        TO shipping_order_finished_generation_swap,
                    shipping_order_finished_generation_next
                        TO shipping_order_finished_generation,
                    shipping_order_finished_generation_swap
                        TO shipping_order_finished_generation_next
            """))
            return

        # SQLite-only test fallback. Production always uses the single MySQL
        # RENAME TABLE statement above.
        statements = (
            'ALTER TABLE shipping_order_finished '
            'RENAME TO shipping_order_finished_swap',
            'ALTER TABLE shipping_order_finished_next '
            'RENAME TO shipping_order_finished',
            'ALTER TABLE shipping_order_finished_swap '
            'RENAME TO shipping_order_finished_next',
            'ALTER TABLE shipping_order_finished_generation '
            'RENAME TO shipping_order_finished_generation_swap',
            'ALTER TABLE shipping_order_finished_generation_next '
            'RENAME TO shipping_order_finished_generation',
            'ALTER TABLE shipping_order_finished_generation_swap '
            'RENAME TO shipping_order_finished_generation_next',
        )
        for statement in statements:
            connection.execute(text(statement))
        connection.commit()

    @staticmethod
    def publish_full_generation(task_id: str, *, resolved_count: int,
                                generation_rows: int) -> Dict:
        """
        Atomically swap the fully built standby table into the live name.

        The generation marker is renamed in the same MySQL statement. If the
        worker exits after DDL commit but before task finalization, startup
        recovery can prove publication and finish the committing task.
        """
        result = None
        try:
            with db.engine.connect() as connection:
                _acquire_resolve_cutover_lock(connection)
                try:
                    _assert_mysql_generation_cutover_safe(connection)
                    owner = connection.execute(
                        db.select(
                            ShippingOrderFinishedGenerationNext.c.task_id
                        ).where(
                            ShippingOrderFinishedGenerationNext.c.id
                            == _GENERATION_MARKER_ID,
                        )
                    ).scalar_one_or_none()
                    if owner != task_id:
                        raise RuntimeError('全量重算 standby 所有权已失效')

                    status = connection.execute(
                        db.select(ShippingTask.status).where(
                            ShippingTask.id == task_id,
                        )
                    ).scalar_one_or_none()
                    if status != 'committing':
                        raise RuntimeError('重算任务状态已变化，拒绝发布 standby')

                    actual_rows = connection.execute(
                        db.select(sql_func.count()).select_from(
                            ShippingOrderFinishedNext
                        )
                    ).scalar_one()
                    if int(actual_rows) != int(generation_rows):
                        raise RuntimeError('standby 行数在切换前发生变化')
                    live_rows = connection.execute(
                        db.select(sql_func.count()).select_from(
                            ShippingOrderFinished
                        )
                    ).scalar_one()
                    result = {
                        'resolved': int(resolved_count),
                        'staged_rows': int(generation_rows),
                        'deleted_rows': int(live_rows),
                        'inserted_rows': int(actual_rows),
                        'cleanup_pending': False,
                        'cutover': 'rename',
                        'retired_generation_retained': True,
                    }
                    prepared_at = now_cst()
                    connection.execute(
                        db.update(ShippingOrderFinishedGenerationNext)
                        .where(
                            ShippingOrderFinishedGenerationNext.c.id
                            == _GENERATION_MARKER_ID,
                        )
                        .values(
                            row_count=int(actual_rows),
                            published_at=prepared_at,
                        )
                    )
                    connection.execute(
                        db.update(ShippingTask)
                        .where(
                            ShippingTask.id == task_id,
                            ShippingTask.status == 'committing',
                        )
                        .values(
                            progress={
                                'step': 'committing',
                                'data': result,
                            },
                            result=result,
                            updated_at=prepared_at,
                        )
                    )
                    connection.commit()

                    ShippingRepository._rename_full_generation(connection)
                    ShippingRepository._finalize_published_generation(
                        connection, task_id, result,
                    )
                    return result
                finally:
                    _release_resolve_cutover_lock(connection)
        except Exception:
            # A socket timeout can make DDL outcome ambiguous to the client.
            # Reconnect and trust the atomically renamed live marker.
            with db.engine.connect() as recovery:
                live_owner = recovery.execute(
                    db.select(
                        ShippingOrderFinishedGeneration.c.task_id
                    ).where(
                        ShippingOrderFinishedGeneration.c.id
                        == _GENERATION_MARKER_ID,
                    )
                ).scalar_one_or_none()
                if live_owner == task_id:
                    stored_result = recovery.execute(
                        db.select(ShippingTask.result).where(
                            ShippingTask.id == task_id,
                        )
                    ).scalar_one_or_none() or result or {}
                    ShippingRepository._finalize_published_generation(
                        recovery, task_id, stored_result,
                    )
                    return stored_result
            raise

    @staticmethod
    def rollback_published_full_generation(task_id: str) -> Dict:
        """
        Atomically swap the retained previous generation back into service.

        This is an explicit maintenance operation, not an HTTP endpoint.
        """
        with db.engine.connect() as connection:
            _acquire_resolve_cutover_lock(connection)
            try:
                _assert_mysql_generation_cutover_safe(connection)
                live_owner = connection.execute(
                    db.select(
                        ShippingOrderFinishedGeneration.c.task_id
                    ).where(
                        ShippingOrderFinishedGeneration.c.id
                        == _GENERATION_MARKER_ID,
                    )
                ).scalar_one_or_none()
                if live_owner != task_id:
                    raise RuntimeError(
                        '当前正式代不是指定任务发布的版本，拒绝回切'
                    )
                standby_owner = connection.execute(
                    db.select(
                        ShippingOrderFinishedGenerationNext.c.task_id
                    ).where(
                        ShippingOrderFinishedGenerationNext.c.id
                        == _GENERATION_MARKER_ID,
                    )
                ).scalar_one_or_none()
                if standby_owner:
                    standby_status = connection.execute(
                        db.select(ShippingTask.status).where(
                            ShippingTask.id == standby_owner,
                        )
                    ).scalar_one_or_none()
                    if standby_status in (
                        'pending', 'running', 'committing',
                    ):
                        raise RuntimeError(
                            'standby 正被活跃任务使用，拒绝回切'
                        )

                ShippingRepository._rename_full_generation(connection)
                task_result = connection.execute(
                    db.select(ShippingTask.result).where(
                        ShippingTask.id == task_id,
                    )
                ).scalar_one_or_none() or {}
                task_result = {
                    **task_result,
                    'rolled_back': True,
                    'rolled_back_at': now_cst().strftime(
                        '%Y-%m-%d %H:%M:%S'
                    ),
                }
                connection.execute(
                    db.update(ShippingTask)
                    .where(ShippingTask.id == task_id)
                    .values(
                        result=task_result,
                        progress={'step': 'done', 'data': task_result},
                        message='该全量重算发布已回切到上一代',
                        updated_at=now_cst(),
                    )
                )
                connection.commit()
                return task_result
            finally:
                _release_resolve_cutover_lock(connection)

    @staticmethod
    def cutover_resolve_staging(task_id: str, *, full_rebuild: bool,
                                resolved_count: int,
                                staged_rows: int) -> Dict:
        """
        Atomically publish a fully prepared generation and finish its task.

        Keeping the live-table cutover and the terminal task state in one
        transaction closes the reload window where new data could be visible
        while startup recovery still marked the task as interrupted.
        """
        live = ShippingOrderFinished.__table__
        staging = ShippingOrderFinishedStaging.__table__
        target = ShippingResolveTarget.__table__
        task = ShippingTask.__table__
        columns = (
            'ecommerce_order_no', 'finished_code', 'finished_name', 'quantity',
            'return_quantity', 'actual_quantity', 'shipped_date', 'operator',
            'channel_name', 'channel_code', 'channel_org_name', 'province',
            'city', 'district', 'customer_alias', 'source', 'is_stale',
            'resolved_at',
        )
        if full_rebuild:
            raise RuntimeError(
                '全量重算必须使用 rename-table generation cutover'
            )
        with db.engine.begin() as connection:
            in_scope = db.exists(
                db.select(1).select_from(target).where(
                    target.c.task_id == task_id,
                    target.c.source == live.c.source,
                    target.c.ecommerce_order_no == live.c.ecommerce_order_no,
                )
            )
            deleted = connection.execute(
                db.delete(live).where(in_scope)
            ).rowcount
            source_rows = db.select(
                *(staging.c[column] for column in columns)
            ).where(staging.c.task_id == task_id)
            inserted = connection.execute(
                db.insert(live).from_select(columns, source_rows)
            ).rowcount
            result = {
                'resolved': resolved_count,
                'staged_rows': staged_rows,
                'deleted_rows': max(deleted or 0, 0),
                'inserted_rows': max(inserted or 0, 0),
                'cleanup_pending': False,
            }
            finished_at = now_cst()
            task_update = connection.execute(
                db.update(task)
                .where(
                    task.c.id == task_id,
                    task.c.status == 'committing',
                )
                .values(
                    status='done',
                    progress={'step': 'done', 'data': result},
                    result=result,
                    message='',
                    finished_at=finished_at,
                    updated_at=finished_at,
                    lease_key=None,
                )
            )
            if task_update.rowcount != 1:
                raise RuntimeError('重算任务状态已变化，拒绝发布暂存结果')
        return result

    @staticmethod
    def cleanup_resolve_staging(task_id: str):
        """
        Idempotently clean private resolve data with fresh-connection retries.

        Large task scopes are deleted in committed chunks so cleanup does not
        repeat the failed 30-second monolithic DELETE pattern.
        """
        last_error = None
        for attempt in range(3):
            try:
                with db.engine.connect() as connection:
                    if connection.dialect.name == 'mysql':
                        for table_name in (
                            'shipping_order_finished_staging',
                            'shipping_resolve_target',
                        ):
                            while True:
                                deleted = connection.execute(
                                    text(
                                        f'DELETE FROM {table_name} '
                                        'WHERE task_id = :task_id '
                                        f'LIMIT {_STAGING_CLEANUP_CHUNK}'
                                    ),
                                    {'task_id': task_id},
                                ).rowcount
                                connection.commit()
                                if not deleted:
                                    break
                    else:
                        connection.execute(
                            db.delete(ShippingOrderFinishedStaging).where(
                                ShippingOrderFinishedStaging.task_id
                                == task_id,
                            )
                        )
                        connection.execute(
                            db.delete(ShippingResolveTarget).where(
                                ShippingResolveTarget.task_id == task_id,
                            )
                        )
                        connection.commit()

                    if _generation_tables_available(connection):
                        _acquire_resolve_cutover_lock(connection)
                        try:
                            owner = connection.execute(
                                db.select(
                                    ShippingOrderFinishedGenerationNext.c.task_id
                                ).where(
                                    ShippingOrderFinishedGenerationNext.c.id
                                    == _GENERATION_MARKER_ID,
                                )
                            ).scalar_one_or_none()
                            if owner == task_id:
                                if connection.dialect.name == 'mysql':
                                    connection.execute(text(
                                        'TRUNCATE TABLE '
                                        'shipping_order_finished_next'
                                    ))
                                    connection.commit()
                                else:
                                    connection.execute(
                                        db.delete(ShippingOrderFinishedNext)
                                    )
                                    connection.commit()
                                connection.execute(
                                    db.update(
                                        ShippingOrderFinishedGenerationNext
                                    )
                                    .where(
                                        ShippingOrderFinishedGenerationNext.c.id
                                        == _GENERATION_MARKER_ID,
                                    )
                                    .values(
                                        task_id=None,
                                        row_count=None,
                                        published_at=None,
                                    )
                                )
                                connection.commit()
                        finally:
                            _release_resolve_cutover_lock(connection)
                return
            except Exception as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(0.25 * (2 ** attempt))
        raise last_error

    @staticmethod
    def cleanup_retired_full_generation(task_id: str) -> bool:
        """Truncate the old live generation after a successful atomic swap."""
        with db.engine.connect() as connection:
            _acquire_resolve_cutover_lock(connection)
            try:
                live_owner = connection.execute(
                    db.select(
                        ShippingOrderFinishedGeneration.c.task_id
                    ).where(
                        ShippingOrderFinishedGeneration.c.id
                        == _GENERATION_MARKER_ID,
                    )
                ).scalar_one_or_none()
                if live_owner != task_id:
                    return False
                standby_owner = connection.execute(
                    db.select(
                        ShippingOrderFinishedGenerationNext.c.task_id
                    ).where(
                        ShippingOrderFinishedGenerationNext.c.id
                        == _GENERATION_MARKER_ID,
                    )
                ).scalar_one_or_none()
                if standby_owner:
                    standby_status = connection.execute(
                        db.select(ShippingTask.status).where(
                            ShippingTask.id == standby_owner,
                        )
                    ).scalar_one_or_none()
                    if standby_status in (
                        'pending', 'running', 'committing',
                    ):
                        return False
                if connection.dialect.name == 'mysql':
                    connection.execute(text(
                        'TRUNCATE TABLE shipping_order_finished_next'
                    ))
                    connection.commit()
                else:
                    connection.execute(db.delete(
                        ShippingOrderFinishedNext
                    ))
                    connection.commit()
                connection.execute(
                    db.update(ShippingOrderFinishedGenerationNext)
                    .where(
                        ShippingOrderFinishedGenerationNext.c.id
                        == _GENERATION_MARKER_ID,
                    )
                    .values(
                        task_id=None,
                        row_count=None,
                        published_at=None,
                    )
                )
                connection.commit()
                return True
            finally:
                _release_resolve_cutover_lock(connection)

    @staticmethod
    def cleanup_abandoned_resolve_staging():
        """
        Remove private generations left by terminal tasks for over one hour.

        The delay avoids racing a graceful-reload worker that has just been
        marked interrupted but is still unwinding and writing its final chunk.
        """
        cutoff = now_cst() - timedelta(hours=1)
        with db.engine.connect() as connection:
            terminal_ids = set(connection.execute(
                db.select(ShippingTask.id).where(
                    ShippingTask.status.in_(
                        ('done', 'error', 'cancelled', 'interrupted')
                    ),
                    ShippingTask.updated_at < cutoff,
                )
            ).scalars().all())
            private_ids = set(connection.execute(
                db.select(
                    ShippingOrderFinishedStaging.task_id
                ).distinct()
            ).scalars().all())
            private_ids.update(connection.execute(
                db.select(ShippingResolveTarget.task_id).distinct()
            ).scalars().all())
            existing_ids = set()
            if private_ids:
                existing_ids = set(connection.execute(
                    db.select(ShippingTask.id).where(
                        ShippingTask.id.in_(private_ids)
                    )
                ).scalars().all())
            orphan_ids = private_ids - existing_ids
        for task_id in terminal_ids | orphan_ids:
            ShippingRepository.cleanup_resolve_staging(task_id)

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
        tag_filters   = params.get('tag_filters') or []  # [{category_id, tag_ids?, tag_names?}]

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

        # 财务端「地域/品牌」既兼容原有 tag_ids，也允许直接传 tag_names，
        # 避免人工映射中的新国家/品牌必须先在产品标签表建档才能下钻。
        finance_mapping_filters = []
        product_tag_filters = []
        for tag_filter in tag_filters:
            filter_category_id = tag_filter.get('category_id')
            filter_tag_ids = tag_filter.get('tag_ids') or []
            raw_tag_names = tag_filter.get('tag_names') or []
            if not isinstance(raw_tag_names, (list, tuple, set)):
                raw_tag_names = []
            filter_tag_names = {
                name.strip()
                for name in list(raw_tag_names)[:100]
                if isinstance(name, str) and name.strip() and len(name.strip()) <= 100
            }
            if not filter_category_id:
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
                if filter_tag_ids:
                    product_tag_filters.append(tag_filter)
                continue
            if filter_tag_ids:
                filter_tag_names.update(
                    row[0] for row in db.session.query(ProductTag.name).filter(
                        ProductTag.category_id == filter_category_id,
                        ProductTag.id.in_(filter_tag_ids),
                    ).all()
                )
            if filter_tag_names:
                finance_mapping_filters.append((mapping_field, sorted(filter_tag_names)))

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
        aftersale_ops_sub = db.select(ShippingOperatorType.operator).where(
            ShippingOperatorType.type == 'aftersale',
        )

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
                    ShippingFinanceCustomerMapping.status == 'export',
                    mapping_field.in_(selected_names),
                )
            # 内外销过滤：使用缓存的 ftp_codes 集合，避免 JOIN 产品表
            if needs_trade_filter:
                if source == 'finance':
                    expected_status = 'export' if trade_type == 'foreign' else 'domestic'
                    q = q.filter(ShippingFinanceCustomerMapping.status == expected_status)
                elif ftp_codes:
                    if trade_type == 'domestic':
                        q = q.filter(~sof.finished_code.in_(ftp_codes))
                    elif trade_type == 'foreign':
                        q = q.filter(sof.finished_code.in_(ftp_codes))
                elif trade_type == 'foreign':
                    q = q.filter(db.false())
            if is_finance_mapping_group:
                q = q.filter(
                    ShippingFinanceCustomerMapping.status == 'export',
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

        # 普通维度互斥且完整覆盖过滤后的行，直接汇总 grouped 原始聚合值，
        # 避免对 shipping_order_finished 再执行一次相同过滤/JOIN 的全量扫描。
        # 标签维度可能因多对多 JOIN 扇出，暂时保留独立汇总查询以维持既有口径。
        ordinary_group_by = {
            'date', 'category', 'series', 'model',
            'channel', 'channel_code', 'province', 'city', 'district',
        }
        if group_by in ordinary_group_by:
            summary = {
                'quantity': _f(sum((row.quantity or 0) for row in rows)),
                'return_quantity': _f(sum((row.return_quantity or 0) for row in rows)),
                'actual_quantity': _f(sum((row.actual_quantity or 0) for row in rows)),
            }
        else:
            summary_q = db.session.query(
                func.sum(sof.quantity).label('quantity'),
                func.sum(sof.return_quantity).label('return_quantity'),
                func.sum(sof.actual_quantity).label('actual_quantity'),
            )
            summary_q = _apply_filters(summary_q)
            sr = summary_q.one()
            summary = {
                'quantity': _f(sr.quantity),
                'return_quantity': _f(sr.return_quantity),
                'actual_quantity': _f(sr.actual_quantity),
            }

        return {
            'summary': summary,
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
