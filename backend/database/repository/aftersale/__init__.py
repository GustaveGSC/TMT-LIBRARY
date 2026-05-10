import re
import difflib
from datetime import datetime, timezone, timedelta, date
from collections import defaultdict
from aftersale_logger import write_confirm_log
from database.base import db
from database.models.aftersale import (
    AftersaleReasonCategory, AftersaleReason, AftersaleKeywordCandidate,
    AftersaleCase, AftersaleCaseReason,
    AftersaleShippingAlias,
    AftersaleShippingIgnoreTerm,
    AftersaleShippingAmbiguousTerm,
    AftersaleReasonStopword, AftersaleReasonShortKeepTerm,
    AftersaleDictSuggestion,
    AftersaleReasonAliasAffinity,
    AftersaleProductRemarkDict,

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
            q.order_by(func.min(ShippingRecord.shipped_date).desc())
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
                  shipping_alias=None, model_code=None, search=None,
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

        from database.models.aftersale import AftersaleShippingAlias
        ship_aliases = [
            {'id': r.id, 'name': r.name}
            for r in AftersaleShippingAlias.query.order_by(AftersaleShippingAlias.sort_order, AftersaleShippingAlias.name).all()
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
            'model_codes':       model_codes,
        }

    def confirm_case(self, order_no, products, seller_remark, buyer_remark,
                     shipped_date, operator, channel_name, province, reasons_data,
                     city=None, district=None):
        """
        创建或更新工单（status→confirmed），批量写入 reasons。
        reasons_data: [{reason_id?, custom_reason?, model_id?, shipping_material_alias?, aftersale_material_alias?}]
        """
        # ── 初始化日志上下文 ──────────────────────────────
        import time as _time
        _t0 = _time.perf_counter()
        def _lap(label):
            print(f'[confirm_case] {label}: {(_time.perf_counter() - _t0)*1000:.1f}ms', flush=True)

        self._active_log_ctx = None   # 先清空，confirm_case 执行完前通过 _upsert_dict_suggestion 填充
        log_ctx = {
            'timestamp':       now_cst().strftime('%Y-%m-%d %H:%M:%S'),
            'order_no':        order_no,
            'original': {
                'seller_remark': seller_remark,
                'buyer_remark':  buyer_remark,
                'products':      products or [],
                'reasons_data':  reasons_data,
            },
            'cleaned': {
                'effective_remark':   None,   # 去除买家留言后的有效备注
                'extracted_keywords': [],     # 提取的候选关键词
                'product_tokens':     [],     # 物料名清洗后的 token
            },
            'saved': {
                'case_id': None,
                'is_new':  None,
                'status':  'confirmed',
                'reasons': [],
            },
            'alias_learning':   [],   # 每条简称学习详情
            'keyword_learning': [],   # 每个原因的关键词晋升/抑制详情
            'dict_suggestions': [],   # 本次触发的词典建议
        }
        self._active_log_ctx = log_ctx   # 供 _upsert_dict_suggestion 写入

        case = AftersaleCase.query.filter_by(ecommerce_order_no=order_no).first()
        _lap('查询工单')
        is_new = case is None
        log_ctx['saved']['is_new'] = is_new
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
        log_ctx['saved']['case_id'] = case.id

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
                purchase_date       = item_purchase_date,
                days_since_purchase = item_days,
            )
            db.session.add(cr)
            if rd.get('reason_id'):
                reason_ids_used.add(rd['reason_id'])

            # 记录保存的 reason 行
            log_ctx['saved']['reasons'].append({
                'reason_id':          reason_id,
                'reason_name':        reason_obj.name if reason_id and reason_obj else rd.get('custom_reason'),
                'reason_category_id': reason_category_id,
                'model_id':           rd.get('model_id'),
                'shipping_alias_id':  rd.get('shipping_alias_id') or None,
                'purchase_date':      str(item_purchase_date) if item_purchase_date else None,
                'days_since_purchase': item_days,
            })

        _lap('写入 case + reasons')
        # 递增 use_count + 自动合并关键词
        if reason_ids_used:
            AftersaleReason.query.filter(
                AftersaleReason.id.in_(reason_ids_used)
            ).update({'use_count': AftersaleReason.use_count + 1},
                     synchronize_session='fetch')
            # 按备注分组关键词学习：每条 reason 优先使用前端传入的独立备注，
            # 缺省回退到工单级备注，避免多内容时不同原因互相污染关键词学习。
            remark_to_reasons = {}
            for rd in reasons_data:
                rid = rd.get('reason_id')
                if not rid or rid not in reason_ids_used:
                    continue
                remark_key = (rd.get('seller_remark') or seller_remark or '').strip()
                if not remark_key:
                    continue
                remark_to_reasons.setdefault(remark_key, set()).add(rid)
            if remark_to_reasons:
                for remark_key, rids in remark_to_reasons.items():
                    self._auto_update_reason_keywords(remark_key, rids, buyer_remark,
                                                      log_ctx=log_ctx)
            else:
                self._auto_update_reason_keywords(seller_remark, reason_ids_used, buyer_remark,
                                                  log_ctx=log_ctx)

        _lap('关键词学习(_auto_update_reason_keywords)')
        # 清洗物料名 → 有效 token（去掉代码段、数量、通用前缀、过滤词）
        ignore_terms_list = [t.term for t in AftersaleShippingIgnoreTerm.query.all()]
        cleaned_tokens = sorted(self._parse_product_tokens(products or [], ignore_terms_list))
        log_ctx['cleaned']['product_tokens'] = cleaned_tokens

        # 自动将简称关键词合并到简称库（使用清洗后的 token，而非原始名称）
        alias_ids_used = list({rd['shipping_alias_id'] for rd in reasons_data if rd.get('shipping_alias_id')})
        alias_obj_map = {
            a.id: a
            for a in AftersaleShippingAlias.query.filter(AftersaleShippingAlias.id.in_(alias_ids_used)).all()
        } if alias_ids_used else {}
        for rd in reasons_data:
            if rd.get('shipping_alias_id'):
                alias_id  = rd['shipping_alias_id']
                alias_obj = alias_obj_map.get(alias_id)
                kws_before = list(alias_obj.keywords or []) if alias_obj else []
                self.upsert_shipping_alias_by_id(alias_id, cleaned_tokens)
                kws_after  = list(alias_obj.keywords or []) if alias_obj else []
                added = [k for k in kws_after if k not in kws_before]
                log_ctx['alias_learning'].append({
                    'alias_id':      alias_id,
                    'alias_name':    alias_obj.name if alias_obj else None,
                    'tokens_added':  added,
                    'keywords_total': len(kws_after),
                })

        _lap('简称关键词学习(upsert_shipping_alias)')
        # 词典自动建议：检测过滤词候选（_upsert_dict_suggestion 内自动追加到 log_ctx）
        if products:
            self._check_ignore_term_candidates(products)

        _lap('过滤词候选检测(_check_ignore_term_candidates)')
        # 原因-简称亲和度：累积 reason_id + shipping_alias_id 共现次数
        self._upsert_reason_alias_affinity(reasons_data)

        _lap('亲和度更新(_upsert_reason_alias_affinity)')
        db.session.commit()
        _lap('db.commit')

        self._active_log_ctx = None   # 清除，避免后续调用误用
        self._invalidate_case_vec_cache()  # 新工单录入后使历史向量缓存失效，下次匹配重建
        write_confirm_log(log_ctx)
        _lap('写日志文件(总耗时)')
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
    _KW_PROMOTE_THRESHOLD = 2
    # 关键词晋升的最低质量分（0~1）
    _KW_MIN_QUALITY_SCORE = 0.45
    # 每个原因最多保留关键词数
    _KW_MAX_TOTAL = 30
    # 跨原因高频抑制：同一候选词在 >=N 个原因候选池出现时不晋升
    _KW_GLOBAL_HOT_THRESHOLD = 3
    # auto_match 历史相似度阶段上限（CPU 防护，difflib 兜底用）
    _AUTO_MATCH_HISTORY_LIMIT = 180
    # 已确认工单语义向量缓存（confirm_case 后失效；None = 未构建）
    _CASE_VEC_CACHE = None
    # 向量缓存最多纳入的已确认工单数
    _CASE_VEC_CACHE_LIMIT = 400

    @classmethod
    def _invalidate_case_vec_cache(cls):
        cls._CASE_VEC_CACHE = None

    def _get_case_vec_cache(self):
        """
        构建/返回已确认工单文本的向量缓存，供 auto_match 历史语义检索使用。
        - 首次调用时查库 + bge 编码，结果缓存在类变量中
        - confirm_case 成功后调用 _invalidate_case_vec_cache 使缓存失效
        - 返回 {'texts': [...], 'reason_ids': [[rid, ...], ...], 'vecs': ndarray|None}
        """
        if AftersaleRepository._CASE_VEC_CACHE is not None:
            return AftersaleRepository._CASE_VEC_CACHE

        from sqlalchemy.orm import selectinload
        confirmed_cases = (
            AftersaleCase.query
            .filter_by(status='confirmed')
            .filter(AftersaleCase.seller_remark.isnot(None))
            .options(selectinload(AftersaleCase.case_reasons))
            .order_by(AftersaleCase.processed_at.desc())
            .limit(self._CASE_VEC_CACHE_LIMIT)
            .all()
        )

        texts, reason_ids_per_case = [], []
        for case in confirmed_cases:
            if not case.seller_remark or not case.seller_remark.strip():
                continue
            rids = [cr.reason_id for cr in case.case_reasons if cr.reason_id]
            if not rids:
                continue
            t = case.seller_remark.lower()
            t = self._DATE_RE.sub(' ', t)
            t = self._NUM_RE.sub(' ', t)
            t = self._SPACES_RE.sub(' ', t).strip()[:100]
            if not t:
                continue
            texts.append(t)
            reason_ids_per_case.append(rids)

        cache = {'texts': texts, 'reason_ids': reason_ids_per_case, 'vecs': None}

        # 用 bge 对工单文本编码（模型不可用时 vecs 保持 None，退回 difflib）
        try:
            import model_manager
            model = model_manager.get_model()
            if model is not None and texts:
                cache['vecs'] = model_manager.encode(texts)   # (N, dim)
        except Exception:
            pass

        AftersaleRepository._CASE_VEC_CACHE = cache
        return cache
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
        short_keep_terms = {
            (r.term or '').strip().lower()
            for r in AftersaleReasonShortKeepTerm.query
            .filter(AftersaleReasonShortKeepTerm.enabled.is_(True))
            .all()
            if (r.term or '').strip()
        }
        return {
            'stopwords': stopwords,
            'short_keep_terms': short_keep_terms,
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
            'short_keep_terms': sorted(rules['short_keep_terms']),
        }

    def replace_reason_keyword_rules(self, stopwords, short_keep_terms=None):
        AftersaleReasonStopword.query.delete()
        AftersaleReasonShortKeepTerm.query.delete()

        for i, term in enumerate(stopwords or []):
            t = (term or '').strip()
            if t:
                db.session.add(AftersaleReasonStopword(term=t, sort_order=i))
        for i, term in enumerate(short_keep_terms or []):
            t = (term or '').strip()
            if t:
                db.session.add(AftersaleReasonShortKeepTerm(term=t, sort_order=i))
        db.session.commit()
        self._invalidate_reason_rule_cache()

    # ── 产品留言词典（材质/颜色/驱动/尺寸）────────────────────────────────────

    # 短时缓存，避免每次 suggest_product 都查库
    _REMARK_DICT_CACHE    = None
    _REMARK_DICT_CACHE_TS = None
    _REMARK_DICT_CACHE_TTL_SEC = 120

    @classmethod
    def _invalidate_remark_dict_cache(cls):
        cls._REMARK_DICT_CACHE    = None
        cls._REMARK_DICT_CACHE_TS = None

    @classmethod
    def _load_remark_dict(cls):
        """从 DB 加载词典并结构化，返回 {materials, colors, drive_types, sizes}。"""
        rows = (
            AftersaleProductRemarkDict.query
            .filter(AftersaleProductRemarkDict.enabled.is_(True))
            .order_by(AftersaleProductRemarkDict.sort_order.asc(),
                      AftersaleProductRemarkDict.id.asc())
            .all()
        )
        result = {'materials': [], 'colors': [], 'drive_types': [], 'sizes': {}, 'series_aliases': {}}
        for r in rows:
            if r.type == 'material':
                result['materials'].append(r.value)
            elif r.type == 'color':
                result['colors'].append(r.value)
            elif r.type == 'drive_type':
                result['drive_types'].append(r.value)
            elif r.type == 'size' and r.display:
                result['sizes'][r.value] = r.display
            elif r.type == 'series_alias' and r.display:
                # value=买家非正式名（小写存储），display=官方系列基础名
                result['series_aliases'][r.value.lower().strip()] = r.display.strip()
        return result

    @classmethod
    def _get_remark_dict(cls):
        """带缓存的词典读取，供 suggest_product 内部使用。"""
        now = now_cst()
        if (cls._REMARK_DICT_CACHE is not None and cls._REMARK_DICT_CACHE_TS is not None
                and (now - cls._REMARK_DICT_CACHE_TS).total_seconds() <= cls._REMARK_DICT_CACHE_TTL_SEC):
            return cls._REMARK_DICT_CACHE
        cls._REMARK_DICT_CACHE    = cls._load_remark_dict()
        cls._REMARK_DICT_CACHE_TS = now
        return cls._REMARK_DICT_CACHE

    def get_product_remark_dict(self):
        """API 用：返回全量词典（含 enabled=False 的，供前端管理）。"""
        rows = (
            AftersaleProductRemarkDict.query
            .order_by(AftersaleProductRemarkDict.type.asc(),
                      AftersaleProductRemarkDict.sort_order.asc(),
                      AftersaleProductRemarkDict.id.asc())
            .all()
        )
        return [r.to_dict() for r in rows]

    def replace_product_remark_dict(self, items):
        """全量替换词典（先删后写），items 为 list[{type, value, display?, enabled?, sort_order?}]。"""
        AftersaleProductRemarkDict.query.delete()
        for i, item in enumerate(items or []):
            type_  = (item.get('type') or '').strip()
            value  = (item.get('value') or '').strip()
            if not type_ or not value:
                continue
            db.session.add(AftersaleProductRemarkDict(
                type=type_,
                value=value,
                display=(item.get('display') or '').strip() or None,
                enabled=bool(item.get('enabled', True)),
                sort_order=int(item.get('sort_order', i)),
            ))
        db.session.commit()
        self._invalidate_remark_dict_cache()

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
        """原因学习/匹配用文本归一化：去日期数字噪声。"""
        if not text:
            return ''
        t = text.lower()
        t = cls._DATE_RE.sub(' ', t)
        t = cls._NUM_RE.sub(' ', t)
        t = cls._SPACES_RE.sub(' ', t).strip()
        return t

    @classmethod
    def _canonicalize_keyword(cls, kw):
        """将关键词归一为可复用 token。
        仅做 lower + 去空格，不重复执行同义词替换（调用方已通过 _normalize_reason_text 处理过）。"""
        return kw.lower().replace(' ', '')

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
    def _strip_stopwords(text, stopwords):
        """从文本中直接移除停用词子串，返回清洗后文本。
        按停用词长度降序处理，避免短词提前截断长词。"""
        if not stopwords or not text:
            return text
        result = text
        for sw in sorted(stopwords, key=len, reverse=True):
            if sw and sw in result:
                result = result.replace(sw, '')
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

    def _auto_update_reason_keywords(self, seller_remark, reason_ids, buyer_remark=None, log_ctx=None):
        """
        提交工单时更新候选词频池，达到阈值的候选词晋升到原因 keywords。
        流程：
          1. 从 seller_remark 中去除 buyer_remark 重复内容，再提取 n-gram 候选词
          2. 对每个 reason_id，upsert aftersale_keyword_candidate（count+1）
          3. count >= 阈值 且 尚未在 keywords 中 → 晋升，并从候选池删除
        log_ctx: 若非 None，向其写入关键词学习详情供日志输出。
        """
        if not seller_remark or not reason_ids:
            return
        effective_remark = self._subtract_buyer_remark(seller_remark, buyer_remark)
        # 预处理：直接从文本中移除停用词，再提取候选词
        rules    = self._get_reason_rules()
        stopwords = rules.get('stopwords', set())
        effective_remark = self._strip_stopwords(effective_remark, stopwords)
        new_kws  = self._extract_keywords_from_text(effective_remark)

        if log_ctx is not None:
            log_ctx['cleaned']['effective_remark'] = effective_remark
            log_ctx['cleaned']['extracted_keywords'] = sorted(new_kws)

        if not new_kws:
            return

        reasons = {r.id: r for r in AftersaleReason.query.filter(
            AftersaleReason.id.in_(reason_ids)
        ).all()}

        reason_id_list = list(reasons.keys())
        if not reason_id_list:
            return

        # 孤儿候选词清理：当 reason.keywords 被手动编辑后，候选池里该词的记录不会自动删除。
        # 每次 confirm 时顺手清理当前涉及原因的孤儿，避免脏数据积累。
        for rid, reason in reasons.items():
            kws_in_reason = {k.strip() for k in (reason.keywords or '').split(',') if k.strip()}
            if kws_in_reason:
                orphans = (
                    AftersaleKeywordCandidate.query
                    .filter(
                        AftersaleKeywordCandidate.reason_id == rid,
                        AftersaleKeywordCandidate.keyword.in_(list(kws_in_reason)),
                    )
                    .all()
                )
                for o in orphans:
                    db.session.delete(o)

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
            # 日志：收集该原因的学习结果
            if log_ctx is not None:
                log_ctx['keyword_learning'].append({
                    'reason_id':   rid,
                    'reason_name': reason.name,
                    'promoted':    [],
                    'suppressed':  [],
                })
                _log_reason = log_ctx['keyword_learning'][-1]
            else:
                _log_reason = None
            for kw in kws:
                spread = spread_map.get(kw, 0)
                if spread >= self._KW_GLOBAL_HOT_THRESHOLD:
                    # 跨多个原因高频出现，疑似泛化词，建议加入停用词
                    self._upsert_dict_suggestion(
                        'stopword', kw,
                        f'跨 {spread} 个原因候选池高频出现，疑似泛化词'
                    )
                    if _log_reason is not None:
                        _log_reason['suppressed'].append({'keyword': kw, 'spread': spread})
                    continue
                if kw not in kw_list and len(kw_list) < self._KW_MAX_TOTAL:
                    kw_list.append(kw)
                    # 晋升成功：建议用户考虑是否归类为故障词或部件词
                    self._upsert_dict_suggestion(
                        'promoted_keyword', kw,
                        f'已自动晋升至原因「{reason.name}」，可酌情归类为故障词或部件词'
                    )
                    if _log_reason is not None:
                        _log_reason['promoted'].append(kw)
                candidate = candidate_map.get((rid, kw))
                if candidate:
                    db.session.delete(candidate)
            reason.keywords = ','.join(kw_list)

        # 候选池超限时自动清理（不独立 commit，由 confirm_case 统一提交）
        self._auto_cleanup_candidates_if_needed()

    # ── 自动匹配 ────────────────────────────────────────────────────────────

    def auto_match(self, text, buyer_remark=None):
        """
        两阶段自动匹配，返回按置信度降序排列的 Top5 建议。
        阶段1：关键词库匹配
        阶段2：历史案例相似度（difflib）
        buyer_remark 若非空，先从 text 中去除买家留言内容再匹配，减少噪声。
        """
        if not text or not text.strip():
            return []

        # 预处理：去除买家留言片段，移除停用词（同义词归一已由语义向量承担，不再做文本替换）
        effective_text = self._subtract_buyer_remark(text, buyer_remark) if buyer_remark else text
        rules = self._get_reason_rules()
        stopwords = rules.get('stopwords', set())
        # 仅做日期/数字归一化，不再做同义词替换
        import re as _re
        text_lower = effective_text.lower()
        text_lower = self._DATE_RE.sub(' ', text_lower)
        text_lower = self._NUM_RE.sub(' ', text_lower)
        text_lower = self._SPACES_RE.sub(' ', text_lower).strip()
        text_lower = self._strip_stopwords(text_lower, stopwords)
        scores = {}   # reason_id -> score details

        def ensure_reason_score(reason_id, name, category_id, category_name):
            if reason_id not in scores:
                scores[reason_id] = {
                    'reason_id': reason_id,
                    'name': name,
                    'category_id': category_id,
                    'category_name': category_name,
                    'keyword_score': 0.0,
                    'history_score': 0.0,  # difflib 兜底分
                    'case_score':    0.0,  # 已确认工单语义相似度（主要历史信号）
                    'total_score':   0.0,
                    'matched_keywords': [],
                }
            return scores[reason_id]

        # 阶段1：关键词库匹配（joinedload 消除 category_obj 的 N+1 查询）
        from sqlalchemy.orm import joinedload
        reasons = AftersaleReason.query.options(
            joinedload(AftersaleReason.category_obj)
        ).all()
        for r in reasons:
            if not r.keywords:
                continue
            kws = [k.strip() for k in r.keywords.split(',') if k.strip()]
            if not kws:
                continue
            hits = []
            for kw in kws:
                kw_norm = self._canonicalize_keyword(kw)
                if not kw_norm:
                    continue
                direct_hit = kw_norm in text_lower
                sim = self._text_sim(text_lower, kw_norm)
                if not direct_hit and sim < 0.45:
                    continue
                quality = self._keyword_quality_score(kw_norm)
                if quality <= 0:
                    continue
                base   = max(sim, 0.6 if direct_hit else sim)
                weight = base * (0.55 + 0.45 * quality)
                if self._is_generic_keyword(kw_norm):
                    weight *= 0.4
                hits.append({'kw': kw_norm, 'weight': weight, 'direct_hit': direct_hit})

            if not hits:
                continue
            # 必须至少有一个关键词直接命中，防止纯 sim 滑动窗口误判
            if not any(h['direct_hit'] for h in hits):
                continue

            item = ensure_reason_score(
                r.id, r.name, r.category_id,
                r.category_obj.name if r.category_obj else None,
            )
            keyword_score = sum(h['weight'] for h in hits)
            coverage = len(hits) / len(kws)
            keyword_score *= (0.75 + 0.25 * coverage)
            item['keyword_score'] = round(max(item['keyword_score'], keyword_score), 4)
            item['matched_keywords'] = sorted(
                {h['kw'] for h in hits},
                key=lambda k: -max(h['weight'] for h in hits if h['kw'] == k),
            )[:6]

        # ── 提前编码 query_vec（两个语义阶段复用，避免重复推理）────────────────
        query_vec = None
        try:
            import model_manager
            import numpy as np
            _model = model_manager.get_model()
            if _model is not None and text_lower.strip():
                query_vec = model_manager.encode([text_lower])[0]   # (dim,)
        except Exception:
            pass

        # 阶段2：已确认工单历史匹配（始终运行，纠偏关键词排名）
        # 优先使用 bge 语义相似度；模型不可用时退回 difflib。
        # 工单向量缓存在进程生命周期内复用，confirm_case 后失效重建。
        try:
            case_cache = self._get_case_vec_cache()
            if case_cache and case_cache['texts']:
                if query_vec is not None and case_cache['vecs'] is not None:
                    # ── 语义路径：bge 余弦相似度 ──────────────────────────────
                    case_sims = np.dot(case_cache['vecs'], query_vec)   # (M,)
                    for i, rids in enumerate(case_cache['reason_ids']):
                        sim = float(case_sims[i])
                        if sim < 0.50:
                            continue
                        for rid in rids:
                            if rid not in scores:
                                r_obj = next((r for r in reasons if r.id == rid), None)
                                if r_obj is None:
                                    continue
                                item = ensure_reason_score(
                                    rid, r_obj.name, r_obj.category_id,
                                    r_obj.category_obj.name if r_obj.category_obj else None,
                                )
                            else:
                                item = scores[rid]
                            item['case_score'] = round(max(item['case_score'], sim), 4)
                else:
                    # ── 兜底路径：difflib（模型不可用时）───────────────────────
                    def _strip_num(t):
                        return re.sub(r'\d{4}[\.\-/]\d{1,2}[\.\-/]\d{1,2}', '', t).strip()
                    left = _strip_num(text_lower)[:80]
                    if left:
                        for i, (t, rids) in enumerate(
                            zip(case_cache['texts'], case_cache['reason_ids'])
                        ):
                            right = _strip_num(t)[:80]
                            if not right:
                                continue
                            ratio = difflib.SequenceMatcher(None, left, right).ratio()
                            if ratio < 0.30:
                                continue
                            for rid in rids:
                                if rid not in scores:
                                    r_obj = next((r for r in reasons if r.id == rid), None)
                                    if r_obj is None:
                                        continue
                                    item = ensure_reason_score(
                                        rid, r_obj.name, r_obj.category_id,
                                        r_obj.category_obj.name if r_obj.category_obj else None,
                                    )
                                else:
                                    item = scores[rid]
                                item['history_score'] = round(max(item['history_score'], ratio), 4)
        except Exception:
            pass   # 历史阶段异常不影响主流程

        # 阶段3：原因名语义匹配（bge 对原因名+关键词编码）
        # 召回关键词尚未覆盖的原因，并对已有候选做语义校正。
        try:
            if query_vec is not None:
                # 缓存原因向量：按原因列表 hash 决定是否重算
                reason_ids_key = tuple(r.id for r in reasons)
                if not hasattr(self, '_sem_cache') or self._sem_cache.get('key') != reason_ids_key:
                    # 用"原因名 + 关键词"拼接作为语义文档，比单纯用名称效果更好
                    reason_docs, reason_id_order = [], []
                    for r in reasons:
                        kws_part = '，'.join(k.strip() for k in (r.keywords or '').split(',') if k.strip())
                        doc = r.name + ('，' + kws_part if kws_part else '')
                        reason_docs.append(doc)
                        reason_id_order.append(r.id)
                    reason_vecs = model_manager.encode(reason_docs)   # (N, dim)
                    self._sem_cache = {
                        'key':  reason_ids_key,
                        'vecs': reason_vecs,
                        'ids':  reason_id_order,
                    }

                reason_vecs    = self._sem_cache['vecs']
                reason_id_list = self._sem_cache['ids']

                # 批量余弦相似度
                sims = np.dot(reason_vecs, query_vec)                 # (N,)
                for rid, sim in zip(reason_id_list, sims):
                    sim = float(sim)
                    if sim < 0.35:
                        continue
                    if rid not in scores:
                        r_obj = next((r for r in reasons if r.id == rid), None)
                        if r_obj is None:
                            continue
                        item = ensure_reason_score(
                            rid, r_obj.name, r_obj.category_id,
                            r_obj.category_obj.name if r_obj.category_obj else None,
                        )
                    else:
                        item = scores[rid]
                    item['semantic_score'] = round(max(item.get('semantic_score', 0.0), sim), 4)
        except Exception:
            pass   # 语义模块异常不影响主流程

        # 历史匹配语义验证加成
        # case_score 较高（≥0.65）且 query 与该原因语义对齐（sem≥0.35）时，
        # 说明历史相似度可信（而非文本凑巧相近），给予提权，最多 +25%。
        if query_vec is not None:
            for item in scores.values():
                cs = item.get('case_score', 0.0)
                if cs < 0.65:
                    continue
                sem = item.get('semantic_score', 0.0)
                if sem >= 0.35:
                    bonus = 0.15 + 0.10 * min(1.0, (sem - 0.35) / 0.30)  # 0.15~0.25
                    item['case_score'] = round(min(cs * (1 + bonus), 0.99), 4)

        # 统一融合与过滤
        results = []
        for item in scores.values():
            kw_score   = item['keyword_score']
            hs_score   = item['history_score']   # difflib 兜底分
            case_score = item.get('case_score',  0.0)   # 历史工单语义分（主要历史信号）
            sem_score  = item.get('semantic_score', 0.0)

            # 过滤：至少有一个信号达到门槛（case_score 语义信号可独立触发）
            if kw_score <= 0 and case_score < 0.50 and hs_score < 0.45 and sem_score < 0.55:
                continue

            # 融合：关键词为主，历史工单语义为有力辅助，原因名语义次之，difflib 兜底
            total = kw_score + case_score * 0.75 + sem_score * 0.45 + hs_score * 0.35
            if kw_score <= 0:
                total *= 0.85
            confidence = min(0.99, total / 2.2)

            # 来源：优先展示贡献最大的信号
            if case_score > 0 and case_score >= kw_score and case_score >= sem_score:
                source = 'case'
            elif kw_score > 0 and kw_score >= case_score * 0.9:
                source = 'keyword'
            elif sem_score >= kw_score and sem_score >= case_score and sem_score >= hs_score:
                source = 'semantic'
            else:
                source = 'history'

            results.append({
                'reason_id':       item['reason_id'],
                'name':            item['name'],
                'category_id':     item['category_id'],
                'category_name':   item['category_name'],
                'confidence':      round(confidence, 3),
                'source':          source,
                'matched_keywords': item['matched_keywords'],
                'keyword_score':   round(kw_score,   3),
                'case_score':      round(case_score, 3),
                'history_score':   round(hs_score,   3),
                'semantic_score':  round(sem_score,  3),
                'total_score':     round(total,       3),
            })

        results.sort(key=lambda x: x['total_score'], reverse=True)
        return {'items': results[:5], 'cleaned_text': text_lower}

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
        return {
            'channels':           channels,
            'provinces':          provinces,
            'cities':             cities,
            'model_ids':          model_ids,
            'reason_ids':         reason_ids,
            'shipping_alias_ids': shipping_alias_ids,
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

        # ── 两阶段匹配：结构化解析 + 生命周期优先 ──────────────────────────────
        # 阶段一：解析买家留言结构化字段 → 名称匹配 → 版本/新老款/生命周期过滤 → 候选系列
        # 阶段二：在候选系列内按尺寸/材质/颜色/变体 + 生命周期 精确匹配型号

        # ── 词典常量（从 DB 加载，带短时缓存）────────────────────────────────
        _remark_dict  = self._get_remark_dict()
        _MATERIALS    = _remark_dict['materials']
        _COLORS       = _remark_dict['colors']
        _DRIVE_TYPES  = _remark_dict['drive_types']
        _SIZE_TO_METER = _remark_dict['sizes']

        def _base_name(name):
            """去掉系列名版本号括号：'进取（V3.1）' → '进取'"""
            return re.sub(r'\s*[（(][Vv].*', '', name or '').strip()

        def _version_str(series_name):
            m = re.search(r'[Vv](\d+\.\d+)', series_name or '')
            return m.group(1) if m else None

        def _version_tuple(series_name):
            m = re.search(r'[Vv](\d+)\.(\d+)', series_name or '')
            return (int(m.group(1)), int(m.group(2))) if m else (0, 0)

        def _parse_remark(text):
            """将买家留言解析为结构化字段（版本/新老款/驱动/尺寸/材质/颜色/变体/基础名）"""
            remaining = text.strip()
            parsed = {
                'version': None, 'recency': None, 'size': None,
                'materials': set(), 'colors': set(), 'variant': None,
                'base_text': '',
            }
            # 版本号（V3.1 形式 或 独立 3.1 形式）
            m = re.search(r'[Vv](\d+\.\d+)', remaining)
            if m:
                parsed['version'] = m.group(1)
                remaining = remaining[:m.start()] + remaining[m.end():]
            else:
                m = re.search(r'(?<![0-9.])([1-9]\.\d+)(?![0-9.])', remaining)
                if m:
                    parsed['version'] = m.group(1)
                    remaining = remaining[:m.start()] + remaining[m.end():]
            # 新款/老款/智能款（优先匹配更长的词）
            for word, tag in [('智能款', 'smart'), ('新款', 'new'), ('老款', 'old')]:
                if word in remaining:
                    parsed['recency'] = tag
                    remaining = remaining.replace(word, '', 1)
                    break
            # 驱动方式（去除避免干扰基础名识别）
            for dt in _DRIVE_TYPES:
                if dt in remaining:
                    remaining = remaining.replace(dt, '', 1)
                    break
            # 材质
            for mat in _MATERIALS:
                if mat in remaining:
                    parsed['materials'].add(mat)
                    remaining = remaining.replace(mat, '', 1)
            # 颜色
            for col in _COLORS:
                if col in remaining:
                    parsed['colors'].add(col)
                    remaining = remaining.replace(col, '', 1)
            # 尺寸（080/100/105/120 等）
            m = re.search(r'(?<!\d)(0?80|0?90|100|105|120|140|160|180|200)(?!\d)', remaining)
            if m:
                raw = str(int(m.group(1)))  # 去前导零："080" → "80"
                if raw in _SIZE_TO_METER:
                    parsed['size'] = raw
                    remaining = remaining[:m.start()] + remaining[m.end():]
            # 变体字母（前置：C新款探索家；后置：探索家B）
            stripped = remaining.strip()
            m_front = re.match(r'^([A-D])(?=[\u4e00-\u9fff])', stripped, re.IGNORECASE)
            if m_front and len(stripped[m_front.end():].strip()) >= 2:
                # 剥离变体字母后剩余文本至少2字，否则该字母是产品名的一部分（如"A椅"）
                parsed['variant'] = m_front.group(1).upper()
                remaining = stripped[m_front.end():]
            else:
                m_back = re.search(r'(?<=[\u4e00-\u9fff0-9])([A-D])$', stripped, re.IGNORECASE)
                if m_back:
                    parsed['variant'] = m_back.group(1).upper()
                    remaining = stripped[:m_back.start()]
            parsed['base_text'] = re.sub(r'[\s/／,，]+', '', remaining).strip()
            return parsed

        # ── 加载所有型号行 + 生命周期 ─────────────────────────────────────────
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
        lifecycle_map = _get_lifecycle_map()
        current_ym    = now_cst().strftime('%Y-%m')

        # ── 构建系列字典 ─────────────────────────────────────────────────────
        series_dict = {}   # series_id → {meta, base_name, version_str, version_tuple, models}
        for row in model_rows:
            sid = row.series_id
            if sid not in series_dict:
                series_dict[sid] = {
                    'meta':          row,
                    'base_name':     _base_name(row.series_name),
                    'version_str':   _version_str(row.series_name),
                    'version_tuple': _version_tuple(row.series_name),
                    'models':        [],
                }
            series_dict[sid]['models'].append(row)

        # 按基础名分组，用于快速查找
        base_to_sids = defaultdict(list)
        for sid, sdata in series_dict.items():
            base_to_sids[sdata['base_name']].append(sid)

        # ── 阶段一：系列匹配 ─────────────────────────────────────────────────
        candidate_sids    = []
        series_confidence = None
        parsed            = {}
        version_confirmed = False

        # 非正式英文产品后缀正则（pro/plus/lite/max 等，不含 S/X 以免误剥官方后缀）
        _INFORMAL_SUFFIX_RE = re.compile(
            r'(?i)[\s\-_]*(pro\+?|plus|lite|max|mini|air|ultra|prime|go|elite|turbo)$'
        )

        def _run_tier_match(bt):
            """对给定 base_text 跑 tier1-4 名称匹配，返回 candidate_sids 列表。"""
            from difflib import SequenceMatcher as _SM
            _exact, _sub, _pre, _fuzz_best_r, _fuzz_best = [], [], [], 0.0, []
            for bn, sids in base_to_sids.items():
                if not bn or len(bn) < 2:
                    continue
                bn_l = bn.lower()
                if bn_l == bt:
                    _exact.extend(sids)
                elif bn_l in bt:
                    _sub.extend(sids)
                elif len(bt) >= 2 and bt in bn_l and len(bt) / len(bn_l) >= 0.5:
                    _pre.extend(sids)
                else:
                    r = _SM(None, bt, bn_l).ratio()
                    if r > _fuzz_best_r:
                        _fuzz_best_r, _fuzz_best = r, list(sids)
                    elif r == _fuzz_best_r and r > 0:
                        _fuzz_best.extend(sids)
            fuzz = _fuzz_best if (_fuzz_best_r >= 0.75 and not _exact and not _sub and not _pre) else []
            return _exact or _sub or _pre or fuzz

        if buyer_remark and buyer_remark.strip() and len(buyer_remark.strip()) >= 2:
            parsed    = _parse_remark(buyer_remark)
            base_text = parsed['base_text'].lower()

            # 0. 产品别名映射（用户在词典中配置的非正式名称 → 官方系列名）
            #    优先级最高，命中后直接替换 base_text 再走正常 tier 匹配
            _series_aliases = _remark_dict.get('series_aliases', {})
            if base_text in _series_aliases:
                base_text = _series_aliases[base_text].lower()
                parsed['base_text'] = base_text

            # 1a. 名称匹配：四级优先级（提取为 _run_tier_match 复用）
            #   tier1 精确：bn == base_text
            #   tier2 正向包含：系列名 in 买家文本（如"领航员"in"新款领航员S"）
            #   tier3 反向包含：买家文本 in 系列名（如"领航" in "领航员"，缩写/简称）
            #   tier4 模糊 difflib：处理"领航S"→"领航员S"之类省字缩写
            candidate_sids = _run_tier_match(base_text)

            # 1a-sfx. 非正式后缀兜底：去掉 pro/plus/lite 等后重试（如"领航pro"→"领航"→tier3 匹配"领航员"）
            if not candidate_sids and base_text:
                stripped = _INFORMAL_SUFFIX_RE.sub('', base_text).strip()
                if stripped and stripped != base_text and len(stripped) >= 2:
                    candidate_sids = _run_tier_match(stripped)
                    if candidate_sids:
                        # 后缀剥离后命中，置信度降为 medium
                        series_confidence = 'medium'

            # 1a-sem. 语义兜底：名称匹配均无结果时，用 bge 向量找最近系列
            if not candidate_sids and base_text.strip():
                try:
                    import model_manager
                    import numpy as np
                    model = model_manager.get_model()
                    if model is not None:
                        all_sids = list(series_dict.keys())
                        series_key = tuple(sorted(all_sids))
                        if (not hasattr(self, '_series_sem_cache') or
                                self._series_sem_cache.get('key') != series_key):
                            docs = [series_dict[s]['base_name'] for s in all_sids]
                            vecs = model_manager.encode(docs)
                            self._series_sem_cache = {
                                'key':  series_key,
                                'vecs': vecs,
                                'ids':  all_sids,
                            }
                        q_vec    = model_manager.encode([base_text])[0]
                        sims     = np.dot(self._series_sem_cache['vecs'], q_vec)
                        best_idx = int(np.argmax(sims))
                        if float(sims[best_idx]) >= 0.72:
                            candidate_sids = [self._series_sem_cache['ids'][best_idx]]
                except Exception:
                    pass   # 语义异常不影响主流程

            if candidate_sids:
                # 1b. 版本号过滤（精确命中则锁定版本）
                # 原则：留言明确给出版本号 + 系列名已匹配 → 版本不符直接置空，不降级
                if parsed['version']:
                    v_matched = [sid for sid in candidate_sids
                                 if series_dict[sid]['version_str'] == parsed['version']]
                    if v_matched:
                        candidate_sids    = v_matched
                        version_confirmed = True
                    else:
                        candidate_sids = []  # 版本明确但无匹配，终止匹配

                # 1c. 生命周期过滤：购买日期落在系列至少一个型号的上下市区间内
                def _is_series_active(sid, ym):
                    for mrow in series_dict[sid]['models']:
                        lc = lifecycle_map.get(mrow.model_id)
                        if not lc:
                            return True          # 无生命周期数据 → 视为在售
                        listed, delisted = lc
                        if listed and ym < listed:
                            continue             # 购买日期早于上市
                        if ym > (delisted or current_ym):
                            continue             # 购买日期晚于退市
                        return True              # 至少一个型号在售
                    return False

                if purchase_ym and lifecycle_map:
                    active = [sid for sid in candidate_sids if _is_series_active(sid, purchase_ym)]
                    if active:
                        candidate_sids = active
                    elif not parsed.get('version'):
                        # 精确/包含匹配：生命周期全部不符
                        # 模糊匹配：日期不符但名称有匹配 → 保留候选，降置信度（用户确认）
                        if fuzzy_sids and not exact_sids and not substring_sids and not prefix_sids:
                            series_confidence = 'low'   # 提前锁定低置信，不终止
                        elif len(candidate_sids) == 1:
                            # 单一候选：生命周期数据可能不准，保留并降低置信度
                            series_confidence = 'low'
                        else:
                            # 多候选且全部不符 → 无法确定版本，终止
                            candidate_sids = []

                # 1d. 新款/老款：取版本最高/最低的系列
                if parsed.get('recency') == 'new' and candidate_sids:
                    candidate_sids = [max(candidate_sids, key=lambda s: series_dict[s]['version_tuple'])]
                elif parsed.get('recency') == 'old' and candidate_sids:
                    candidate_sids = [min(candidate_sids, key=lambda s: series_dict[s]['version_tuple'])]

                # 1e. 多候选时按版本降序排列（新版本优先展示）
                if len(candidate_sids) > 1:
                    candidate_sids.sort(key=lambda s: series_dict[s]['version_tuple'], reverse=True)

                # 1f. 系列置信度
                n = len(candidate_sids)
                if version_confirmed or (parsed.get('recency') and n == 1) or n == 1:
                    series_confidence = 'high'
                elif n <= 3:
                    series_confidence = 'medium'
                else:
                    series_confidence = 'low'

        # ── 阶段二：型号匹配 ─────────────────────────────────────────────────
        def _score_model(mrow, purchase_ym):
            """按结构化字段对型号打分，返回 (match_score, lifecycle_ok)"""
            lc = lifecycle_map.get(mrow.model_id)
            lifecycle_ok = True
            if lc and purchase_ym:
                listed, delisted = lc
                too_early    = listed and purchase_ym < listed
                too_late     = purchase_ym > (delisted or current_ym)
                lifecycle_ok = not too_early and not too_late

            if not parsed:
                return 0, lifecycle_ok

            score = 0
            mname = mrow.model_name or ''
            mcode = getattr(mrow, 'model_code', '') or ''

            # 尺寸（精确米制匹配 +3，数字兜底 +1）
            if parsed.get('size'):
                meter = _SIZE_TO_METER.get(parsed['size'], '')
                if meter and meter in mname:
                    score += 3
                elif parsed['size'] in mname or parsed['size'] in mcode:
                    score += 1
            # 材质
            for mat in parsed.get('materials', set()):
                if mat in mname:
                    score += 2
            # 颜色
            for col in parsed.get('colors', set()):
                if col in mname:
                    score += 1
            # 变体字母（_B 或 -B 结尾）
            if parsed.get('variant'):
                v = parsed['variant']
                if mcode.endswith(f'-{v}') or mname.endswith(f'_{v}'):
                    score += 2
            # 智能款
            if parsed.get('recency') == 'smart' and '智能' in mname:
                score += 2

            return score, lifecycle_ok

        # 最高可能得分（用于置信度归一化）
        _max_mscore = 0
        if parsed:
            if parsed.get('size'):               _max_mscore += 3
            _max_mscore += 2 * len(parsed.get('materials', set()))
            _max_mscore += len(parsed.get('colors', set()))
            if parsed.get('variant'):            _max_mscore += 2
            if parsed.get('recency') == 'smart': _max_mscore += 2

        def _model_conf(score):
            if _max_mscore == 0: return None
            r = score / _max_mscore
            if r >= 0.7: return 'high'
            if r >= 0.4: return 'medium'
            return 'low'

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

        # ── 发货物料简称：绑定库匹配优先，历史频次二次验证兜底 ─────────────
        _ignore_terms_list = [t.term for t in AftersaleShippingIgnoreTerm.query.all()]
        product_tokens = sorted(self._parse_product_tokens(products or [], _ignore_terms_list))
        binding_shipping_id, _ = self.match_shipping_alias(products or [], seller_remark=seller_remark, buyer_remark=buyer_remark)
        history_shipping_id     = _top_alias_id(AftersaleCaseReason.shipping_alias_id)

        # 二次验证：只有当历史数据指向另一个简称时才降级（防止泛化词误命中）。
        # 若该产品从未有过确认工单（any_hist == 0），无历史可参考，直接信任关键词匹配。
        if binding_shipping_id and code_filters:
            any_hist = (
                db.session.query(AftersaleCaseReason.shipping_alias_id)
                .join(AftersaleCase, AftersaleCase.id == AftersaleCaseReason.case_id)
                .filter(AftersaleCase.status == 'confirmed')
                .filter(AftersaleCaseReason.shipping_alias_id.isnot(None))
                .filter(or_(*code_filters))
                .count()
            )
            if any_hist > 0:
                # 有历史数据：验证关键词命中的 alias 是否被历史支持
                binding_hist_count = (
                    db.session.query(AftersaleCaseReason.shipping_alias_id)
                    .join(AftersaleCase, AftersaleCase.id == AftersaleCaseReason.case_id)
                    .filter(AftersaleCase.status == 'confirmed')
                    .filter(AftersaleCaseReason.shipping_alias_id == binding_shipping_id)
                    .filter(or_(*code_filters))
                    .count()
                )
                if binding_hist_count == 0:
                    binding_shipping_id = None   # 历史指向其他简称，降级

        suggested_shipping_alias_id     = binding_shipping_id or history_shipping_id
        suggested_shipping_alias_source = (
            'library' if binding_shipping_id else ('history' if history_shipping_id else None)
        )

        # 历史原因：取 reason_id 出现最多的一条，并附带其 category_id 和频次
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
        suggested_reason_count       = None
        if reason_cnt:
            best_key = max(reason_cnt, key=reason_cnt.get)
            suggested_reason_id, suggested_reason_category_id = best_key
            suggested_reason_count = reason_cnt[best_key]

        # ── 组装返回 ─────────────────────────────────────────────────────
        suggestions = {
            'suggested_shipping_alias_id':     suggested_shipping_alias_id,
            'suggested_shipping_alias_source': suggested_shipping_alias_source,
            'suggested_reason_id':             suggested_reason_id,
            'suggested_reason_category_id':    suggested_reason_category_id,
            'suggested_reason_count':          suggested_reason_count,
            'product_tokens':                  product_tokens,
        }

        if not candidate_sids:
            # 没有找到系列匹配，但仍可返回辅助建议
            has_any = any(v is not None for v in suggestions.values())
            return suggestions if has_any else None

        # ── 组装 candidates（最多5个系列）────────────────────────────────────
        # series_confidence → 系列评分（用于进度条显示）
        _conf_to_score = {'high': 1.0, 'medium': 0.75, 'low': 0.5}
        s_score = _conf_to_score.get(series_confidence, 0.5)

        candidates = []
        for sid in candidate_sids[:5]:
            sdata  = series_dict[sid]
            s_meta = sdata['meta']

            # 对该系列所有型号打分
            scored_models = []
            for mrow in sdata['models']:
                ms, lc_ok = _score_model(mrow, purchase_ym)
                scored_models.append({
                    'id':               mrow.model_id,
                    'name':             mrow.model_name,
                    'model_code':       getattr(mrow, 'model_code', None),
                    'score':            round(ms / _max_mscore, 2) if _max_mscore else 0,
                    'model_confidence': _model_conf(ms),
                    'date_ok':          lc_ok,
                    '_raw':             ms,
                })
            # 排序：生命周期优先，其次匹配分
            scored_models.sort(key=lambda x: (x['date_ok'], x['_raw']), reverse=True)
            for m in scored_models:
                del m['_raw']

            best_m = scored_models[0] if scored_models else None
            candidates.append({
                'category_id':       s_meta.category_id,
                'category_name':     s_meta.category_name,
                'series_id':         sid,
                'series_name':       s_meta.series_name,
                'series_score':      s_score,
                'score':             s_score,   # 向后兼容（模板用 c.score 渲染进度条）
                'series_confidence': series_confidence,
                'model_id':          best_m['id']               if best_m else None,
                'model_name':        best_m['name']             if best_m else None,
                'model_code':        best_m['model_code']       if best_m else None,
                'model_confidence':  best_m['model_confidence'] if best_m else None,
                'date_ok':           best_m['date_ok']          if best_m else True,
                'models':            scored_models,
            })

        best = candidates[0]
        return {
            'category_id':       best['category_id'],
            'category_name':     best['category_name'],
            'series_id':         best['series_id'],
            'series_name':       best['series_name'],
            'series_confidence': series_confidence,
            'model_id':          best['model_id'],
            'model_name':        best['model_name'],
            'model_confidence':  best['model_confidence'],
            'date_ok':           best['date_ok'],
            'candidates':        candidates,
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

    # ── 简称库关键词自动合并（提交工单时调用，通过 ID 查找） ──────────────────

    def upsert_shipping_alias_by_id(self, alias_id, product_names):
        """提交工单时：从 product_tokens 中选出与简称名称重叠度最高的一个 token 写入关键词。
        每次工单只写一个 key；若已存在则跳过，避免重复积累。"""
        obj = AftersaleShippingAlias.query.get(alias_id)
        if not obj:
            return
        # 对 alias_name 做同义词归一，使"椅垫"和"座垫"这类词能匹配
        alias_name = self._normalize_reason_text(obj.name or '').replace(' ', '')

        def _overlap_score(token):
            """返回同义词归一后 token 与 alias_name 的最长公共子串长度（归一到 alias_name 长度）。"""
            t = self._normalize_reason_text(token).replace(' ', '')
            if not alias_name:
                return 0
            if t == alias_name:
                return 1.0
            best = 0
            for length in range(min(len(t), len(alias_name)), 1, -1):
                for i in range(len(t) - length + 1):
                    if t[i:i + length] in alias_name:
                        best = length
                        break
                if best == length:
                    break
            return best / len(alias_name)

        # 过滤掉零重叠的 token，对剩余按重叠分降序，取最高分的一个
        candidates = [
            (n.strip(), _overlap_score(n.strip()))
            for n in (product_names or [])
            if n and n.strip() and _overlap_score(n.strip()) > 0
        ]
        if not candidates:
            return
        best_token = max(candidates, key=lambda x: x[1])[0]

        existing = set(obj.keywords or [])
        if best_token in existing:
            return  # 已存在，跳过
        obj.keywords = list(existing | {best_token})

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

    # 热路径预编译正则（类级别，进程内只编译一次）
    _NUM_RE    = re.compile(r'\d+(?:\.\d+)?')
    _SPACES_RE = re.compile(r'\s+')

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

    @staticmethod
    def _parse_product_tokens(products, ignore_terms):
        """
        从发货物料列表中提取有效词 token。

        步骤：
          1. 按空格分割物料名
          2. 丢弃 code 段（含 "-" 且含数字的段，如 "14PL01197-A01"）
          3. 丢弃数量段（匹配 ×N 或 NxN，如 "×3"）
          4. 剩余段按 "_" 再分割
          5. 丢弃与任意 ignore_term 完全相同（大小写不敏感精确匹配）的子词
          6. 丢弃空串和单字符
        返回去重后的 token set（小写）。
        """
        _CODE_RE = re.compile(r'^[A-Za-z0-9]+-[A-Za-z0-9\-]+$')
        _QTY_RE  = re.compile(r'^[×xX×]\d+$|^\d+[×xX×]$|^\d+$')
        ignore_lower = [t.lower() for t in ignore_terms if t]
        tokens = set()
        for p in products:
            name = (p.get('name') or '').strip()
            if not name:
                continue
            for seg in name.split(' '):
                seg = seg.strip()
                if not seg:
                    continue
                # 丢弃物料编号和数量标记
                if _CODE_RE.match(seg) or _QTY_RE.match(seg):
                    continue
                # 按 "_" 再分割
                for part in seg.split('_'):
                    part = part.strip().lower()
                    if not part or len(part) <= 1:
                        continue
                    # 丢弃与 ignore_term 完全相同的子词（精确匹配）
                    if any(ig == part for ig in ignore_lower):
                        continue
                    tokens.add(part)
        return tokens

    def match_shipping_alias(self, products, seller_remark=None, buyer_remark=None):
        """
        根据发货物料列表（含 name 字段）匹配最佳发货物料简称。
        返回 (alias_id, score) 或 (None, 0)。

        三阶段匹配：
        1. 关键词匹配：绝对命中数优先，覆盖率次之（精准但依赖 keyword 配置）
        2. 备注 × 简称名 tie-breaking：同分时用 seller/buyer 备注文本与简称名的
           字符覆盖度区分歧义候选（如"气弹簧"vs"气弹簧手柄"）
        3. 语义向量（bge）：模型就绪时对所有简称计算余弦相似度，作为无命中时的
           兜底（sem >= 0.55）或命中数 <= 1 时的参与者（融合权重 kw*0.7 + sem*0.3）

        匹配使用 _parse_product_tokens 提取的 token 集合；
        旧格式 keyword（含 "_"）兼容回退到完整名称包含匹配。
        """
        if not products:
            return None, 0.0
        ignore_terms = [t.term for t in AftersaleShippingIgnoreTerm.query.all()]
        product_tokens = self._parse_product_tokens(products, ignore_terms)
        # 旧格式 fallback：完整 combined_name 用于含 "_" 的 keyword
        product_names = [p.get('name', '') or '' for p in products]
        combined_name = ' '.join(product_names).lower()

        # 阶段1：关键词匹配，收集所有别名的 (matched, ratio)
        aliases = AftersaleShippingAlias.query.all()
        kw_scores = {}   # alias_id → (matched, ratio)
        for obj in aliases:
            kws = [k for k in (obj.keywords or []) if k]
            if not kws:
                continue
            matched = 0
            for k in kws:
                kl = k.lower()
                if kl in product_tokens:
                    matched += 1
                elif '_' in kl and kl in combined_name:
                    matched += 1
            if matched == 0:
                continue
            ratio = matched / len(kws)
            kw_scores[obj.id] = (matched, ratio)

        best_kw_matched = max((v[0] for v in kw_scores.values()), default=0)

        # 阶段2：语义向量评分（仅在模型就绪时）
        sem_scores = {}  # alias_id → cosine_sim
        try:
            import model_manager
            import numpy as np
            model = model_manager.get_model()
            if model is not None and combined_name.strip():
                alias_ids_key = tuple(sorted(a.id for a in aliases))
                if (not hasattr(self, '_alias_sem_cache') or
                        self._alias_sem_cache.get('key') != alias_ids_key):
                    alias_docs = [a.name for a in aliases]
                    alias_vecs = model_manager.encode(alias_docs)
                    self._alias_sem_cache = {
                        'key':  alias_ids_key,
                        'vecs': alias_vecs,
                        'ids':  [a.id for a in aliases],
                    }
                query_vec  = model_manager.encode([combined_name])[0]
                alias_vecs = self._alias_sem_cache['vecs']
                alias_ids  = self._alias_sem_cache['ids']
                sims = np.dot(alias_vecs, query_vec)
                for aid, sim in zip(alias_ids, sims):
                    sem_scores[aid] = float(sim)
        except Exception:
            pass   # 语义模块异常不影响主流程

        # ── 备注 × 简称名 tie-breaking 工具 ──────────────────────────────────
        # 当多个简称关键词分相同时（如"气弹簧"和"气弹簧手柄"关联同一物料清单），
        # 用 seller/buyer 备注中出现的字符序列对简称名的覆盖量来区分。
        # 覆盖量 = SequenceMatcher 匹配块的字符总数（绝对值，不归一）：
        #   同分时覆盖量更高的候选获胜；仍相同时选名称更长者（更具体）。
        remark_text = ' '.join(filter(None, [
            (seller_remark or '').lower(),
            (buyer_remark  or '').lower(),
        ])).strip()
        alias_names = {obj.id: obj.name.lower() for obj in aliases}

        def _remark_name_coverage(aid):
            """计算简称名称在备注中被覆盖的字符数（difflib 匹配块累计）。"""
            if not remark_text:
                return 0
            name = alias_names.get(aid, '')
            if not name:
                return 0
            import difflib as _dl
            blocks = _dl.SequenceMatcher(None, name, remark_text, autojunk=False).get_matching_blocks()
            return sum(size for _, _, size in blocks)

        # 融合：
        # - 关键词命中 >= 2 时直接用关键词结果（可信度高），同分时备注 tie-breaking
        # - 关键词命中 <= 1 时引入语义分参与排序
        # - 关键词无命中时语义兜底（阈值 0.55）
        if best_kw_matched >= 2 or not sem_scores:
            # 找出与最高命中数并列的全部候选
            top_candidates = [(aid, m, r) for aid, (m, r) in kw_scores.items() if m == best_kw_matched]
            if len(top_candidates) == 1:
                aid, _, r = top_candidates[0]
                return aid, r
            # 同分 → 备注 tie-breaking：覆盖量大优先，相同则名称长优先，再看覆盖率
            top_candidates.sort(key=lambda x: (
                _remark_name_coverage(x[0]),   # 覆盖字符数（降序）
                len(alias_names.get(x[0], '')),# 名称长度（降序，更具体）
                x[2],                          # 关键词覆盖率（降序）
            ), reverse=True)
            best_id = top_candidates[0][0]
            return best_id, top_candidates[0][2]

        # 融合评分
        all_ids = set(kw_scores) | (set(sem_scores) if best_kw_matched == 0 else set())
        best_id, best_score = None, -1.0
        for aid in all_ids:
            m, r = kw_scores.get(aid, (0, 0.0))
            sem  = sem_scores.get(aid, 0.0)
            if best_kw_matched == 0:
                # 无关键词命中：纯语义兜底，需超过阈值
                if sem < 0.55:
                    continue
                score = sem
            else:
                # 命中数 == 1：关键词 + 语义融合
                kw_norm = min(m / max(best_kw_matched, 1), 1.0) * r
                score = kw_norm * 0.7 + sem * 0.3
            if score > best_score:
                best_score, best_id = score, aid
        return best_id, best_score

    def migrate_alias_keywords(self):
        """
        将 aftersale_shipping_alias.keywords 中旧格式的完整物料名
        （含"_"分隔的无效前缀，如"原材料_塑胶件_书包挂钩盖子"）
        拆分为有效 token，就地更新。
        返回 (总简称数, 变更数)。
        """
        ignore_terms = [t.term for t in AftersaleShippingIgnoreTerm.query.all()]
        aliases = AftersaleShippingAlias.query.all()
        changed = 0
        for alias in aliases:
            if not alias.keywords:
                continue
            new_kws = []
            dirty = False
            for kw in alias.keywords:
                if not kw:
                    continue
                if '_' in kw:
                    # 旧格式：拆分
                    tokens = self._parse_product_tokens(
                        [{'name': kw, 'code': ''}], ignore_terms
                    )
                    if tokens:
                        new_kws.extend(sorted(tokens))
                        dirty = True
                    else:
                        new_kws.append(kw)
                else:
                    new_kws.append(kw)
            if dirty:
                # 去重、保序
                seen = set()
                deduped = []
                for k in new_kws:
                    if k not in seen:
                        seen.add(k)
                        deduped.append(k)
                alias.keywords = deduped
                changed += 1
        if changed:
            db.session.commit()
        return len(aliases), changed

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

    # ── 发货物料歧义词 ─────────────────────────────────────────────────────────

    def get_all_ambiguous_terms(self):
        return AftersaleShippingAmbiguousTerm.query.order_by(
            AftersaleShippingAmbiguousTerm.created_at.asc()
        ).all()

    def create_ambiguous_term(self, term):
        obj = AftersaleShippingAmbiguousTerm(term=term)
        db.session.add(obj)
        db.session.commit()
        return obj

    def delete_ambiguous_term(self, term_id):
        obj = AftersaleShippingAmbiguousTerm.query.get(term_id)
        if not obj:
            return False
        db.session.delete(obj)
        db.session.commit()
        return True

    # ── 词典自动建议 ──────────────────────────────────────────────────────────

    # 已知通用物料名前缀词，首次出现即建议加入过滤词
    _KNOWN_GENERIC_PREFIXES = {
        '原材料', '塑胶件', '五金件', '配件', '辅料',
        '半成品', '成品', '包材', '耗材', '工具',
    }

    def _upsert_dict_suggestion(self, sug_type, value, reason_text, meta=None):
        """
        插入或更新词典建议记录（count+1）。
        已拒绝的建议不再重复触发；在调用方的 session 内执行，不独立 commit。
        meta: 附加 JSON 数据（synonym_candidate 存涉及的 reason_ids 等）。
        若当前处于 confirm_case 流程中（_active_log_ctx 非空），同步写入日志上下文。
        """
        existing = AftersaleDictSuggestion.query.filter_by(
            type=sug_type, value=value
        ).first()
        if existing:
            if existing.status == 'rejected':
                return
            existing.count += 1
            # 合并 meta 中的 reason_ids（避免覆盖旧数据）
            if meta and isinstance(meta.get('reason_ids'), list) and existing.meta:
                old_ids = existing.meta.get('reason_ids') or []
                merged = list(set(old_ids) | set(meta['reason_ids']))
                existing.meta = {**existing.meta, 'reason_ids': merged}
            elif meta:
                existing.meta = meta
            action = 'count+1'
        else:
            db.session.add(AftersaleDictSuggestion(
                type=sug_type, value=value, reason=reason_text, meta=meta
            ))
            action = 'new'

        # 写入日志上下文（如果在 confirm_case 流程中）
        ctx = getattr(self, '_active_log_ctx', None)
        if ctx is not None:
            ctx['dict_suggestions'].append({
                'type':   sug_type,
                'value':  value,
                'reason': reason_text,
                'action': action,
            })

    def _check_ignore_term_candidates(self, products):
        """
        分析工单物料 token，对已知通用前缀词或极短词（≤2字）生成过滤词建议。
        随着工单积累，count 升高的建议自然浮出水面供用户审核。
        """
        raw_tokens = self._parse_product_tokens(products, [])
        if not raw_tokens:
            return
        existing_ignore = {t.term.lower() for t in AftersaleShippingIgnoreTerm.query.all()}
        for token in raw_tokens:
            if token in existing_ignore:
                continue
            if token in self._KNOWN_GENERIC_PREFIXES or len(token) <= 2:
                self._upsert_dict_suggestion(
                    'ignore_term', token,
                    '物料名中的通用前缀词，建议加入过滤词以提升简称匹配精度'
                )

    def _upsert_reason_alias_affinity(self, reasons_data):
        """
        工单确认时，对每条同时有 reason_id 和 shipping_alias_id 的 reason 行，
        将 (reason_id, shipping_alias_id) 共现次数 +1。
        在调用方的 session 内执行，不独立 commit。
        """
        pairs = {
            (int(rd['reason_id']), int(rd['shipping_alias_id']))
            for rd in (reasons_data or [])
            if rd.get('reason_id') and rd.get('shipping_alias_id')
        }
        if not pairs:
            return

        # 批量查询已有记录
        existing = (
            AftersaleReasonAliasAffinity.query
            .filter(
                db.tuple_(
                    AftersaleReasonAliasAffinity.reason_id,
                    AftersaleReasonAliasAffinity.shipping_alias_id,
                ).in_(list(pairs))
            )
            .all()
        )
        existing_map = {(r.reason_id, r.shipping_alias_id): r for r in existing}

        for pair in pairs:
            rec = existing_map.get(pair)
            if rec:
                rec.count += 1
            else:
                db.session.add(AftersaleReasonAliasAffinity(
                    reason_id=pair[0], shipping_alias_id=pair[1]
                ))

    def get_alias_affinity(self, reason_id, alias_ids):
        """
        查询指定 reason_id 对各 alias_id 的亲和度 count。
        返回 {alias_id: count} 字典，无记录的 alias_id 不出现在结果中。
        """
        if not reason_id or not alias_ids:
            return {}
        rows = (
            AftersaleReasonAliasAffinity.query
            .filter_by(reason_id=reason_id)
            .filter(AftersaleReasonAliasAffinity.shipping_alias_id.in_(alias_ids))
            .all()
        )
        return {r.shipping_alias_id: r.count for r in rows}

    def get_dict_suggestions(self, type_filter=None, status='pending'):
        q = AftersaleDictSuggestion.query.filter_by(status=status)
        if type_filter:
            q = q.filter_by(type=type_filter)
        return q.order_by(
            AftersaleDictSuggestion.count.desc(),
            AftersaleDictSuggestion.created_at.asc()
        ).all()

    def accept_dict_suggestion(self, sug_id):
        """接受建议：将词写入对应词典表，并标记 status=accepted。"""
        from sqlalchemy.exc import IntegrityError
        sug = AftersaleDictSuggestion.query.get(sug_id)
        if not sug or sug.status != 'pending':
            return None, '建议不存在或已处理'
        sug.status = 'accepted'
        try:
            if sug.type == 'stopword':
                db.session.add(AftersaleReasonStopword(term=sug.value))
            elif sug.type == 'ignore_term':
                db.session.add(AftersaleShippingIgnoreTerm(term=sug.value))
            # promoted_keyword：关键词已晋升到 reason.keywords，仅确认即可
            db.session.commit()
            self._invalidate_reason_rule_cache()
        except IntegrityError:
            db.session.rollback()
            sug.status = 'accepted'
            db.session.commit()
        return sug, None

    def reject_dict_suggestion(self, sug_id):
        sug = AftersaleDictSuggestion.query.get(sug_id)
        if not sug or sug.status != 'pending':
            return None
        sug.status = 'rejected'
        db.session.commit()
        return sug

    # ── 候选池维护 ────────────────────────────────────────────────────────────

    _CANDIDATE_MAX_ROWS = 1000  # 候选池上限，超出时自动清理 count=1 的噪声词

    def cleanup_keyword_candidates(self, min_count=2, top_per_reason=200):
        """手动清理接口：删除低频噪声词 + 每原因保留 top_per_reason 条。"""
        noise = AftersaleKeywordCandidate.query.filter(
            AftersaleKeywordCandidate.count < min_count
        ).all()
        noise_count = len(noise)
        for row in noise:
            db.session.delete(row)
        db.session.flush()

        overflow_count = 0
        for (rid,) in db.session.query(AftersaleKeywordCandidate.reason_id).distinct().all():
            rows = (
                AftersaleKeywordCandidate.query
                .filter_by(reason_id=rid)
                .order_by(AftersaleKeywordCandidate.count.desc())
                .all()
            )
            if len(rows) > top_per_reason:
                for row in rows[top_per_reason:]:
                    db.session.delete(row)
                    overflow_count += 1

        db.session.commit()
        remaining = AftersaleKeywordCandidate.query.count()
        return {
            'deleted_noise':    noise_count,
            'deleted_overflow': overflow_count,
            'remaining':        remaining,
        }

    def _auto_cleanup_candidates_if_needed(self):
        """超出上限时，按 id 升序删除 count=1 的噪声词，直到降回上限以内。
        在 session 内执行，不独立 commit（由调用方统一提交）。"""
        total = AftersaleKeywordCandidate.query.count()
        if total <= self._CANDIDATE_MAX_ROWS:
            return
        excess = total - self._CANDIDATE_MAX_ROWS
        # 取最旧的 count=1 行（id 升序），只取需要删除的数量
        to_delete = (
            AftersaleKeywordCandidate.query
            .filter(AftersaleKeywordCandidate.count == 1)
            .order_by(AftersaleKeywordCandidate.id.asc())
            .limit(excess)
            .all()
        )
        for row in to_delete:
            db.session.delete(row)

    def get_keyword_candidate_stats(self):
        """返回候选池概况：总行数、原因数、各 count 分布。"""
        total    = AftersaleKeywordCandidate.query.count()
        reasons  = db.session.query(
            db.func.count(db.func.distinct(AftersaleKeywordCandidate.reason_id))
        ).scalar() or 0
        dist_rows = db.session.query(
            AftersaleKeywordCandidate.count,
            db.func.count(AftersaleKeywordCandidate.id).label('n'),
        ).group_by(AftersaleKeywordCandidate.count).order_by(AftersaleKeywordCandidate.count).all()
        distribution = {int(r.count): int(r.n) for r in dist_rows}
        return {'total': total, 'reasons': reasons, 'distribution': distribution}

    def get_series_monthly_by_model_id(self, model_id: int) -> list:
        """
        按月聚合指定 model_id 所属系列的售后工单数 + 发货实际数量。
        仅返回有售后工单的月份，x 轴由前端决定。
        """
        from sqlalchemy import func
        from database.models.product.category import ProductModel, ProductSeries
        from database.models.product.finished import ProductFinished
        from database.models.shipping import ShippingOrderFinished, ShippingOperatorType

        # 找到该 model 所属的 series_id
        model_row = db.session.query(ProductModel.series_id).filter_by(id=model_id).first()
        if not model_row:
            return []
        series_id = model_row.series_id

        # 该系列下所有 model id
        sibling_model_ids = [
            r.id for r in db.session.query(ProductModel.id).filter_by(series_id=series_id).all()
        ]
        if not sibling_model_ids:
            return []

        # 按月统计售后工单数（去重 case，同一工单只算一次）
        aftersale_sub = (
            db.session.query(
                func.date_format(AftersaleCase.shipped_date, '%Y-%m').label('month'),
                func.count(func.distinct(AftersaleCase.id)).label('aftersale_count'),
            )
            .join(AftersaleCaseReason, AftersaleCaseReason.case_id == AftersaleCase.id)
            .filter(
                AftersaleCaseReason.model_id.in_(sibling_model_ids),
                AftersaleCase.shipped_date.isnot(None),
                AftersaleCase.status != 'ignored',
            )
            .group_by('month')
            .order_by('month')
            .all()
        )

        if not aftersale_sub:
            return []

        # 有售后数据的月份集合
        aftersale_months = {r.month: int(r.aftersale_count) for r in aftersale_sub}

        # 该系列所有成品 code（用于关联 shipping_order_finished）
        series_finished_codes = [
            r.code for r in (
                db.session.query(ProductFinished.code)
                .join(ProductModel, ProductFinished.model_id == ProductModel.id)
                .filter(ProductModel.series_id == series_id)
                .filter(ProductFinished.status != 'ignored')
                .all()
            )
        ]

        # 按月统计发货实际数量（排除售后操作人）
        shipping_by_month = {}
        if series_finished_codes:
            aftersale_ops = db.session.query(ShippingOperatorType.operator).filter_by(type='aftersale').subquery()
            sof = ShippingOrderFinished
            shipping_rows = (
                db.session.query(
                    func.date_format(sof.shipped_date, '%Y-%m').label('month'),
                    func.sum(sof.actual_quantity).label('actual'),
                )
                .filter(
                    sof.finished_code.in_(series_finished_codes),
                    sof.shipped_date.isnot(None),
                    db.or_(sof.operator.is_(None), ~sof.operator.in_(aftersale_ops)),
                )
                .group_by('month')
                .all()
            )
            shipping_by_month = {r.month: float(r.actual) if r.actual else 0.0 for r in shipping_rows}

        # 仅输出有售后数据的月份，按月排序
        result = []
        for month in sorted(aftersale_months):
            result.append({
                'month':           month,
                'aftersale_count': aftersale_months[month],
                'shipping_actual': shipping_by_month.get(month, 0.0),
            })
        return result

    # ── 通用设置 ─────────────────────────────────────────────────────────────

    _SETTINGS_DEFAULTS = {
        'reason_auto_fill_threshold': {
            'value': 0.35,
            'label': '原因自动填写最低语义评分',
        },
    }

    def get_settings(self):
        """读取所有设置，缺失的键用默认值补全后返回 list[dict]"""
        from database.models.aftersale import AftersaleSetting
        rows = {r.key: r for r in AftersaleSetting.query.all()}
        result = []
        for key, meta in self._SETTINGS_DEFAULTS.items():
            if key in rows:
                result.append(rows[key].to_dict())
            else:
                result.append({'key': key, 'value': meta['value'], 'label': meta['label'], 'updated_at': None})
        return result

    def update_setting(self, key, value):
        """更新单个设置，键不在白名单时拒绝"""
        import json
        from database.models.aftersale import AftersaleSetting
        if key not in self._SETTINGS_DEFAULTS:
            return False, f'未知设置项: {key}'
        row = AftersaleSetting.query.filter_by(key=key).first()
        encoded = json.dumps(value, ensure_ascii=False)
        if row:
            row.value = encoded
        else:
            label = self._SETTINGS_DEFAULTS[key]['label']
            db.session.add(AftersaleSetting(key=key, value=encoded, label=label))
        db.session.commit()
        return True, None
