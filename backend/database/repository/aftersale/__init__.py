import re
import difflib
from datetime import datetime, timezone, timedelta
from database.base import db
from database.models.aftersale import (
    AftersaleReasonCategory, AftersaleReason, AftersaleKeywordCandidate,
    AftersaleCase, AftersaleCaseReason,
    AftersaleShippingAlias, AftersaleReturnAlias,
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
        'purchase_date':       AftersaleCase.purchase_date,
        'days_since_purchase': AftersaleCase.days_since_purchase,
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
                   .filter(AftersaleCaseReason.shipping_material_alias == shipping_alias)
                   .subquery())
            q = q.filter(AftersaleCase.id.in_(sub))
        if return_alias:
            sub = (db.session.query(AftersaleCaseReason.case_id)
                   .filter(AftersaleCaseReason.aftersale_material_alias == return_alias)
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
        sort_col = self._SORT_FIELDS.get(sort_by, AftersaleCase.shipped_date)
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

        ship_aliases   = q("SELECT DISTINCT shipping_material_alias  FROM aftersale_case_reason WHERE shipping_material_alias  IS NOT NULL AND shipping_material_alias  != '' ORDER BY shipping_material_alias")
        return_aliases = q("SELECT DISTINCT aftersale_material_alias FROM aftersale_case_reason WHERE aftersale_material_alias IS NOT NULL AND aftersale_material_alias != '' ORDER BY aftersale_material_alias")

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
                     assigned_models=None, shipping_materials=None, aftersale_materials=None,
                     city=None, district=None, purchase_date=None):
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
        case.purchase_date = purchase_date

        # 自动计算售后间隔天数（售后日期 - 购买日期），两者均有才计算
        if shipped_date and purchase_date:
            case.days_since_purchase = (shipped_date - purchase_date).days
        else:
            case.days_since_purchase = None

        case.assigned_models     = assigned_models    or []
        case.shipping_materials  = shipping_materials  or []
        case.aftersale_materials = aftersale_materials or []
        case.status              = 'confirmed'
        case.processed_at        = now_cst()

        # 清除旧 reasons，重新写入
        AftersaleCaseReason.query.filter_by(case_id=case.id).delete()
        reason_ids_used = set()
        for rd in reasons_data:
            cr = AftersaleCaseReason(
                case_id                  = case.id,
                reason_id                = rd.get('reason_id'),
                reason_category_id       = rd.get('reason_category_id') if not rd.get('reason_id') else None,
                custom_reason            = rd.get('custom_reason'),
                involved_products        = rd.get('involved_products'),
                notes                    = rd.get('notes'),
                model_id                 = rd.get('model_id'),
                shipping_material_alias  = rd.get('shipping_material_alias') or None,
                aftersale_material_alias = rd.get('aftersale_material_alias') or None,
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
            self._auto_update_reason_keywords(seller_remark, reason_ids_used)

        # 自动将简称写入/合并到简称库
        product_codes = [p.get('code') for p in (products or []) if p.get('code')]
        for rd in reasons_data:
            ship_alias = (rd.get('shipping_material_alias') or '').strip()
            ret_alias  = (rd.get('aftersale_material_alias') or '').strip()
            if ship_alias:
                self.upsert_shipping_alias(ship_alias, product_codes)
            if ret_alias:
                self.upsert_return_alias(ret_alias, seller_remark)

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
                case_id                  = case_id,
                reason_id                = rd.get('reason_id'),
                reason_category_id       = rd.get('reason_category_id') if not rd.get('reason_id') else None,
                custom_reason            = rd.get('custom_reason'),
                involved_products        = rd.get('involved_products'),
                notes                    = rd.get('notes'),
                model_id                 = rd.get('model_id'),
                shipping_material_alias  = rd.get('shipping_material_alias') or None,
                aftersale_material_alias = rd.get('aftersale_material_alias') or None,
            )
            db.session.add(cr)
            if rd.get('reason_id'):
                new_reason_ids.add(rd['reason_id'])

        if new_reason_ids:
            AftersaleReason.query.filter(
                AftersaleReason.id.in_(new_reason_ids)
            ).update({'use_count': AftersaleReason.use_count + 1},
                     synchronize_session='fetch')
            self._auto_update_reason_keywords(case.seller_remark, new_reason_ids)

        # 仅当参数非 None 时覆盖（None 表示调用方未传，保留原值）
        if assigned_models is not None:
            case.assigned_models = assigned_models
        if shipping_materials is not None:
            case.shipping_materials = shipping_materials
        if aftersale_materials is not None:
            case.aftersale_materials = aftersale_materials
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

    @staticmethod
    def _extract_keywords_from_text(text):
        """
        从备注文本中提取候选关键词。
        按标点/空白切段，过滤纯数字和过短片段（<2字）。
        段长 ≤ 10字：直接作为一个关键词。
        段长 > 10字：取所有4字 n-gram，避免单段过长无法命中。
        """
        if not text:
            return []
        segments = re.split(r'[，,。.！!？?、\s；;：:【】\[\]()（）""\'\'/\\|]+', text)
        seen = set()
        result = []
        for seg in segments:
            seg = seg.strip()
            if len(seg) < 2 or seg.isdigit():
                continue
            if len(seg) <= 10:
                if seg not in seen:
                    seen.add(seg)
                    result.append(seg)
            else:
                for i in range(len(seg) - 3):
                    gram = seg[i:i + 4]
                    if gram.isdigit() or gram in seen:
                        continue
                    seen.add(gram)
                    result.append(gram)
        return result

    # 关键词晋升阈值：候选词出现 N 次后才写入 keywords
    _KW_PROMOTE_THRESHOLD = 3
    # 每个原因最多保留关键词数
    _KW_MAX_TOTAL = 30

    def _auto_update_reason_keywords(self, seller_remark, reason_ids):
        """
        提交工单时更新候选词频池，达到阈值的候选词晋升到原因 keywords。
        流程：
          1. 提取 seller_remark 的 n-gram 候选词
          2. 对每个 reason_id，upsert aftersale_keyword_candidate（count+1）
          3. count >= 阈值 且 尚未在 keywords 中 → 晋升，并从候选池删除
        """
        if not seller_remark or not reason_ids:
            return
        new_kws = self._extract_keywords_from_text(seller_remark)
        if not new_kws:
            return

        reasons = {r.id: r for r in AftersaleReason.query.filter(
            AftersaleReason.id.in_(reason_ids)
        ).all()}

        for rid, reason in reasons.items():
            existing_kws = set(k.strip() for k in (reason.keywords or '').split(',') if k.strip())
            to_promote = []

            for kw in new_kws:
                if kw in existing_kws:
                    continue  # 已晋升，跳过

                candidate = AftersaleKeywordCandidate.query.filter_by(
                    reason_id=rid, keyword=kw
                ).first()

                if candidate:
                    candidate.count += 1
                else:
                    candidate = AftersaleKeywordCandidate(reason_id=rid, keyword=kw, count=1)
                    db.session.add(candidate)
                    db.session.flush()

                if candidate.count >= self._KW_PROMOTE_THRESHOLD:
                    to_promote.append(kw)
                    db.session.delete(candidate)

            if to_promote:
                kw_list = [k for k in (reason.keywords or '').split(',') if k.strip()]
                for kw in to_promote:
                    if kw not in kw_list and len(kw_list) < self._KW_MAX_TOTAL:
                        kw_list.append(kw)
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

        text_lower = text.lower()
        scores = {}   # reason_id → {score, name, category_name, source}

        # 阶段1：关键词库匹配
        reasons = AftersaleReason.query.all()
        for r in reasons:
            if not r.keywords:
                continue
            kws = [k.strip() for k in r.keywords.split(',') if k.strip()]
            if not kws:
                continue
            matched = sum(1 for k in kws if k.lower() in text_lower)
            if matched > 0:
                conf = matched / len(kws)
                if r.id not in scores or scores[r.id]['confidence'] < conf:
                    scores[r.id] = {
                        'reason_id':     r.id,
                        'name':          r.name,
                        'category_name': r.category_obj.name if r.category_obj else None,
                        'confidence':    conf,
                        'source':        'keyword',
                    }

        # 阶段2：历史案例相似度（取最近 500 条已确认工单）
        confirmed_cases = (
            AftersaleCase.query
            .filter_by(status='confirmed')
            .filter(AftersaleCase.seller_remark.isnot(None))
            .order_by(AftersaleCase.processed_at.desc())
            .limit(500)
            .all()
        )
        for case in confirmed_cases:
            if not case.seller_remark:
                continue
            ratio = difflib.SequenceMatcher(
                None, text_lower, case.seller_remark.lower()
            ).ratio()
            if ratio < 0.3:
                continue
            for cr in case.case_reasons:
                if not cr.reason_id:
                    continue
                existing = scores.get(cr.reason_id)
                if not existing or existing['confidence'] < ratio:
                    scores[cr.reason_id] = {
                        'reason_id':     cr.reason_id,
                        'name':          cr.reason.name if cr.reason else '',
                        'category_name': cr.reason.category_obj.name if cr.reason and cr.reason.category_obj else None,
                        'confidence':    round(ratio, 3),
                        'source':        'history',
                    }

        results = sorted(scores.values(), key=lambda x: x['confidence'], reverse=True)
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

    def get_chart_data(self, group_by, date_start=None, date_end=None,
                       channel_names=None, provinces=None, category_id=None):
        """
        图表聚合数据。
        group_by: 'reason' | 'channel' | 'province' | 'month'
        """
        from sqlalchemy import func

        q = (
            db.session.query(AftersaleCase, AftersaleCaseReason, AftersaleReason)
            .join(AftersaleCaseReason, AftersaleCaseReason.case_id == AftersaleCase.id)
            .outerjoin(AftersaleReason, AftersaleReason.id == AftersaleCaseReason.reason_id)
            .filter(AftersaleCase.status == 'confirmed')
        )

        if date_start:
            q = q.filter(AftersaleCase.shipped_date >= date_start)
        if date_end:
            q = q.filter(AftersaleCase.shipped_date <= date_end)
        if channel_names:
            q = q.filter(AftersaleCase.channel_name.in_(channel_names))
        if provinces:
            q = q.filter(AftersaleCase.province.in_(provinces))
        if category_id:
            q = q.filter(AftersaleReason.category_id == category_id)

        rows = q.all()

        # 按 group_by 聚合
        agg = {}
        for case, cr, reason in rows:
            if group_by == 'reason':
                key = reason.name if reason else (cr.custom_reason or '未分类')
            elif group_by == 'channel':
                key = case.channel_name or '未知渠道'
            elif group_by == 'province':
                key = case.province or '未知省份'
            elif group_by == 'month':
                key = case.shipped_date.strftime('%Y-%m') if case.shipped_date else '未知'
            else:
                key = '未知'
            agg[key] = agg.get(key, 0) + 1

        items = [{'name': k, 'value': v} for k, v in
                 sorted(agg.items(), key=lambda x: x[1], reverse=True)]
        return {
            'summary': {'total': sum(v['value'] for v in items)},
            'items':   items,
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

    def suggest_product(self, product_codes, purchase_date_str=None, seller_remark=None):
        """
        根据发货产品代码列表 + 购买日期，综合两个来源推断最可能的产品型号：

        来源 A（基础，权重 +1/产品）：
          product_finished.code → product_model → series → category
          若购买日期已知且 listed_yymm 晚于购买月份，该型号标记为日期不符

        来源 B（历史，权重 +2/工单）：
          已确认的 aftersale_case（含相同产品代码）的 case_reason.model_id
          历史记录权重更高，反映实际处理经验

        最终排序：日期符合 > 综合得分
        返回 {category_id, series_id, model_id, ...} 或 None
        """
        if not product_codes:
            return None

        from collections import defaultdict
        from sqlalchemy import or_
        from database.models.product.category import ProductCategory, ProductSeries, ProductModel
        from database.models.product.finished import ProductFinished

        # purchase_date → YYYY-MM，与 listed_yymm 做字符串比较
        purchase_ym = None
        if purchase_date_str:
            try:
                from datetime import date as _date
                pd = _date.fromisoformat(purchase_date_str)
                purchase_ym = f"{pd.year}-{pd.month:02d}"
            except (ValueError, AttributeError):
                pass

        # 每个 model_id 的综合信息
        # {model_id: {'score': int, 'date_ok': bool, 'meta': row}}
        model_score = defaultdict(lambda: {'score': 0, 'date_ok': True, 'meta': None})

        # ── 来源 A：product_finished ──────────────────────────────────────
        finished_rows = (
            db.session.query(
                ProductFinished.listed_yymm,
                ProductFinished.delisted_yymm,
                ProductModel.id.label('model_id'),
                ProductModel.name.label('model_name'),
                ProductSeries.id.label('series_id'),
                ProductSeries.name.label('series_name'),
                ProductCategory.id.label('category_id'),
                ProductCategory.name.label('category_name'),
            )
            .join(ProductModel,    ProductModel.id    == ProductFinished.model_id)
            .join(ProductSeries,   ProductSeries.id   == ProductModel.series_id)
            .join(ProductCategory, ProductCategory.id == ProductSeries.category_id)
            .filter(ProductFinished.code.in_(product_codes))
            .filter(ProductFinished.status != 'ignored')
            .filter(ProductFinished.model_id.isnot(None))
            .all()
        )
        for row in finished_rows:
            mid = row.model_id
            model_score[mid]['score'] += 1
            model_score[mid]['meta']   = row
            if purchase_ym:
                # 购买日期早于上架日期 → 该型号尚未发布，不符合
                if row.listed_yymm and row.listed_yymm > purchase_ym:
                    model_score[mid]['date_ok'] = False
                # 购买日期晚于下架日期 → 该型号已停售，不符合
                # 无下架时间：视为当月退市（在售上限 = 当前年月）
                effective_delisted = row.delisted_yymm or now_cst().strftime('%Y-%m')
                if effective_delisted < purchase_ym:
                    model_score[mid]['date_ok'] = False

        # ── 来源 B：历史已确认工单的 case_reason.model_id ────────────────
        # 用 JSON_SEARCH 匹配 aftersale_case.products[*].code 包含任意 product_code
        code_filters = [
            db.func.json_search(
                AftersaleCase.products, 'one', code, None, '$[*].code'
            ).isnot(None)
            for code in product_codes
        ]
        history_rows = (
            db.session.query(
                AftersaleCaseReason.model_id.label('model_id'),
                ProductModel.name.label('model_name'),
                ProductSeries.id.label('series_id'),
                ProductSeries.name.label('series_name'),
                ProductCategory.id.label('category_id'),
                ProductCategory.name.label('category_name'),
            )
            .join(AftersaleCase,   AftersaleCase.id   == AftersaleCaseReason.case_id)
            .join(ProductModel,    ProductModel.id    == AftersaleCaseReason.model_id)
            .join(ProductSeries,   ProductSeries.id   == ProductModel.series_id)
            .join(ProductCategory, ProductCategory.id == ProductSeries.category_id)
            .filter(AftersaleCase.status == 'confirmed')
            .filter(AftersaleCaseReason.model_id.isnot(None))
            .filter(or_(*code_filters))
            .all()
        )
        for row in history_rows:
            mid = row.model_id
            model_score[mid]['score'] += 2   # 历史记录权重更高
            if not model_score[mid]['meta']:
                model_score[mid]['meta'] = row

        # ── 历史简称 & 原因统计（共用 code_filters）────────────────────
        # 三个字段各自按频次取最高，来源均为相同产品代码的历史确认工单

        def _top_alias(field):
            """按频次取 AftersaleCaseReason 某简称字段的最高值"""
            cnt = {}
            rows = (
                db.session.query(field)
                .join(AftersaleCase, AftersaleCase.id == AftersaleCaseReason.case_id)
                .filter(AftersaleCase.status == 'confirmed')
                .filter(field.isnot(None))
                .filter(field != '')
                .filter(or_(*code_filters))
                .all()
            )
            for (val,) in rows:
                v = (val or '').strip()
                if v:
                    cnt[v] = cnt.get(v, 0) + 1
            return max(cnt, key=cnt.get) if cnt else None

        # ── 发货物料简称：绑定库匹配优先，历史频次兜底 ──────────────────────
        binding_shipping, _ = self.match_shipping_alias(product_codes)
        history_shipping     = _top_alias(AftersaleCaseReason.shipping_material_alias)
        suggested_shipping_alias = binding_shipping or history_shipping

        # ── 售后物料简称：绑定库文本匹配优先，历史频次兜底 ──────────────────
        binding_return, _ = self.match_return_alias(seller_remark)
        history_return     = _top_alias(AftersaleCaseReason.aftersale_material_alias)
        suggested_aftersale_alias = binding_return or history_return

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
            'suggested_shipping_alias':  suggested_shipping_alias,
            'suggested_aftersale_alias': suggested_aftersale_alias,
            'suggested_reason_id':          suggested_reason_id,
            'suggested_reason_category_id': suggested_reason_category_id,
        }

        if not model_score:
            # 没有找到型号匹配，但仍可返回辅助建议
            has_any = any(v is not None for v in suggestions.values())
            return suggestions if has_any else None

        # 排序：日期符合 > 综合得分
        ranked = sorted(
            model_score.values(),
            key=lambda x: (x['date_ok'], x['score']),
            reverse=True,
        )
        best   = ranked[0]
        meta   = best['meta']
        return {
            'category_id':   meta.category_id,
            'series_id':     meta.series_id,
            'model_id':      meta.model_id,
            'category_name': meta.category_name,
            'series_name':   meta.series_name,
            'model_name':    meta.model_name,
            'date_ok':       best['date_ok'],   # 购买日期是否在生命周期内
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

    def create_shipping_alias(self, name, product_codes=None, sort_order=0):
        obj = AftersaleShippingAlias(name=name, product_codes=product_codes or [], sort_order=sort_order)
        db.session.add(obj)
        db.session.commit()
        return obj

    def update_shipping_alias(self, alias_id, name, product_codes=None, sort_order=None):
        obj = AftersaleShippingAlias.query.get(alias_id)
        if not obj:
            return None
        obj.name = name
        if product_codes is not None:
            obj.product_codes = product_codes
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

    # ── 简称库自动入库（提交工单时调用） ───────────────────────────────────────

    def upsert_shipping_alias(self, name, product_codes):
        """
        提交工单时：若发货物料简称不在库中则自动创建，
        若已存在则将当前产品代码合并到绑定列表。
        不触发独立 commit（由 confirm_case 统一提交）。
        """
        if not name:
            return
        name = name.strip()
        if not name:
            return
        obj = AftersaleShippingAlias.query.filter_by(name=name).first()
        new_codes = [c for c in (product_codes or []) if c]
        if obj is None:
            obj = AftersaleShippingAlias(name=name, product_codes=new_codes or None)
            db.session.add(obj)
        else:
            # 合并产品代码，去重
            existing = set(obj.product_codes or [])
            merged   = list(existing | set(new_codes))
            obj.product_codes = merged if merged else obj.product_codes

    def upsert_return_alias(self, name, seller_remark):
        """
        提交工单时：若售后物料简称不在库中则自动创建，
        若已存在则将商家备注片段添加到关键词列表（去重，最多保留 50 条）。
        不触发独立 commit（由 confirm_case 统一提交）。
        """
        if not name:
            return
        name = name.strip()
        if not name:
            return
        remark = (seller_remark or '').strip()
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

    def match_shipping_alias(self, product_codes):
        """
        根据产品代码列表匹配最佳发货物料简称。
        返回 (alias_name, score) 或 (None, 0)。
        以代码覆盖率（匹配代码数 / 简称绑定代码总数）为得分。
        """
        if not product_codes:
            return None, 0.0
        code_set = set(product_codes)
        best_name, best_score = None, 0.0
        for obj in AftersaleShippingAlias.query.filter(
            AftersaleShippingAlias.product_codes.isnot(None)
        ).all():
            bound = set(obj.product_codes or [])
            if not bound:
                continue
            overlap = len(code_set & bound)
            if overlap == 0:
                continue
            score = overlap / len(bound)
            if score > best_score:
                best_score = score
                best_name  = obj.name
        return best_name, best_score

    def match_return_alias(self, seller_remark):
        """
        根据商家备注文本匹配最佳售后物料简称。
        遍历每个简称的 keywords 列表，取最高文本相似分。
        返回 (alias_name, score) 或 (None, 0)。
        """
        if not seller_remark:
            return None, 0.0
        best_name, best_score = None, 0.0
        for obj in AftersaleReturnAlias.query.filter(
            AftersaleReturnAlias.keywords.isnot(None)
        ).all():
            for kw in (obj.keywords or []):
                score = self._text_sim(seller_remark, kw)
                if score > best_score:
                    best_score = score
                    best_name  = obj.name
        # 阈值 0.3：相似度不够不推荐
        return (best_name, best_score) if best_score >= 0.3 else (None, 0.0)
