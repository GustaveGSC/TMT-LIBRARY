import re
import difflib
from datetime import datetime, timezone, timedelta, date
from collections import defaultdict
from database.base import db
from database.models.aftersale import (
    AftersaleReasonCategory, AftersaleReason, AftersaleKeywordCandidate,
    AftersaleCase, AftersaleCaseReason,
    AftersaleShippingAlias, AftersaleReturnAlias,
    AftersaleShippingIgnoreTerm,
    AftersaleReasonStopword, AftersaleReasonFaultTerm,
    AftersaleReasonComponentTerm, AftersaleReasonShortKeepTerm,
    AftersaleReasonSynonymRule,
)
from database.models.shipping import ShippingRecord, ShippingOperatorType
from database.models.product.category import ProductModel

CST = timezone(timedelta(hours=8))
def now_cst(): return datetime.now(CST).replace(tzinfo=None)


class AftersaleRepository:

    # ── 一级分类 ───────────────────────────────────────────────────────────────

    def get_all_categories(self):
        """按 sort_order 返回所有一级分类"""
        return (
            AftersaleReasonCategory.query
            .order_by(AftersaleReasonCategory.sort_order.asc(),
                      AftersaleReasonCategory.id.asc())
            .all()
        )

    def get_category_by_id(self, category_id):
        return AftersaleReasonCategory.query.get(category_id)

    def create_category(self, name, sort_order=0):
        cat = AftersaleReasonCategory(name=name, sort_order=sort_order or 0)
        db.session.add(cat)
        db.session.commit()
        return cat

    def update_category(self, category_id, name, sort_order=None):
        cat = AftersaleReasonCategory.query.get(category_id)
        if not cat:
            return None
        cat.name = name
        if sort_order is not None:
            cat.sort_order = sort_order
        db.session.commit()
        return cat

    def delete_category(self, category_id):
        """删除前检查是否有二级原因关联；有则拒绝删除"""
        cat = AftersaleReasonCategory.query.get(category_id)
        if not cat:
            return False, 0
        reason_count = AftersaleReason.query.filter_by(category_id=category_id).count()
        if reason_count > 0:
            return False, reason_count
        db.session.delete(cat)
        db.session.commit()
        return True, 0

    def get_category_reason_count(self, category_id):
        return AftersaleReason.query.filter_by(category_id=category_id).count()

    # ── 二级原因 ───────────────────────────────────────────────────────────────

    def get_all_reasons(self):
        """按 sort_order 返回所有二级原因"""
        return (
            AftersaleReason.query
            .order_by(AftersaleReason.sort_order.asc(),
                      AftersaleReason.id.asc())
            .all()
        )

    def get_reason_by_id(self, reason_id):
        return AftersaleReason.query.get(reason_id)

    def create_reason(self, name, category_id, keywords, sort_order):
        reason = AftersaleReason(
            name=name,
            category_id=category_id,
            keywords=keywords or '',
            sort_order=sort_order or 0,
        )
        db.session.add(reason)
        db.session.commit()
        return reason

    def update_reason(self, reason_id, name, category_id, keywords, sort_order):
        reason = AftersaleReason.query.get(reason_id)
        if not reason:
            return None
        reason.name        = name
        reason.category_id = category_id
        reason.keywords    = keywords or ''
        reason.sort_order  = sort_order if sort_order is not None else reason.sort_order
        db.session.commit()
        return reason

    def delete_reason(self, reason_id):
        reason = AftersaleReason.query.get(reason_id)
        if not reason:
            return False, 0
        usage_count = AftersaleCaseReason.query.filter_by(reason_id=reason_id).count()
        if usage_count > 0:
            return False, usage_count
        db.session.delete(reason)
        db.session.commit()
        return True, 0

    def get_reason_usage(self, reason_id):
        return AftersaleCaseReason.query.filter_by(reason_id=reason_id).count()


    # ── 待处理订单 ──────────────────────────────────────────────────────────

    def get_pending_orders(self, page=1, page_size=50, search=None, date_start=None, date_end=None):
        """
        查询属于售后操作人、且尚未创建 aftersale_case 的订单，按 ecommerce_order_no 聚合。
        返回 (items, total_count)
        """
        # 售后操作人子查询
        aftersale_ops = (
            db.session.query(ShippingOperatorType.operator)
            .filter_by(type='aftersale')
            .subquery()
            .select()
        )

        # 已创建工单的订单号子查询
        existing_orders = (
            db.session.query(AftersaleCase.ecommerce_order_no)
            .subquery()
            .select()
        )

        # 基础查询：只取售后操作人、且未建工单的记录，按订单聚合
        from sqlalchemy import func
        q = (
            db.session.query(
                ShippingRecord.ecommerce_order_no,
                func.min(ShippingRecord.shipped_date).label('shipped_date'),
                func.min(ShippingRecord.channel_name).label('channel_name'),
                func.min(ShippingRecord.operator).label('operator'),
                func.min(ShippingRecord.province).label('province'),
                func.min(ShippingRecord.city).label('city'),
                func.min(ShippingRecord.district).label('district'),
                func.min(ShippingRecord.seller_remark).label('seller_remark'),
                func.min(ShippingRecord.buyer_remark).label('buyer_remark'),
                func.count(ShippingRecord.id).label('line_count'),
            )
            .filter(ShippingRecord.operator.in_(aftersale_ops))
            .filter(ShippingRecord.ecommerce_order_no.notin_(existing_orders))
            .filter(ShippingRecord.ecommerce_order_no.isnot(None))
        )

        if search:
            q = q.filter(ShippingRecord.ecommerce_order_no.like(f'%{search}%'))
        if date_start:
            q = q.filter(ShippingRecord.shipped_date >= date_start)
        if date_end:
            q = q.filter(ShippingRecord.shipped_date <= date_end)

        q = q.group_by(ShippingRecord.ecommerce_order_no)
        total = q.count()

        rows = (
            q.order_by(func.min(ShippingRecord.shipped_date).asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        # 聚合每个订单的物料列表
        items = []
        for row in rows:
            products = self._get_order_products(row.ecommerce_order_no)
            items.append({
                'ecommerce_order_no': row.ecommerce_order_no,
                'shipped_date':       row.shipped_date.strftime('%Y-%m-%d') if row.shipped_date else None,
                'channel_name':       row.channel_name,
                'operator':           row.operator,
                'province':           row.province,
                'city':               row.city,
                'district':           row.district,
                'seller_remark':      row.seller_remark,
                'buyer_remark':       row.buyer_remark,
                'line_count':         row.line_count,
                'products':           products,
            })

        return items, total

    def get_pending_count(self):
        """快速获取待处理订单总数"""
        aftersale_ops = (
            db.session.query(ShippingOperatorType.operator)
            .filter_by(type='aftersale')
            .subquery()
        )
        existing_orders = (
            db.session.query(AftersaleCase.ecommerce_order_no)
            .subquery()
        )
        from sqlalchemy import func, distinct
        return (
            db.session.query(func.count(distinct(ShippingRecord.ecommerce_order_no)))
            .filter(ShippingRecord.operator.in_(aftersale_ops))
            .filter(ShippingRecord.ecommerce_order_no.notin_(existing_orders))
            .filter(ShippingRecord.ecommerce_order_no.isnot(None))
            .scalar()
        ) or 0

    def _get_order_products(self, order_no):
        """聚合订单下所有物料（按 product_code 分组，quantity 累加）"""
        from sqlalchemy import func
        rows = (
            db.session.query(
                ShippingRecord.product_code,
                func.min(ShippingRecord.product_name).label('product_name'),
                func.sum(ShippingRecord.quantity).label('quantity'),
            )
            .filter(ShippingRecord.ecommerce_order_no == order_no)
            .group_by(ShippingRecord.product_code)
            .all()
        )
        return [
            {'code': r.product_code, 'name': r.product_name, 'quantity': float(r.quantity or 0)}
            for r in rows
        ]

    # ── 工单 CRUD ──────────────────────────────────────────────────────────

    def get_case_by_order_no(self, order_no):
        return AftersaleCase.query.filter_by(ecommerce_order_no=order_no).first()

    def get_case_by_id(self, case_id):
        return AftersaleCase.query.get(case_id)

    # 允许排序的字段白名单
    _SORT_FIELDS = {
        'shipped_date':        AftersaleCase.shipped_date,
        'days_since_purchase': None,   # 子查询排序，特殊处理
        'channel_name':        AftersaleCase.channel_name,
        'province':            AftersaleCase.province,
        'ecommerce_order_no':  AftersaleCase.ecommerce_order_no,
    }

    def get_cases(self, page=1, page_size=50,
                  status=None, date_start=None, date_end=None,
                  reason_id=None, channel_name=None, province=None, city=None,
                  district=None, reason_category=None, reason_name=None,
                  shipping_alias=None, return_alias=None, model_code=None, search=None,
                  sort_by=None, sort_order='desc'):
        """分页查询工单，支持多维筛选和服务端排序"""
        from sqlalchemy import func as sqlfunc
        q = AftersaleCase.query

        if status:
            q = q.filter(AftersaleCase.status == status)
        if date_start:
            q = q.filter(AftersaleCase.shipped_date >= date_start)
        if date_end:
            q = q.filter(AftersaleCase.shipped_date <= date_end)
        if channel_name:
            q = q.filter(AftersaleCase.channel_name == channel_name)
        if province:
            q = q.filter(AftersaleCase.province == province)
        if city:
            q = q.filter(AftersaleCase.city == city)
        if district:
            q = q.filter(AftersaleCase.district == district)
        if search:
            q = q.filter(AftersaleCase.ecommerce_order_no.like(f'%{search}%'))
        if reason_id:
            sub = db.session.query(AftersaleCaseReason.case_id).filter_by(reason_id=reason_id).subquery()
            q = q.filter(AftersaleCase.id.in_(sub))

        # 经由 AftersaleCaseReason 的子查询筛选
        if reason_category:
            sub = (db.session.query(AftersaleCaseReason.case_id)
                   .join(AftersaleReason, AftersaleCaseReason.reason_id == AftersaleReason.id)
                   .join(AftersaleReasonCategory, AftersaleReason.category_id == AftersaleReasonCategory.id)
                   .filter(AftersaleReasonCategory.name == reason_category)
                   .subquery())
            q = q.filter(AftersaleCase.id.in_(sub))
        if reason_name:
            sub = (db.session.query(AftersaleCaseReason.case_id)
                   .join(AftersaleReason, AftersaleCaseReason.reason_id == AftersaleReason.id)
                   .filter(AftersaleReason.name == reason_name)
                   .subquery())
            q = q.filter(AftersaleCase.id.in_(sub))
        if shipping_alias:
            sub = (db.session.query(AftersaleCaseReason.case_id)
                   .filter(AftersaleCaseReason.shipping_alias_id == shipping_alias)
                   .subquery())
            q = q.filter(AftersaleCase.id.in_(sub))
        if return_alias:
            sub = (db.session.query(AftersaleCaseReason.case_id)
                   .filter(AftersaleCaseReason.return_alias_id == return_alias)
                   .subquery())
            q = q.filter(AftersaleCase.id.in_(sub))
        if model_code:
            sub = (db.session.query(AftersaleCaseReason.case_id)
                   .join(ProductModel, AftersaleCaseReason.model_id == ProductModel.id)
                   .filter(ProductModel.model_code == model_code)
                   .subquery())
            q = q.filter(AftersaleCase.id.in_(sub))

        total = q.count()

        # 排序：sort_by 必须在白名单内，默认按售后日期倒序
        if sort_by == 'days_since_purchase':
            from sqlalchemy import func as sqlfunc
            days_sub = (
                db.session.query(sqlfunc.min(AftersaleCaseReason.days_since_purchase))
                .filter(AftersaleCaseReason.case_id == AftersaleCase.id)
                .correlate(AftersaleCase)
                .scalar_subquery()
            )
            order_expr = days_sub.asc() if sort_order == 'asc' else days_sub.desc()
        else:
            sort_col   = self._SORT_FIELDS.get(sort_by) or AftersaleCase.shipped_date
            order_expr = sort_col.asc() if sort_order == 'asc' else sort_col.desc()

        items = (
            q.order_by(order_expr, AftersaleCase.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return items, total

    def get_filter_options(self):
        """返回各列的可选筛选值（并行执行减少往返）"""
        from sqlalchemy import text as satext

        def q(sql):
            return sorted([
                r[0] for r in db.session.execute(satext(sql)).fetchall()
                if r[0] is not None and r[0] != ''
            ])

        channels  = q("SELECT DISTINCT channel_name FROM aftersale_case WHERE channel_name IS NOT NULL AND channel_name != '' ORDER BY channel_name")
        provinces = q("SELECT DISTINCT province    FROM aftersale_case WHERE province    IS NOT NULL AND province    != '' ORDER BY province")
        cities    = q("SELECT DISTINCT city        FROM aftersale_case WHERE city        IS NOT NULL AND city        != '' ORDER BY city")
        districts = q("SELECT DISTINCT district    FROM aftersale_case WHERE district    IS NOT NULL AND district    != '' ORDER BY district")

        from database.models.aftersale import AftersaleShippingAlias, AftersaleReturnAlias
        ship_aliases = [
            {'id': r.id, 'name': r.name}
            for r in AftersaleShippingAlias.query.order_by(AftersaleShippingAlias.sort_order, AftersaleShippingAlias.name).all()
        ]
        return_aliases = [
            {'id': r.id, 'name': r.name}
            for r in AftersaleReturnAlias.query.order_by(AftersaleReturnAlias.sort_order, AftersaleReturnAlias.name).all()
        ]

        reason_cats = q("""
            SELECT DISTINCT c.name FROM aftersale_reason_category c
            JOIN aftersale_reason r ON r.category_id = c.id
            JOIN aftersale_case_reason cr ON cr.reason_id = r.id
            ORDER BY c.name
        """)
        reason_names = q("""
            SELECT DISTINCT r.name FROM aftersale_reason r
            JOIN aftersale_case_reason cr ON cr.reason_id = r.id
            ORDER BY r.name
        """)
        model_codes = q("""
            SELECT DISTINCT m.model_code FROM product_model m
            JOIN aftersale_case_reason cr ON cr.model_id = m.id
            WHERE m.model_code IS NOT NULL
            ORDER BY m.model_code
        """)

        return {
            'channels':          channels,
            'provinces':         provinces,
            'cities':            cities,
            'districts':         districts,
            'reason_categories': reason_cats,
            'reason_names':      reason_names,
            'shipping_aliases':  ship_aliases,
            'return_aliases':    return_aliases,
            'model_codes':       model_codes,
        }

    def confirm_case(self, order_no, products, seller_remark, buyer_remark,
                     shipped_date, operator, channel_name, province, reasons_data,
                     city=None, district=None):
        """
        创建或更新工单（status→confirmed），批量写入 reasons。
        reasons_data: [{reason_id?, custom_reason?, model_id?, shipping_material_alias?, aftersale_material_alias?}]
        """
        case = AftersaleCase.query.filter_by(ecommerce_order_no=order_no).first()
        if not case:
            case = AftersaleCase(
                ecommerce_order_no=order_no,
                products=products,
                seller_remark=seller_remark,
                buyer_remark=buyer_remark,
                shipped_date=shipped_date,
                operator=operator,
                channel_name=channel_name,
                province=province,
                city=city,
                district=district,
            )
            db.session.add(case)
            db.session.flush()
        else:
            case.products      = products
            case.seller_remark = seller_remark
            case.buyer_remark  = buyer_remark
            case.shipped_date  = shipped_date
            case.operator      = operator
            case.channel_name  = channel_name
            case.province      = province
            case.city          = city
            case.district      = district
        case.status       = 'confirmed'
        case.processed_at = now_cst()

        # 清除旧 reasons，重新写入
        AftersaleCaseReason.query.filter_by(case_id=case.id).delete()
        reason_ids_used = set()
        for rd in reasons_data:
            # 解析每条内容的购买日期
            item_purchase_date = None
            if rd.get('purchase_date'):
                try:
                    item_purchase_date = date.fromisoformat(rd['purchase_date'])
                except ValueError:
                    pass
            reason_id = rd.get('reason_id') or None
            # reason_category_id 始终有值：
            # 选了库中原因 → 从 reason 本身取 category_id；自定义原因 → 用前端传的分类
            if reason_id:
                reason_obj = AftersaleReason.query.get(reason_id)
                reason_category_id = reason_obj.category_id if reason_obj else rd.get('reason_category_id')
            else:
                reason_category_id = rd.get('reason_category_id') or None

            # 每条内容单独计算售后间隔天数
            item_days = None
            if shipped_date and item_purchase_date:
                item_days = (shipped_date - item_purchase_date).days

            cr = AftersaleCaseReason(
                case_id             = case.id,
                reason_id           = reason_id,
                reason_category_id  = reason_category_id,
                model_id            = rd.get('model_id'),
                shipping_alias_id   = rd.get('shipping_alias_id') or None,
                return_alias_id     = rd.get('return_alias_id')   or None,
                purchase_date       = item_purchase_date,
                days_since_purchase = item_days,
            )
            db.session.add(cr)
            if rd.get('reason_id'):
                reason_ids_used.add(rd['reason_id'])

        # 递增 use_count + 自动合并关键词
        if reason_ids_used:
            AftersaleReason.query.filter(
                AftersaleReason.id.in_(reason_ids_used)
            ).update({'use_count': AftersaleReason.use_count + 1},
                     synchronize_session='fetch')
            self._auto_update_reason_keywords(seller_remark, reason_ids_used, buyer_remark)

        # 自动将简称关键词合并到简称库（通过 ID 查找对象）
        product_names = [p.get('name') for p in (products or []) if p.get('name')]
        for rd in reasons_data:
            if rd.get('shipping_alias_id'):
                self.upsert_shipping_alias_by_id(rd['shipping_alias_id'], product_names)
            if rd.get('return_alias_id'):
                self.upsert_return_alias_by_id(rd['return_alias_id'], seller_remark, buyer_remark)

        db.session.commit()
        return case

    def update_case(self, case_id, reasons_data,
                    assigned_models=None, shipping_materials=None, aftersale_materials=None):
        """更新已有工单的 reasons"""
        case = AftersaleCase.query.get(case_id)
        if not case:
            return None

        # 先撤回旧 reasons 的 use_count
        old_reason_ids = {
            cr.reason_id
            for cr in AftersaleCaseReason.query.filter_by(case_id=case_id).all()
            if cr.reason_id
        }
        if old_reason_ids:
            AftersaleReason.query.filter(
                AftersaleReason.id.in_(old_reason_ids)
            ).update({'use_count': AftersaleReason.use_count - 1},
                     synchronize_session='fetch')

        # 删旧写新
        AftersaleCaseReason.query.filter_by(case_id=case_id).delete()
        new_reason_ids = set()
        for rd in reasons_data:
            cr = AftersaleCaseReason(
                case_id            = case_id,
                reason_id          = rd.get('reason_id'),
                reason_category_id = rd.get('reason_category_id') if not rd.get('reason_id') else None,
                model_id           = rd.get('model_id'),
                shipping_alias_id  = rd.get('shipping_alias_id') or None,
                return_alias_id    = rd.get('return_alias_id')   or None,
            )
            db.session.add(cr)
            if rd.get('reason_id'):
                new_reason_ids.add(rd['reason_id'])

        if new_reason_ids:
            AftersaleReason.query.filter(
                AftersaleReason.id.in_(new_reason_ids)
            ).update({'use_count': AftersaleReason.use_count + 1},
                     synchronize_session='fetch')
            self._auto_update_reason_keywords(case.seller_remark, new_reason_ids, case.buyer_remark)

        # 仅当参数非 None 时覆盖（None 表示调用方未传，保留原值）
        case.processed_at = now_cst()
        db.session.commit()
        return case

    def ignore_case(self, order_no):
        """将待处理订单直接标记为忽略（新建 case 并置 ignored）"""
        case = AftersaleCase.query.filter_by(ecommerce_order_no=order_no).first()
        if not case:
            # 从 shipping_record 拉取基础信息
            from sqlalchemy import func
            row = (
                db.session.query(
                    func.min(ShippingRecord.shipped_date).label('shipped_date'),
                    func.min(ShippingRecord.channel_name).label('channel_name'),
                    func.min(ShippingRecord.operator).label('operator'),
                    func.min(ShippingRecord.province).label('province'),
                    func.min(ShippingRecord.seller_remark).label('seller_remark'),
                    func.min(ShippingRecord.buyer_remark).label('buyer_remark'),
                )
                .filter(ShippingRecord.ecommerce_order_no == order_no)
                .first()
            )
            products = self._get_order_products(order_no)
            case = AftersaleCase(
                ecommerce_order_no=order_no,
                products=products,
                seller_remark=row.seller_remark if row else None,
                buyer_remark=row.buyer_remark if row else None,
                shipped_date=row.shipped_date if row else None,
                operator=row.operator if row else None,
                channel_name=row.channel_name if row else None,
                province=row.province if row else None,
                status='ignored',
                processed_at=now_cst(),
            )
            db.session.add(case)
        else:
            case.status       = 'ignored'
            case.processed_at = now_cst()
        db.session.commit()
        return case

    # ── 关键词自动提取 ───────────────────────────────────────────────────────

    # 关键词晋升阈值：候选词出现 N 次后才写入 keywords
    _KW_PROMOTE_THRESHOLD = 3
    # 关键词晋升的最低质量分（0~1）
    _KW_MIN_QUALITY_SCORE = 0.45
    # 每个原因最多保留关键词数
    _KW_MAX_TOTAL = 30
    # 跨原因高频抑制：同一候选词在 >=N 个原因候选池出现时不晋升
    _KW_GLOBAL_HOT_THRESHOLD = 3
    # auto_match 历史相似度阶段上限（CPU 防护）
    _AUTO_MATCH_HISTORY_LIMIT = 180
    # auto_match 进入历史相似度阶段的最低关键词命中候选数
    _AUTO_MATCH_MIN_KEYWORD_CANDIDATES = 2
    # 候选关键词长度边界
    _KW_MIN_LEN = 2
    _KW_MAX_LEN = 18
    _RULE_CACHE = None
    _RULE_CACHE_TS = None
    _RULE_CACHE_TTL_SEC = 60

    @classmethod
    def _invalidate_reason_rule_cache(cls):
        cls._RULE_CACHE = None
        cls._RULE_CACHE_TS = None

    @classmethod
    def _load_reason_rules_from_db(cls):
        stopwords = {
            (r.term or '').strip().lower()
            for r in AftersaleReasonStopword.query
            .filter(AftersaleReasonStopword.enabled.is_(True))
            .all()
            if (r.term or '').strip()
        }
        fault_terms = {
            (r.term or '').strip().lower()
            for r in AftersaleReasonFaultTerm.query
            .filter(AftersaleReasonFaultTerm.enabled.is_(True))
            .all()
            if (r.term or '').strip()
        }
        component_terms = {
            (r.term or '').strip().lower()
            for r in AftersaleReasonComponentTerm.query
            .filter(AftersaleReasonComponentTerm.enabled.is_(True))
            .all()
            if (r.term or '').strip()
        }
        short_keep_terms = {
            (r.term or '').strip().lower()
            for r in AftersaleReasonShortKeepTerm.query
            .filter(AftersaleReasonShortKeepTerm.enabled.is_(True))
            .all()
            if (r.term or '').strip()
        }
        synonym_rows = (
            AftersaleReasonSynonymRule.query
            .filter(AftersaleReasonSynonymRule.enabled.is_(True))
            .order_by(AftersaleReasonSynonymRule.sort_order.asc(), AftersaleReasonSynonymRule.id.asc())
            .all()
        )
        synonyms = [
            ((r.pattern or '').strip(), (r.replacement or '').strip(), bool(r.is_regex))
            for r in synonym_rows
            if (r.pattern or '').strip() and (r.replacement or '').strip()
        ]
        return {
            'stopwords': stopwords,
            'fault_terms': fault_terms,
            'component_terms': component_terms,
            'short_keep_terms': short_keep_terms,
            'synonyms': synonyms,
        }

    @classmethod
    def _get_reason_rules(cls):
        now = now_cst()
        if cls._RULE_CACHE is not None and cls._RULE_CACHE_TS is not None:
            if (now - cls._RULE_CACHE_TS).total_seconds() <= cls._RULE_CACHE_TTL_SEC:
                return cls._RULE_CACHE
        cls._RULE_CACHE = cls._load_reason_rules_from_db()
        cls._RULE_CACHE_TS = now
        return cls._RULE_CACHE

    def get_reason_keyword_rules(self):
        rules = self._load_reason_rules_from_db()
        return {
            'stopwords': sorted(rules['stopwords']),
            'fault_terms': sorted(rules['fault_terms']),
            'component_terms': sorted(rules['component_terms']),
            'short_keep_terms': sorted(rules['short_keep_terms']),
            'synonyms': [
                {'pattern': p, 'replacement': repl, 'is_regex': bool(is_regex)}
                for p, repl, is_regex in rules['synonyms']
            ],
        }

    def replace_reason_keyword_rules(self, stopwords, fault_terms, component_terms, synonyms,
                                     short_keep_terms=None):
        AftersaleReasonStopword.query.delete()
        AftersaleReasonFaultTerm.query.delete()
        AftersaleReasonComponentTerm.query.delete()
        AftersaleReasonShortKeepTerm.query.delete()
        AftersaleReasonSynonymRule.query.delete()

        for i, term in enumerate(stopwords or []):
            t = (term or '').strip()
            if t:
                db.session.add(AftersaleReasonStopword(term=t, sort_order=i))
        for i, term in enumerate(fault_terms or []):
            t = (term or '').strip()
            if t:
                db.session.add(AftersaleReasonFaultTerm(term=t, sort_order=i))
        for i, term in enumerate(component_terms or []):
            t = (term or '').strip()
            if t:
                db.session.add(AftersaleReasonComponentTerm(term=t, sort_order=i))
        for i, term in enumerate(short_keep_terms or []):
            t = (term or '').strip()
            if t:
                db.session.add(AftersaleReasonShortKeepTerm(term=t, sort_order=i))
        for i, row in enumerate(synonyms or []):
            pattern = (row.get('pattern') or '').strip()
            replacement = (row.get('replacement') or '').strip()
            if pattern and replacement:
                db.session.add(AftersaleReasonSynonymRule(
                    pattern=pattern,
                    replacement=replacement,
                    is_regex=bool(row.get('is_regex', True)),
                    sort_order=i,
                ))
        db.session.commit()
        self._invalidate_reason_rule_cache()

    @classmethod
    def _is_generic_keyword(cls, kw):
        """是否属于泛化/低信息词。"""
        k = (kw or '').strip().lower()
        if not k:
            return True
        rules = cls._get_reason_rules()
        if k in rules['stopwords']:
            return True
        # 纯数字、数字+单位、纯字母编号
        if re.fullmatch(r'\d+[a-zA-Z%cmkmg]*', k):
            return True
        # 高频无区分短词（如「问题」「补偿」）；例外词由词典表 short_keep_terms 配置
        if len(k) <= 2 and k not in rules['short_keep_terms']:
            return True
        return False

    @classmethod
    def _keyword_quality_score(cls, kw):
        """关键词质量分（0~1），用于晋升与匹配加权。"""
        k = (kw or '').strip().lower()
        if not k:
            return 0.0
        if cls._is_generic_keyword(k):
            return 0.0
        # 长度评分（2~8 字最佳）
        ln = len(k)
        if ln < cls._KW_MIN_LEN or ln > cls._KW_MAX_LEN:
            return 0.0
        length_score = 1.0 if ln <= 8 else max(0.4, 1.0 - (ln - 8) * 0.08)
        # 中文占比越高越倾向业务语义词；英文/编号词适度降权
        cn_count = len(re.findall(r'[\u4e00-\u9fff]', k))
        cn_ratio = cn_count / ln if ln else 0
        ratio_score = 0.6 + 0.4 * cn_ratio
        return round(length_score * ratio_score, 3)

    @classmethod
    def _normalize_reason_text(cls, text):
        """原因学习/匹配用文本归一化：去日期数字噪声 + 同义词收敛。"""
        if not text:
            return ''
        t = text.lower()
        # 日期与纯数字归一，降低型号/时间差异对学习的影响
        t = cls._DATE_RE.sub(' ', t)
        t = re.sub(r'\d+(?:\.\d+)?', ' ', t)
        for pattern, repl, is_regex in cls._get_reason_rules()['synonyms']:
            if is_regex:
                t = re.sub(pattern, repl, t)
            else:
                t = t.replace(pattern, repl)
        t = re.sub(r'\s+', ' ', t).strip()
        return t

    @classmethod
    def _canonicalize_keyword(cls, kw):
        """将关键词归一为可复用 token。"""
        t = cls._normalize_reason_text(kw)
        return t.replace(' ', '')

    @classmethod
    def _extract_keywords_from_text(cls, text):
        """
        从备注文本中提取候选关键词。
        按标点/空白切段，过滤纯数字和过短片段（<2字）。
        段长 ≤ 10字：直接作为一个关键词。
        段长 > 10字：取所有4字 n-gram，避免单段过长无法命中。
        """
        normalized_text = cls._normalize_reason_text(text)
        if not normalized_text:
            return []
        segments = re.split(r'[，,。.！!？?、\s；;：:【】\[\]()（）""\'\'/\\|]+', normalized_text)
        seen = set()
        result = []
        for seg in segments:
            seg = cls._canonicalize_keyword(seg.strip())
            if len(seg) < cls._KW_MIN_LEN or seg.isdigit():
                continue
            # 跳过日期类片段（如 2024-01-01、2024年1月、01/01 等）
            if AftersaleRepository._DATE_RE.fullmatch(seg):
                continue
            if len(seg) <= 10:
                if cls._keyword_quality_score(seg) < cls._KW_MIN_QUALITY_SCORE:
                    continue
                if seg not in seen:
                    seen.add(seg)
                    result.append(seg)
            else:
                for i in range(len(seg) - 3):
                    gram = cls._canonicalize_keyword(seg[i:i + 4])
                    if gram.isdigit() or gram in seen:
                        continue
                    if cls._keyword_quality_score(gram) < cls._KW_MIN_QUALITY_SCORE:
                        continue
                    seen.add(gram)
                    result.append(gram)
        return result

    @staticmethod
    def _subtract_buyer_remark(seller_remark, buyer_remark):
        """从商家备注中去掉买家留言里出现的内容，避免提取无关关键词。
        若买家留言是商家备注的子串，直接替换为空；否则按词（分隔符切段）逐段去除。"""
        if not buyer_remark or not seller_remark:
            return seller_remark
        # 情况1：买家留言完整包含在商家备注中，直接删除
        if buyer_remark in seller_remark:
            return seller_remark.replace(buyer_remark, ' ')
        # 情况2：按分隔符切买家留言为段，逐段从商家备注中去除（>=4字的段才处理，避免误删）
        buyer_segs = re.split(r'[，,。.！!？?、\s；;：:【】\[\]()（）""\'\'/\\|]+', buyer_remark)
        result = seller_remark
        for seg in buyer_segs:
            seg = seg.strip()
            if len(seg) >= 4 and seg in result:
                result = result.replace(seg, ' ')
        return result

    def _auto_update_reason_keywords(self, seller_remark, reason_ids, buyer_remark=None):
        """
        提交工单时更新候选词频池，达到阈值的候选词晋升到原因 keywords。
        流程：
          1. 从 seller_remark 中去除 buyer_remark 重复内容，再提取 n-gram 候选词
          2. 对每个 reason_id，upsert aftersale_keyword_candidate（count+1）
          3. count >= 阈值 且 尚未在 keywords 中 → 晋升，并从候选池删除
        """
        if not seller_remark or not reason_ids:
            return
        effective_remark = self._subtract_buyer_remark(seller_remark, buyer_remark)
        new_kws = self._extract_keywords_from_text(effective_remark)
        if not new_kws:
            return

        reasons = {r.id: r for r in AftersaleReason.query.filter(
            AftersaleReason.id.in_(reason_ids)
        ).all()}

        reason_id_list = list(reasons.keys())
        if not reason_id_list:
            return

        existing_candidates = (
            AftersaleKeywordCandidate.query
            .filter(AftersaleKeywordCandidate.reason_id.in_(reason_id_list))
            .filter(AftersaleKeywordCandidate.keyword.in_(new_kws))
            .all()
        )
        candidate_map = {(c.reason_id, c.keyword): c for c in existing_candidates}
        to_check_spread = set()
        promote_map = defaultdict(set)

        for rid, reason in reasons.items():
            existing_kws = set(k.strip() for k in (reason.keywords or '').split(',') if k.strip())
            for kw in new_kws:
                if kw in existing_kws:
                    continue
                key = (rid, kw)
                candidate = candidate_map.get(key)
                if candidate:
                    candidate.count += 1
                else:
                    candidate = AftersaleKeywordCandidate(reason_id=rid, keyword=kw, count=1)
                    db.session.add(candidate)
                    candidate_map[key] = candidate
                if candidate.count >= self._KW_PROMOTE_THRESHOLD and self._keyword_quality_score(kw) >= self._KW_MIN_QUALITY_SCORE:
                    to_check_spread.add(kw)
                    promote_map[rid].add(kw)

        spread_map = {}
        if to_check_spread:
            spread_rows = (
                db.session.query(
                    AftersaleKeywordCandidate.keyword,
                    db.func.count(db.func.distinct(AftersaleKeywordCandidate.reason_id)).label('spread'),
                )
                .filter(AftersaleKeywordCandidate.keyword.in_(list(to_check_spread)))
                .group_by(AftersaleKeywordCandidate.keyword)
                .all()
            )
            spread_map = {row.keyword: int(row.spread or 0) for row in spread_rows}

        for rid, kws in promote_map.items():
            reason = reasons.get(rid)
            if not reason:
                continue
            kw_list = [k for k in (reason.keywords or '').split(',') if k.strip()]
            for kw in kws:
                if spread_map.get(kw, 0) >= self._KW_GLOBAL_HOT_THRESHOLD:
                    continue
                if kw not in kw_list and len(kw_list) < self._KW_MAX_TOTAL:
                    kw_list.append(kw)
                candidate = candidate_map.get((rid, kw))
                if candidate:
                    db.session.delete(candidate)
            reason.keywords = ','.join(kw_list)

    # ── 自动匹配 ────────────────────────────────────────────────────────────

    def auto_match(self, text):
        """
        两阶段自动匹配，返回按置信度降序排列的 Top5 建议。
        阶段1：关键词库匹配
        阶段2：历史案例相似度（difflib）
        """
        if not text or not text.strip():
            return []

        text_lower = self._normalize_reason_text(text)
        scores = {}   # reason_id -> score details

        def ensure_reason_score(reason_id, name, category_name):
            if reason_id not in scores:
                scores[reason_id] = {
                    'reason_id': reason_id,
                    'name': name,
                    'category_name': category_name,
                    'keyword_score': 0.0,
                    'history_score': 0.0,
                    'total_score': 0.0,
                    'matched_keywords': [],
                }
            return scores[reason_id]

        # 阶段1：关键词库匹配
        reasons = AftersaleReason.query.all()
        rules = self._get_reason_rules()
        for r in reasons:
            if not r.keywords:
                continue
            kws = [k.strip() for k in r.keywords.split(',') if k.strip()]
            if not kws:
                continue
            strong_hits = []
            for kw in kws:
                kw_norm = self._canonicalize_keyword(kw)
                if not kw_norm:
                    continue
                sim = self._text_sim(text_lower, kw_norm)
                direct_hit = kw_norm in text_lower
                if sim < 0.45:
                    if not direct_hit:
                        continue
                quality = self._keyword_quality_score(kw_norm)
                if quality <= 0:
                    continue
                # 强语义关键词放大，泛化词显著降权
                base = max(sim, 0.6 if direct_hit else sim)
                weight = base * (0.55 + 0.45 * quality)
                if self._is_generic_keyword(kw_norm):
                    weight *= 0.4
                core_hit = any(t in kw_norm and t in text_lower for t in rules['fault_terms'])
                comp_hit = any(t in kw_norm and t in text_lower for t in rules['component_terms'])
                strong_hits.append({'kw': kw_norm, 'weight': weight, 'sim': sim, 'core_hit': core_hit, 'comp_hit': comp_hit})

            if strong_hits:
                item = ensure_reason_score(
                    r.id,
                    r.name,
                    r.category_obj.name if r.category_obj else None
                )
                core_hits = sum(1 for h in strong_hits if h['core_hit'])
                comp_hits = sum(1 for h in strong_hits if h['comp_hit'])
                # 无核心故障语义命中且仅单点弱命中时，跳过，避免误判
                if core_hits == 0 and len(strong_hits) < 2:
                    continue
                keyword_score = sum(h['weight'] for h in strong_hits)
                coverage = len(strong_hits) / len(kws)
                # 覆盖率作为次级增益，避免单词命中直接冲顶
                keyword_score *= (0.75 + 0.25 * coverage)
                keyword_score *= (1.0 + min(core_hits, 2) * 0.15 + min(comp_hits, 2) * 0.08)
                item['keyword_score'] = round(max(item['keyword_score'], keyword_score), 4)
                item['matched_keywords'] = sorted(
                    {h['kw'] for h in strong_hits},
                    key=lambda k: -max(h['weight'] for h in strong_hits if h['kw'] == k)
                )[:6]

        # 阶段2：历史案例相似度（CPU 防护）
        # 仅当关键词候选不足时再启动历史比对，避免每次都跑 difflib 全量扫描。
        keyword_hits = sum(1 for v in scores.values() if v.get('keyword_score', 0) > 0)
        if keyword_hits < self._AUTO_MATCH_MIN_KEYWORD_CANDIDATES:
            from sqlalchemy.orm import selectinload
            confirmed_cases = (
                AftersaleCase.query
                .filter_by(status='confirmed')
                .filter(AftersaleCase.seller_remark.isnot(None))
                .options(
                    selectinload(AftersaleCase.case_reasons)
                    .selectinload(AftersaleCaseReason.reason)
                    .selectinload(AftersaleReason.category_obj)
                )
                .order_by(AftersaleCase.processed_at.desc())
                .limit(self._AUTO_MATCH_HISTORY_LIMIT)
                .all()
            )

            def _strip_num(t):
                return re.sub(r'\d{4}[\.\-/]\d{1,2}[\.\-/]\d{1,2}', '', t).strip()  # 仅剥离日期

            # 控制 difflib 输入长度，防止长文本高 CPU
            left = _strip_num(text_lower)[:80]
            if left:
                for case in confirmed_cases:
                    if not case.seller_remark:
                        continue
                    right = _strip_num(case.seller_remark.lower())[:80]
                    if not right:
                        continue
                    ratio = difflib.SequenceMatcher(None, left, right).ratio()
                    if ratio < 0.3:
                        continue
                    for cr in case.case_reasons:
                        if not cr.reason_id:
                            continue
                        item = ensure_reason_score(
                            cr.reason_id,
                            cr.reason.name if cr.reason else '',
                            cr.reason.category_obj.name if cr.reason and cr.reason.category_obj else None
                        )
                        item['history_score'] = round(max(item['history_score'], ratio), 4)

        # 统一融合与过滤
        results = []
        for item in scores.values():
            kw_score = item['keyword_score']
            hs_score = item['history_score']
            if kw_score <= 0 and hs_score < 0.45:
                continue
            total = kw_score + hs_score * 0.55
            if kw_score <= 0:
                total *= 0.85
            confidence = min(0.99, total / 2.2)
            source = 'keyword' if kw_score >= hs_score * 0.9 and kw_score > 0 else 'history'
            results.append({
                'reason_id': item['reason_id'],
                'name': item['name'],
                'category_name': item['category_name'],
                'confidence': round(confidence, 3),
                'source': source,
                'matched_keywords': item['matched_keywords'],
                'keyword_score': round(kw_score, 3),
                'history_score': round(hs_score, 3),
                'total_score': round(total, 3),
            })

        results.sort(key=lambda x: x['total_score'], reverse=True)
        return results[:5]

    # ── 统计 ────────────────────────────────────────────────────────────────

    def get_stats(self):
        """摘要统计"""
        from sqlalchemy import func
        total      = AftersaleCase.query.count()
        confirmed  = AftersaleCase.query.filter_by(status='confirmed').count()
        pending    = self.get_pending_count()
        ignored    = AftersaleCase.query.filter_by(status='ignored').count()

        # 最常见 Top5 原因
        top_reasons = (
            db.session.query(
                AftersaleReason.name,
                AftersaleReason.category_id,
                AftersaleReason.use_count,
            )
            .filter(AftersaleReason.use_count > 0)
            .order_by(AftersaleReason.use_count.desc())
            .limit(5)
            .all()
        )
        # 补充分类名称
        cat_ids = {r.category_id for r in top_reasons if r.category_id}
        cat_names = {}
        if cat_ids:
            cats = AftersaleReasonCategory.query.filter(
                AftersaleReasonCategory.id.in_(cat_ids)
            ).all()
            cat_names = {c.id: c.name for c in cats}

        return {
            'total':     total,
            'confirmed': confirmed,
            'pending':   pending,
            'ignored':   ignored,
            'top_reasons': [
                {
                    'name':          r.name,
                    'category_name': cat_names.get(r.category_id),
                    'use_count':     r.use_count,
                }
                for r in top_reasons
            ],
        }

    def get_chart_data(self, filters: dict):
        """
        图表聚合数据。
        filters.group_by: 'product' | 'reason' | 'shipping_alias' | 'channel' | 'province'
        其余筛选参数与 get_cross_filter_options 一致，另加 max_days_since_purchase。
        product 维度自动下钻：无产品筛选→品类；仅品类→系列；品类+系列→型号。
        """
        from database.models.product.category import ProductModel, ProductSeries, ProductCategory

        group_by  = filters.get('group_by', 'reason')

        q = (
            db.session.query(AftersaleCase, AftersaleCaseReason)
            .join(AftersaleCaseReason, AftersaleCaseReason.case_id == AftersaleCase.id)
            .filter(AftersaleCase.status == 'confirmed')
        )

        # ── 公共筛选条件 ────────────────────────────
        if filters.get('date_start'):
            q = q.filter(AftersaleCase.shipped_date >= filters['date_start'])
        if filters.get('date_end'):
            q = q.filter(AftersaleCase.shipped_date <= filters['date_end'])
        if filters.get('max_days_since_purchase') is not None:
            q = q.filter(AftersaleCaseReason.days_since_purchase <= filters['max_days_since_purchase'])
        if filters.get('channel_names'):
            q = q.filter(AftersaleCase.channel_name.in_(filters['channel_names']))
        if filters.get('provinces'):
            q = q.filter(AftersaleCase.province.in_(filters['provinces']))
        if filters.get('cities'):
            q = q.filter(AftersaleCase.city.in_(filters['cities']))
        if filters.get('model_ids'):
            q = q.filter(AftersaleCaseReason.model_id.in_(filters['model_ids']))
        elif filters.get('series_ids'):
            sub = (db.session.query(ProductModel.id)
                   .filter(ProductModel.series_id.in_(filters['series_ids']))
                   .subquery())
            q = q.filter(AftersaleCaseReason.model_id.in_(sub))
        elif filters.get('category_ids'):
            sub = (db.session.query(ProductModel.id)
                   .join(ProductSeries, ProductSeries.id == ProductModel.series_id)
                   .filter(ProductSeries.category_id.in_(filters['category_ids']))
                   .subquery())
            q = q.filter(AftersaleCaseReason.model_id.in_(sub))
        if filters.get('reason_ids'):
            q = q.filter(AftersaleCaseReason.reason_id.in_(filters['reason_ids']))
        elif filters.get('reason_category_ids'):
            sub = (db.session.query(AftersaleReason.id)
                   .filter(AftersaleReason.category_id.in_(filters['reason_category_ids']))
                   .subquery())
            q = q.filter(AftersaleCaseReason.reason_id.in_(sub))
        if filters.get('shipping_alias_ids'):
            q = q.filter(AftersaleCaseReason.shipping_alias_id.in_(filters['shipping_alias_ids']))
        if filters.get('return_alias_ids'):
            q = q.filter(AftersaleCaseReason.return_alias_id.in_(filters['return_alias_ids']))

        rows = q.all()

        # ── 按维度聚合 ────────────────────���──────────
        agg = {}

        if group_by == 'product':
            # 按产品下钻层级聚合：收集行内 model_id，查出品类/系列/型号名称
            model_ids_used = set(cr.model_id for _, cr in rows if cr.model_id)
            # 构建 model_id → {category_name, series_code, model_code} 映射
            model_info = {}
            if model_ids_used:
                for m, s, c in (
                    db.session.query(ProductModel, ProductSeries, ProductCategory)
                    .join(ProductSeries, ProductSeries.id == ProductModel.series_id)
                    .join(ProductCategory, ProductCategory.id == ProductSeries.category_id)
                    .filter(ProductModel.id.in_(model_ids_used))
                    .all()
                ):
                    model_info[m.id] = {
                        'category_id':   c.id,
                        'category_name': c.name,
                        'series_id':     s.id,
                        'series_code':   s.code,
                        'model_id':      m.id,
                        'model_code':    m.model_code,
                    }

            # 推导聚合层级：同 ShippingDashboard 逻辑
            sel_cat = set(filters.get('category_ids') or [])
            sel_ser = set(filters.get('series_ids')   or [])
            sel_mod = set(filters.get('model_ids')    or [])

            if sel_mod:
                level = 'model'
            elif sel_ser:
                level = 'model'   # 系列已定，显示型号
            elif sel_cat:
                level = 'series'  # 品类已定，显示系列
            else:
                level = 'category'

            for _, cr in rows:
                info = model_info.get(cr.model_id) if cr.model_id else None
                if level == 'model':
                    key = info['model_code'] if info else '未知型号'
                elif level == 'series':
                    key = info['series_code'] if info else '未知系列'
                else:
                    key = info['category_name'] if info else '未知品类'
                agg[key] = agg.get(key, 0) + 1

        elif group_by == 'reason':
            reason_ids_used = set(cr.reason_id for _, cr in rows if cr.reason_id)
            reason_name_map = {}
            if reason_ids_used:
                for r in AftersaleReason.query.filter(AftersaleReason.id.in_(reason_ids_used)).all():
                    reason_name_map[r.id] = r.name
            for _, cr in rows:
                key = reason_name_map.get(cr.reason_id, '未分类')
                agg[key] = agg.get(key, 0) + 1

        elif group_by == 'shipping_alias':
            alias_ids_used = set(cr.shipping_alias_id for _, cr in rows if cr.shipping_alias_id)
            alias_name_map = {}
            if alias_ids_used:
                for a in AftersaleShippingAlias.query.filter(AftersaleShippingAlias.id.in_(alias_ids_used)).all():
                    alias_name_map[a.id] = a.name
            for _, cr in rows:
                key = alias_name_map.get(cr.shipping_alias_id, '未标记')
                agg[key] = agg.get(key, 0) + 1

        elif group_by == 'channel':
            for case, _ in rows:
                key = case.channel_name or '未知渠道'
                agg[key] = agg.get(key, 0) + 1

        elif group_by == 'province':
            for case, _ in rows:
                key = case.province or '未知省份'
                agg[key] = agg.get(key, 0) + 1

        items = [{'name': k, 'value': v} for k, v in
                 sorted(agg.items(), key=lambda x: x[1], reverse=True)]

        # ── 销售占比：售后件数 / 同期发货量 ───────────────
        ship_agg = self._get_shipping_agg(filters, group_by,
                                          model_info if group_by == 'product' else {},
                                          level     if group_by == 'product' else None)
        for item in items:
            shipped = ship_agg.get(item['name'], 0)
            item['shipped'] = shipped
            if shipped > 0:
                ratio = item['value'] / shipped * 100
                item['sale_ratio'] = round(ratio, 4)
            else:
                item['sale_ratio'] = None

        # ── 整体占比（上一级参考线）：不依赖 group_by，始终用全局发货量计算 ──
        total_aftersale = sum(v['value'] for v in items)
        # 用 None 作为 level/group_by，_get_shipping_agg 对 product 维度取全量
        overall_ship = self._get_shipping_agg(
            filters, group_by,
            model_info if group_by == 'product' else {},
            level      if group_by == 'product' else None,
            total_only=True,
        )
        overall_ratio = round(total_aftersale / overall_ship * 100, 4) if overall_ship > 0 else None

        return {
            'summary': {
                'total':         total_aftersale,
                'overall_ratio': overall_ratio,
            },
            'items': items,
        }

    def _get_shipping_agg(self, filters: dict, group_by: str,
                          model_info: dict, level: str | None,
                          total_only: bool = False) -> dict:
        """
        按相同时间/渠道/地域筛选，用单次 GROUP BY 聚合发货量。
        total_only=True 时不分组，直接返回总发货量（float）。
        """
        from database.models.product.category import ProductModel, ProductSeries, ProductCategory
        from database.models.product.finished import ProductFinished
        from database.models.shipping import ShippingOrderFinished
        from sqlalchemy import func, collate as sa_collate

        sof = ShippingOrderFinished

        # total_only：不分组，直接返回总发货量（用于整体参考线）
        # 此时忽略 group_by 限制，始终查询以获取整体发货量
        if total_only:
            need_product_join = bool(
                filters.get('model_ids') or filters.get('series_ids') or filters.get('category_ids')
            )
            q = db.session.query(func.sum(sof.quantity)).filter(sof.finished_code.isnot(None))
            if need_product_join:
                q = (q.join(ProductFinished,
                             sa_collate(sof.finished_code, 'utf8mb4_unicode_ci') ==
                             sa_collate(ProductFinished.code, 'utf8mb4_unicode_ci'))
                      .join(ProductModel, ProductFinished.model_id == ProductModel.id)
                      .join(ProductSeries, ProductModel.series_id == ProductSeries.id)
                      .join(ProductCategory, ProductSeries.category_id == ProductCategory.id))
            if filters.get('date_start'):  q = q.filter(sof.shipped_date >= filters['date_start'])
            if filters.get('date_end'):    q = q.filter(sof.shipped_date <= filters['date_end'])
            if filters.get('channel_names'): q = q.filter(sof.channel_name.in_(filters['channel_names']))
            if filters.get('provinces'):     q = q.filter(sof.province.in_(filters['provinces']))
            if filters.get('cities'):        q = q.filter(sof.city.in_(filters['cities']))
            if filters.get('model_ids'):     q = q.filter(ProductModel.id.in_(filters['model_ids']))
            elif filters.get('series_ids'):  q = q.filter(ProductSeries.id.in_(filters['series_ids']))
            elif filters.get('category_ids'): q = q.filter(ProductCategory.id.in_(filters['category_ids']))
            result = q.scalar()
            return float(result or 0)

        # reason / shipping_alias 维度无发货关联，直接返回空
        if group_by not in ('product', 'channel', 'province'):
            return {}

        # ── 确定 GROUP BY 表达式及所需 JOIN ────────────────
        need_product_join = (
            group_by == 'product' or
            bool(filters.get('model_ids') or filters.get('series_ids') or filters.get('category_ids'))
        )

        if group_by == 'product':
            if level == 'model':
                label_expr = func.coalesce(ProductModel.model_code, '未知')
            elif level == 'series':
                label_expr = func.coalesce(ProductSeries.code, '未知')
            else:
                label_expr = func.coalesce(ProductCategory.name, '未知')
        elif group_by == 'channel':
            label_expr = func.coalesce(sof.channel_name, '未知渠道')
        else:  # province
            label_expr = func.coalesce(sof.province, '未知省份')

        q = db.session.query(
            label_expr.label('label'),
            func.sum(sof.quantity).label('qty'),
        ).filter(sof.finished_code.isnot(None))

        # ── 产品 JOIN（只有 product 维度或有产品过滤时才 JOIN）───
        if need_product_join:
            q = (q
                 .join(ProductFinished,
                       sa_collate(sof.finished_code, 'utf8mb4_unicode_ci') ==
                       sa_collate(ProductFinished.code, 'utf8mb4_unicode_ci'))
                 .join(ProductModel, ProductFinished.model_id == ProductModel.id)
                 .join(ProductSeries, ProductModel.series_id == ProductSeries.id)
                 .join(ProductCategory, ProductSeries.category_id == ProductCategory.id))

        # ── 公共筛选条件 ────────────────────────────────────
        if filters.get('date_start'):
            q = q.filter(sof.shipped_date >= filters['date_start'])
        if filters.get('date_end'):
            q = q.filter(sof.shipped_date <= filters['date_end'])
        if filters.get('channel_names'):
            q = q.filter(sof.channel_name.in_(filters['channel_names']))
        if filters.get('provinces'):
            q = q.filter(sof.province.in_(filters['provinces']))
        if filters.get('cities'):
            q = q.filter(sof.city.in_(filters['cities']))

        # ── 产品范围过滤 ────────────────────────────────────
        if filters.get('model_ids'):
            q = q.filter(ProductModel.id.in_(filters['model_ids']))
        elif filters.get('series_ids'):
            q = q.filter(ProductSeries.id.in_(filters['series_ids']))
        elif filters.get('category_ids'):
            q = q.filter(ProductCategory.id.in_(filters['category_ids']))

        rows = q.group_by(label_expr).all()
        return {r.label: float(r.qty or 0) for r in rows}

    def get_cross_filter_options(self, filters: dict):
        """
        联动筛选选项：对每个维度，应用所有其他维度的筛选条件，返回该维度可用的候选值。
        filters: {
          date_start, date_end,
          channel_names, provinces, cities,
          model_ids,              # 型号 id 列表（产品维度）
          reason_ids,             # 二级原因 id 列表
          reason_category_ids,    # 一级分类 id 列表
          shipping_alias_ids,     # 发货物料简称 id 列表
          return_alias_ids,       # 售后物料简称 id 列表
        }
        """
        from sqlalchemy import distinct, and_
        from database.models.product.category import ProductModel, ProductSeries, ProductCategory

        def make_conds(exclude=None):
            """构建 WHERE 条件列表，排除指定维度的筛选。"""
            c = [AftersaleCase.status == 'confirmed']
            if filters.get('date_start'):
                c.append(AftersaleCase.shipped_date >= filters['date_start'])
            if filters.get('date_end'):
                c.append(AftersaleCase.shipped_date <= filters['date_end'])
            if exclude != 'channel' and filters.get('channel_names'):
                c.append(AftersaleCase.channel_name.in_(filters['channel_names']))
            if exclude != 'province' and filters.get('provinces'):
                c.append(AftersaleCase.province.in_(filters['provinces']))
            if exclude != 'province' and filters.get('cities'):
                c.append(AftersaleCase.city.in_(filters['cities']))
            if exclude != 'product':
                if filters.get('model_ids'):
                    c.append(AftersaleCaseReason.model_id.in_(filters['model_ids']))
                elif filters.get('series_ids'):
                    sub = (db.session.query(ProductModel.id)
                           .filter(ProductModel.series_id.in_(filters['series_ids']))
                           .subquery())
                    c.append(AftersaleCaseReason.model_id.in_(sub))
                elif filters.get('category_ids'):
                    sub = (db.session.query(ProductModel.id)
                           .join(ProductSeries, ProductSeries.id == ProductModel.series_id)
                           .filter(ProductSeries.category_id.in_(filters['category_ids']))
                           .subquery())
                    c.append(AftersaleCaseReason.model_id.in_(sub))
            if exclude != 'reason' and filters.get('reason_ids'):
                c.append(AftersaleCaseReason.reason_id.in_(filters['reason_ids']))
            if exclude != 'reason' and not filters.get('reason_ids') and filters.get('reason_category_ids'):
                # 仅一级分类筛选时，通过子查询过滤
                sub = (db.session.query(AftersaleReason.id)
                       .filter(AftersaleReason.category_id.in_(filters['reason_category_ids']))
                       .subquery())
                c.append(AftersaleCaseReason.reason_id.in_(sub))
            if exclude != 'shipping' and filters.get('shipping_alias_ids'):
                c.append(AftersaleCaseReason.shipping_alias_id.in_(filters['shipping_alias_ids']))
            if exclude != 'return' and filters.get('return_alias_ids'):
                c.append(AftersaleCaseReason.return_alias_id.in_(filters['return_alias_ids']))
            if filters.get('max_days_since_purchase') is not None:
                c.append(AftersaleCaseReason.days_since_purchase <= filters['max_days_since_purchase'])
            return c

        def base(exclude=None):
            return (
                db.session.query(AftersaleCase, AftersaleCaseReason)
                .join(AftersaleCaseReason, AftersaleCaseReason.case_id == AftersaleCase.id)
                .filter(and_(*make_conds(exclude)))
            )

        # 各维度可用值
        channels = sorted(set(
            r[0] for r in base('channel').with_entities(AftersaleCase.channel_name).all()
            if r[0] is not None
        ))
        provinces = sorted(set(
            r[0] for r in base('province').with_entities(AftersaleCase.province).all()
            if r[0] is not None
        ))
        cities = sorted(set(
            r[0] for r in base('province').with_entities(AftersaleCase.city).all()
            if r[0] is not None
        ))
        model_ids = sorted(set(
            r[0] for r in base('product').with_entities(AftersaleCaseReason.model_id).all()
            if r[0] is not None
        ))
        reason_ids = sorted(set(
            r[0] for r in base('reason').with_entities(AftersaleCaseReason.reason_id).all()
            if r[0] is not None
        ))
        shipping_alias_ids = sorted(set(
            r[0] for r in base('shipping').with_entities(AftersaleCaseReason.shipping_alias_id).all()
            if r[0] is not None
        ))
        return_alias_ids = sorted(set(
            r[0] for r in base('return').with_entities(AftersaleCaseReason.return_alias_id).all()
            if r[0] is not None
        ))

        return {
            'channels':           channels,
            'provinces':          provinces,
            'cities':             cities,
            'model_ids':          model_ids,
            'reason_ids':         reason_ids,
            'shipping_alias_ids': shipping_alias_ids,
            'return_alias_ids':   return_alias_ids,
        }

    def get_chart_options(self):
        """返回筛选用的渠道/省份列表，以及一级分类对象列表"""
        from sqlalchemy import distinct
        channels = [
            r[0] for r in
            db.session.query(distinct(AftersaleCase.channel_name))
            .filter(AftersaleCase.channel_name.isnot(None))
            .filter(AftersaleCase.status == 'confirmed')
            .order_by(AftersaleCase.channel_name)
            .all()
        ]
        provinces = [
            r[0] for r in
            db.session.query(distinct(AftersaleCase.province))
            .filter(AftersaleCase.province.isnot(None))
            .filter(AftersaleCase.status == 'confirmed')
            .order_by(AftersaleCase.province)
            .all()
        ]
        # 一级分类返回对象列表（含 id，供前端 category_id 筛选）
        categories = [
            c.to_dict() for c in
            AftersaleReasonCategory.query
            .order_by(AftersaleReasonCategory.sort_order, AftersaleReasonCategory.id)
            .all()
        ]
        return {'channels': channels, 'provinces': provinces, 'categories': categories}

    def suggest_product(self, product_codes, purchase_date_str=None, seller_remark=None, buyer_remark=None, products=None):
        """
        根据买家留言推断最可能的售后成品型号。

        发货物料代码（product_codes）只用于辅助字段（发货简称/历史原因），
        不参与型号推断——因为多款成品共用相同物料，按物料代码匹配型号会产生误导。

        来源（买家留言 → 型号名/系列名关键词匹配）：
          精确匹配系列名 → +20；系列名/型号名包含买家留言 → +15；
          买家留言包含系列名（≥2字） → +10；
          买家留言包含 3 位尺寸数字（080/100/120）且型号名/代码含该数字 → 额外 +5

        最终排序：综合得分
        返回 {category_id, series_id, model_id, ...} 或 None（买家留言为空时）
        """
        from collections import defaultdict
        from sqlalchemy import or_
        from database.models.product.category import ProductCategory, ProductSeries, ProductModel
        from database.models.product.finished import ProductFinished

        # code_filters：用于辅助字段（简称/历史原因），不再用于型号推断
        code_filters = [
            db.func.json_search(
                AftersaleCase.products, 'one', code, None, '$[*].code'
            ).isnot(None)
            for code in (product_codes or [])
        ] if product_codes else []

        # purchase_date → YYYY-MM，用于生命周期检查
        purchase_ym = None
        if purchase_date_str:
            try:
                from datetime import date as _date
                pd = _date.fromisoformat(purchase_date_str)
                purchase_ym = f"{pd.year}-{pd.month:02d}"
            except (ValueError, AttributeError):
                pass

        # model_id → (listed_yymm, delisted_yymm) 映射（懒加载，Source C 后使用）
        def _get_lifecycle_map():
            rows = (
                db.session.query(
                    ProductFinished.model_id,
                    ProductFinished.listed_yymm,
                    ProductFinished.delisted_yymm,
                )
                .filter(ProductFinished.model_id.isnot(None))
                .filter(ProductFinished.status != 'ignored')
                .all()
            )
            lc = {}
            for r in rows:
                if r.model_id not in lc:
                    lc[r.model_id] = (r.listed_yymm, r.delisted_yymm)
            return lc

        # 每个 model_id 的综合信息
        # match_level: 2=系列+版本均命中，1=仅系列命中（无版本提示或版本未命中）
        # 排序优先级：match_level > date_ok > score
        model_score = defaultdict(lambda: {'score': 0.0, 'date_ok': True, 'meta': None, 'match_level': 1})

        # ── 来源 C：买家留言 → 产品名/系列名关键词匹配 ──────────────────────
        # 买家留言通常直接写明产品名（如"梦境"），用于跨产品代码匹配正确的产品线。
        # 优先级：系列名精确=买家留言 → +20；系列名/型号名包含买家留言 → +15；
        #         买家留言包含系列名（≥2字） → +10
        # 不依赖历史记录，只要产品库有对应数据即可命中
        if buyer_remark and buyer_remark.strip():
            br_lower = buyer_remark.strip().lower()
            if len(br_lower) >= 2:
                model_rows = (
                    db.session.query(
                        ProductModel.id.label('model_id'),
                        ProductModel.name.label('model_name'),
                        ProductModel.model_code.label('model_code'),
                        ProductSeries.id.label('series_id'),
                        ProductSeries.name.label('series_name'),
                        ProductCategory.id.label('category_id'),
                        ProductCategory.name.label('category_name'),
                    )
                    .join(ProductSeries,   ProductSeries.id   == ProductModel.series_id)
                    .join(ProductCategory, ProductCategory.id == ProductSeries.category_id)
                    .all()
                )
                # 尺寸归一化：将型号名中的 "x.x米" 转换为厘米数字字符串，方便与买家留言匹配
                # 例如 "1.0米" → "100"，"0.8米" → "80"（080），"1.2米" → "120"
                def _normalize_tokens(name):
                    """提取型号名中的可匹配属性 token 列表（版本/尺寸/材料/颜色/手动/电动/型号版本等）"""
                    tokens = []
                    # 系列版本号：V3.1 → "3.1"
                    for m in re.finditer(r'[Vv](\d+\.\d+)', name):
                        tokens.append(m.group(1))
                    # 尺寸：1.0米→"100"，0.8米→"080"，1.2米→"120"
                    for m in re.finditer(r'(\d+(?:\.\d+)?)米', name):
                        cm = round(float(m.group(1)) * 100)
                        tokens.append(str(cm).zfill(3))   # 保留前导零如 "080"
                        tokens.append(str(cm))             # 也匹配无前导零如 "80"
                    # 型号版本字母：_A/_B/_C（出现在末尾），单独存放供外部比对
                    m = re.search(r'[_\-]([A-Za-z])$', name.strip())
                    if m:
                        tokens.append('__variant__' + m.group(1).upper())
                    # 其余中文词段（材料/颜色/驱动方式等，≥2字）
                    for seg in re.findall(r'[\u4e00-\u9fff]{2,}', name):
                        tokens.append(seg)
                    return tokens

                def _base_name(name):
                    """去掉系列名中的版本号括号，如 '进取 (V3.1)' → '进取'"""
                    return re.sub(r'\s*[\(（][Vv]\d.*', '', name).strip().lower()

                # 买家留言中的独立字母（非V/v），代表型号版本（如A/B/C）
                br_variant_letters = set(
                    l.upper() for l in re.findall(r'(?<![A-Za-z])([A-UW-Za-uw-z])(?![A-Za-z])', buyer_remark)
                )

                for row in model_rows:
                    sname      = (row.series_name or '').strip().lower()
                    sname_base = _base_name(row.series_name or '')
                    mname      = (row.model_name  or '').strip().lower()
                    mid        = row.model_id
                    if sname == br_lower:
                        weight = 20
                    elif sname_base and sname_base == br_lower:
                        weight = 20
                    elif sname and br_lower in sname:
                        weight = 15
                    elif br_lower in mname:
                        weight = 15
                    elif sname_base and len(sname_base) >= 2 and sname_base in br_lower:
                        weight = 10
                    elif sname and len(sname) >= 2 and sname in br_lower:
                        weight = 10
                    else:
                        continue
                    # 属性匹配加分：逐一检查型号名的属性 token 是否出现在买家留言中
                    version_hit = False
                    for tok in _normalize_tokens(row.model_name or ''):
                        if tok.startswith('__variant__'):
                            if tok[len('__variant__'):] in br_variant_letters:
                                weight += 2
                        elif tok in buyer_remark:
                            weight += 2
                            # 版本号 token（如 "3.1"）命中 → 升级 match_level
                            if re.fullmatch(r'\d+\.\d+', tok):
                                version_hit = True
                    model_score[mid]['score'] += weight
                    if version_hit:
                        model_score[mid]['match_level'] = 2
                    if not model_score[mid]['meta']:
                        model_score[mid]['meta'] = row

        # ── 生命周期惩罚 ──────────────────────────────────────────────────────────
        # 规则：
        # 1. 购买日期 > 退市日期 → 直接归零（型号已停售）
        # 2. 上市日期 > 2024-01，且购买日期 < 上市日期 → 直接归零（型号尚未发布）
        # 3. 上市日期 <= 2024-01，且购买日期 < 上市日期 → 扣 3 分（上市日期可能是数据录入起点，非真实发布日）
        # 说明：发货数据从 2024-01 起有记录，所有当时有数据的型号均被设为 2024-01 上市
        _DATA_START = '2024-01'
        if purchase_ym and model_score:
            lifecycle_map = _get_lifecycle_map()
            current_ym = now_cst().strftime('%Y-%m')
            for mid, v in model_score.items():
                lc = lifecycle_map.get(mid)
                if not lc:
                    continue
                listed_ym, delisted_ym = lc
                effective_delisted = delisted_ym or current_ym
                if effective_delisted < purchase_ym:
                    # 规则1：已退市
                    v['date_ok'] = False
                    v['score']   = 0
                elif listed_ym and purchase_ym < listed_ym:
                    v['date_ok'] = False
                    if listed_ym > _DATA_START:
                        # 规则2：明确在 2024-01 后上市，购买日期更早 → 不可能
                        v['score'] = 0
                    else:
                        # 规则3：上市日期可能只是数据起点，扣分但保留
                        v['score'] = max(0, v['score'] - 3)

        # ── 历史简称 & 原因统计（共用 code_filters）────────────────────
        # 三个字段各自按频次取最高，来源均为相同产品代码的历史确认工单

        def _top_alias_id(field):
            """按频次取 AftersaleCaseReason 某简称 ID 字段的最高值"""
            cnt = {}
            rows = (
                db.session.query(field)
                .join(AftersaleCase, AftersaleCase.id == AftersaleCaseReason.case_id)
                .filter(AftersaleCase.status == 'confirmed')
                .filter(field.isnot(None))
                .filter(or_(*code_filters))
                .all()
            )
            for (val,) in rows:
                if val is not None:
                    cnt[val] = cnt.get(val, 0) + 1
            return max(cnt, key=cnt.get) if cnt else None

        # ── 发货物料简称：绑定库匹配优先，历史频次兜底 ──────────────────────
        binding_shipping_id, _ = self.match_shipping_alias(products or [])
        history_shipping_id     = _top_alias_id(AftersaleCaseReason.shipping_alias_id)
        suggested_shipping_alias_id = binding_shipping_id or history_shipping_id

        # ── 售后物料简称：绑定库文本匹配优先，历史频次兜底 ──────────────────
        binding_return_id, binding_return_score = self.match_return_alias(seller_remark)
        history_return_id     = _top_alias_id(AftersaleCaseReason.return_alias_id)
        suggested_return_alias_id = binding_return_id or history_return_id
        suggested_return_alias_source = 'library' if binding_return_id else ('history' if history_return_id else None)
        suggested_return_alias_score = binding_return_score if binding_return_id else None

        # 历史原因：取 reason_id 出现最多的一条，并附带其 category_id
        reason_cnt = {}
        reason_rows = (
            db.session.query(
                AftersaleCaseReason.reason_id,
                AftersaleReason.category_id,
            )
            .join(AftersaleCase,   AftersaleCase.id   == AftersaleCaseReason.case_id)
            .join(AftersaleReason, AftersaleReason.id == AftersaleCaseReason.reason_id)
            .filter(AftersaleCase.status == 'confirmed')
            .filter(AftersaleCaseReason.reason_id.isnot(None))
            .filter(or_(*code_filters))
            .all()
        )
        for row in reason_rows:
            key = (row.reason_id, row.category_id)
            reason_cnt[key] = reason_cnt.get(key, 0) + 1

        suggested_reason_id          = None
        suggested_reason_category_id = None
        if reason_cnt:
            best_key = max(reason_cnt, key=reason_cnt.get)
            suggested_reason_id, suggested_reason_category_id = best_key

        # ── 组装返回 ─────────────────────────────────────────────────────
        suggestions = {
            'suggested_shipping_alias_id': suggested_shipping_alias_id,
            'suggested_return_alias_id':   suggested_return_alias_id,
            'suggested_return_alias_source': suggested_return_alias_source,
            'suggested_return_alias_score': suggested_return_alias_score,
            'suggested_reason_id':          suggested_reason_id,
            'suggested_reason_category_id': suggested_reason_category_id,
        }

        if not model_score:
            # 没有找到型号匹配，但仍可返回辅助建议
            has_any = any(v is not None for v in suggestions.values())
            return suggestions if has_any else None

        # 排序：系列+版本匹配程度 > date_ok > 综合得分
        ranked = sorted(
            model_score.items(),
            key=lambda x: (x[1]['match_level'], x[1]['date_ok'], x[1]['score']),
            reverse=True,
        )
        size_hints_debug = set(re.findall(r'\b(0\d{2}|1[012]\d)\b', buyer_remark or ''))
        print(f'[suggest_debug] buyer_remark={buyer_remark!r} size_hints={size_hints_debug}')
        for mid, v in ranked[:8]:
            print(f'  model_id={mid} name={v["meta"].model_name if v["meta"] else "?"} code={getattr(v["meta"], "model_code", "?")} score={v["score"]:.2f} date_ok={v["date_ok"]}')
        best   = ranked[0][1]
        meta   = best['meta']

        # Top 5 候选（按系列分组，每个系列取最高分型号为代表，附带系列内所有型号明细）
        series_data = {}
        for mid, v in ranked:
            m = v['meta']
            if not m:
                continue
            sid = m.series_id
            if sid not in series_data:
                series_data[sid] = {
                    'mid': mid, 'score': v['score'], 'meta': m,
                    'date_ok': v['date_ok'], 'match_level': v['match_level'], 'models': []
                }
            series_data[sid]['models'].append({
                'id':         mid,
                'model_code': getattr(m, 'model_code', None),
                'name':       m.model_name,
                'score':      v['score'],
                'date_ok':    v['date_ok'],
            })
        top_series = sorted(series_data.values(), key=lambda x: (x['match_level'], x['date_ok'], x['score']), reverse=True)[:5]
        max_score  = top_series[0]['score'] if top_series else 1
        candidates = [
            {
                'category_id':   s['meta'].category_id,
                'series_id':     s['meta'].series_id,
                'model_id':      s['mid'],
                'category_name': s['meta'].category_name,
                'series_name':   s['meta'].series_name,
                'model_name':    s['meta'].model_name,
                'model_code':    getattr(s['meta'], 'model_code', None),
                'score':         round(s['score'] / max_score, 2),
                'date_ok':       s['date_ok'],
                'models':        sorted(s['models'], key=lambda x: -x['score']),
            }
            for s in top_series
        ]

        return {
            'category_id':   meta.category_id,
            'series_id':     meta.series_id,
            'model_id':      meta.model_id,
            'category_name': meta.category_name,
            'series_name':   meta.series_name,
            'model_name':    meta.model_name,
            'date_ok':       best['date_ok'],
            'candidates':    candidates,
            **suggestions,
        }

    # ── 发货物料简称库 ─────────────────────────────────────────────────────────

    def get_all_shipping_aliases(self):
        return (
            AftersaleShippingAlias.query
            .order_by(AftersaleShippingAlias.sort_order.asc(),
                      AftersaleShippingAlias.id.asc())
            .all()
        )

    def create_shipping_alias(self, name, keywords=None, sort_order=0):
        obj = AftersaleShippingAlias(name=name, keywords=keywords or [], sort_order=sort_order)
        db.session.add(obj)
        db.session.commit()
        return obj

    def update_shipping_alias(self, alias_id, name, keywords=None, sort_order=None):
        obj = AftersaleShippingAlias.query.get(alias_id)
        if not obj:
            return None
        obj.name = name
        if keywords is not None:
            obj.keywords = keywords
        if sort_order is not None:
            obj.sort_order = sort_order
        db.session.commit()
        return obj

    def delete_shipping_alias(self, alias_id):
        obj = AftersaleShippingAlias.query.get(alias_id)
        if not obj:
            return False
        db.session.delete(obj)
        db.session.commit()
        return True

    # ── 售后物料简称库 ─────────────────────────────────────────────────────────

    def get_all_return_aliases(self):
        return (
            AftersaleReturnAlias.query
            .order_by(AftersaleReturnAlias.sort_order.asc(),
                      AftersaleReturnAlias.id.asc())
            .all()
        )

    def create_return_alias(self, name, keywords=None, sort_order=0):
        obj = AftersaleReturnAlias(name=name, keywords=keywords or [], sort_order=sort_order)
        db.session.add(obj)
        db.session.commit()
        return obj

    def update_return_alias(self, alias_id, name, keywords=None, sort_order=None):
        obj = AftersaleReturnAlias.query.get(alias_id)
        if not obj:
            return None
        obj.name = name
        if keywords is not None:
            obj.keywords = keywords
        if sort_order is not None:
            obj.sort_order = sort_order
        db.session.commit()
        return obj

    def delete_return_alias(self, alias_id):
        obj = AftersaleReturnAlias.query.get(alias_id)
        if not obj:
            return False
        db.session.delete(obj)
        db.session.commit()
        return True

    # ── 简称库关键词自动合并（提交工单时调用，通过 ID 查找） ──────────────────

    def upsert_shipping_alias_by_id(self, alias_id, product_names):
        """提交工单时：将当前物料名称合并到已有发货简称的关键词列表。"""
        obj = AftersaleShippingAlias.query.get(alias_id)
        if not obj:
            return
        new_kws = [n.strip() for n in (product_names or []) if n and n.strip()]
        if new_kws:
            existing = set(obj.keywords or [])
            merged   = list(existing | set(new_kws))
            obj.keywords = merged[:50] if merged else obj.keywords

    def upsert_return_alias_by_id(self, alias_id, seller_remark, buyer_remark=None):
        """提交工单时：将商家备注片段合并到已有售后简称的关键词列表。"""
        obj = AftersaleReturnAlias.query.get(alias_id)
        if not obj:
            return
        remark = self._clean_remark_for_alias(seller_remark, buyer_remark)
        if remark:
            existing = list(obj.keywords or [])
            if remark not in existing:
                existing.append(remark)
                obj.keywords = existing[-50:]

    # ── 简称库自动入库（简称管理页用） ───────────────────────────────────────

    def upsert_shipping_alias(self, name, product_names):
        """
        提交工单时：若发货物料简称不在库中则自动创建，
        若已存在则将当前物料名称合并到关键词列表（去重，最多保留 50 条）。
        不触发独立 commit（由 confirm_case 统一提交）。
        """
        if not name:
            return
        name = name.strip()
        if not name:
            return
        obj = AftersaleShippingAlias.query.filter_by(name=name).first()
        new_kws = [n.strip() for n in (product_names or []) if n and n.strip()]
        if obj is None:
            obj = AftersaleShippingAlias(name=name, keywords=new_kws or None)
            db.session.add(obj)
        else:
            existing = set(obj.keywords or [])
            merged   = list(existing | set(new_kws))
            obj.keywords = merged[:50] if merged else obj.keywords

    # 日期相关的正则（过滤后不应作为关键词存入）
    _DATE_RE = re.compile(
        r'\d{4}[年\-/\.]\d{1,2}[月\-/\.]\d{1,2}日?'   # 2024-01-01 / 2024年1月1日
        r'|\d{4}[年\-/\.]\d{1,2}月?'                    # 2024-01 / 2024年1月
        r'|\d{1,2}[月/\-]\d{1,2}[日号]?'                # 1月1日 / 01/01
        r'|\d{4}年',                                     # 2024年
        re.UNICODE
    )

    @classmethod
    def _clean_remark_for_alias(cls, seller_remark, buyer_remark):
        """去除买家留言重复内容和日期后，返回净化的备注文本。"""
        text = cls._subtract_buyer_remark(seller_remark, buyer_remark)
        text = cls._DATE_RE.sub(' ', text or '')
        text = text.strip()
        return text

    def upsert_return_alias(self, name, seller_remark, buyer_remark=None):
        """
        提交工单时：若售后物料简称不在库中则自动创建，
        若已存在则将商家备注片段添加到关键词列表（去重，最多保留 50 条）。
        自动去除买家留言中与商家备注重复的内容，以及日期类字符串。
        不触发独立 commit（由 confirm_case 统一提交）。
        """
        if not name:
            return
        name = name.strip()
        if not name:
            return
        remark = self._clean_remark_for_alias(seller_remark, buyer_remark)
        obj = AftersaleReturnAlias.query.filter_by(name=name).first()
        if obj is None:
            obj = AftersaleReturnAlias(name=name, keywords=[remark] if remark else None)
            db.session.add(obj)
        else:
            if remark:
                existing = list(obj.keywords or [])
                if remark not in existing:
                    existing.append(remark)
                    # 最多保留最新的 50 条备注片段
                    obj.keywords = existing[-50:]

    # ── 简称库匹配（用于 suggest_product） ──────────────────────────────────────

    @staticmethod
    def _text_sim(text, keyword):
        """简单文本相似度：中文字符级滑动窗口，与前端 calcMatchScore 逻辑一致。"""
        if not text or not keyword:
            return 0.0
        t = text.lower()
        k = keyword.lower()
        if t == k or t in k or k in t:
            return 1.0
        # 仅保留中文字符对比
        import re
        t_cn = re.sub(r'[^\u4e00-\u9fff]', '', t)
        k_cn = re.sub(r'[^\u4e00-\u9fff]', '', k)
        if t_cn and k_cn:
            if t_cn in k_cn or k_cn in t_cn:
                return 0.9
        if len(k) < 2:
            return 0.0
        # 滑动窗口
        max_len = 0
        for length in range(len(k) - 1, 1, -1):
            for i in range(len(k) - length + 1):
                if k[i:i + length] in t:
                    max_len = length
                    break
            if max_len:
                break
        return max_len / len(k) if max_len >= 2 else 0.0

    def match_shipping_alias(self, products):
        """
        根据发货物料列表（含 name 字段）匹配最佳发货物料简称。
        返回 (alias_id, score) 或 (None, 0)。

        评分策略：绝对命中数优先，覆盖率（matched/len(kws））仅作次级排序。
        避免仅绑定1个公共物料码的简称因100%覆盖率误胜。
        """
        if not products:
            return None, 0.0
        product_names = [p.get('name', '') or '' for p in products]
        combined_name = ' '.join(product_names).lower()
        best_id, best_matched, best_ratio = None, 0, 0.0
        for obj in AftersaleShippingAlias.query.filter(
            AftersaleShippingAlias.keywords.isnot(None)
        ).all():
            kws = [k for k in (obj.keywords or []) if k]
            if not kws:
                continue
            matched = sum(1 for k in kws if k.lower() in combined_name)
            if matched == 0:
                continue
            ratio = matched / len(kws)
            # 主键：绝对命中数更多的优先；命中数相同时，覆盖率高的优先
            if (matched, ratio) > (best_matched, best_ratio):
                best_matched = matched
                best_ratio   = ratio
                best_id      = obj.id
        return best_id, best_ratio

    def match_return_alias(self, seller_remark):
        """
        根据商家备注文本匹配最佳售后物料简称。
        返回 (alias_id, score) 或 (None, 0)。

        评分策略（收敛误匹配）：
        1) 简称名称在备注中直接命中时给高权重；
        2) 仅累加“强命中关键词”（score >= _KW_STRONG_HIT）；
        3) 没有简称直命中且没有强命中关键词时，视为不匹配。

        这样可避免“补偿/更换”等弱相关片段造成误匹配。
        """
        if not seller_remark:
            return None, 0.0
        text = seller_remark.lower()
        _KW_STRONG_HIT = 0.5
        _DIRECT_ALIAS_BONUS = 1.0
        best_id, best_total = None, 0.0
        for obj in AftersaleReturnAlias.query.filter(
            AftersaleReturnAlias.keywords.isnot(None)
        ).all():
            kws = [kw for kw in (obj.keywords or []) if kw]
            alias_name = (obj.name or '').strip()
            alias_direct_hit = bool(alias_name and alias_name.lower() in text)
            if not kws and not alias_direct_hit:
                continue
            strong_scores = []
            for kw in kws:
                s = self._text_sim(seller_remark, kw)
                if s >= _KW_STRONG_HIT:
                    strong_scores.append(s)
            if not strong_scores and not alias_direct_hit:
                continue
            total = sum(strong_scores) + (_DIRECT_ALIAS_BONUS if alias_direct_hit else 0.0)
            if total > best_total:
                best_total = total
                best_id    = obj.id
        return (best_id, best_total) if best_total >= _KW_STRONG_HIT else (None, 0.0)


    # ── 发货物料匹配过滤词 ────────────────────────────────────────────────────

    def get_all_ignore_terms(self):
        return AftersaleShippingIgnoreTerm.query.order_by(
            AftersaleShippingIgnoreTerm.created_at.asc()
        ).all()

    def create_ignore_term(self, term):
        obj = AftersaleShippingIgnoreTerm(term=term)
        db.session.add(obj)
        db.session.commit()
        return obj

    def delete_ignore_term(self, term_id):
        obj = AftersaleShippingIgnoreTerm.query.get(term_id)
        if not obj:
            return False
        db.session.delete(obj)
        db.session.commit()
        return True
