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
            self._auto_update_reason_keywords(seller_remark, reason_ids_used, buyer_remark)

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
            self._auto_update_reason_keywords(case.seller_remark, new_reason_ids, case.buyer_remark)

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
        def _strip_num(t):
            return re.sub(r'\d{4}[\.\-/]\d{1,2}[\.\-/]\d{1,2}', '', t).strip()  # 仅剥离日期

        for case in confirmed_cases:
            if not case.seller_remark:
                continue
            ratio = difflib.SequenceMatcher(
                None, _strip_num(text_lower), _strip_num(case.seller_remark.lower())
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

    def suggest_product(self, product_codes, purchase_date_str=None, seller_remark=None, buyer_remark=None):
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
