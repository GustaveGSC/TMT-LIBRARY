import difflib
from datetime import datetime, timezone, timedelta
from database.base import db
from database.models.aftersale import (
    AftersaleReasonCategory, AftersaleReason,
    AftersaleCase, AftersaleCaseReason,
    AftersaleProductAlias,
)
from database.models.shipping import ShippingRecord, ShippingOperatorType

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

    # ── 物料简称 ───────────────────────────────────────────────────────────────

    def get_all_aliases(self):
        """按 sort_order 返回所有物料简称"""
        return (
            AftersaleProductAlias.query
            .order_by(AftersaleProductAlias.sort_order.asc(),
                      AftersaleProductAlias.id.asc())
            .all()
        )

    def create_alias(self, alias, product_codes, sort_order=0):
        obj = AftersaleProductAlias(
            alias=alias,
            product_codes=product_codes,
            sort_order=sort_order,
        )
        db.session.add(obj)
        db.session.commit()
        return obj

    def update_alias(self, alias_id, alias, product_codes, sort_order=None):
        obj = AftersaleProductAlias.query.get(alias_id)
        if not obj:
            return None
        obj.alias         = alias
        obj.product_codes = product_codes
        if sort_order is not None:
            obj.sort_order = sort_order
        db.session.commit()
        return obj

    def delete_alias(self, alias_id):
        obj = AftersaleProductAlias.query.get(alias_id)
        if not obj:
            return False
        db.session.delete(obj)
        db.session.commit()
        return True

    def get_product_code_suggestions(self, q=None):
        """返回 shipping_record 中去重的产品代码（可按前缀筛选），供前端自动补全"""
        from sqlalchemy import distinct
        query = (
            db.session.query(
                distinct(ShippingRecord.product_code),
                ShippingRecord.product_name,
            )
            .filter(ShippingRecord.product_code.isnot(None))
        )
        if q:
            query = query.filter(ShippingRecord.product_code.like(f'%{q}%'))
        rows = query.order_by(ShippingRecord.product_code).limit(50).all()
        return [{'code': r[0], 'name': r[1]} for r in rows]

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
        )

        # 已创建工单的订单号子查询
        existing_orders = (
            db.session.query(AftersaleCase.ecommerce_order_no)
            .subquery()
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

    def get_cases(self, page=1, page_size=50,
                  status=None, date_start=None, date_end=None,
                  reason_id=None, channel_name=None, province=None, search=None):
        """分页查询工单，支持多维筛选"""
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
        if search:
            q = q.filter(AftersaleCase.ecommerce_order_no.like(f'%{search}%'))
        if reason_id:
            sub = db.session.query(AftersaleCaseReason.case_id).filter_by(reason_id=reason_id).subquery()
            q = q.filter(AftersaleCase.id.in_(sub))

        total = q.count()
        items = (
            q.order_by(AftersaleCase.shipped_date.desc(), AftersaleCase.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return items, total

    def confirm_case(self, order_no, products, seller_remark, buyer_remark,
                     shipped_date, operator, channel_name, province, reasons_data,
                     assigned_models=None, shipping_materials=None, aftersale_materials=None):
        """
        创建或更新工单（status→confirmed），批量写入 reasons。
        reasons_data: [{reason_id?, custom_reason?, involved_products?, notes?}]
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
                case_id           = case.id,
                reason_id         = rd.get('reason_id'),
                custom_reason     = rd.get('custom_reason'),
                involved_products = rd.get('involved_products'),
                notes             = rd.get('notes'),
            )
            db.session.add(cr)
            if rd.get('reason_id'):
                reason_ids_used.add(rd['reason_id'])

        # 递增 use_count
        if reason_ids_used:
            AftersaleReason.query.filter(
                AftersaleReason.id.in_(reason_ids_used)
            ).update({'use_count': AftersaleReason.use_count + 1},
                     synchronize_session='fetch')

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
                case_id           = case_id,
                reason_id         = rd.get('reason_id'),
                custom_reason     = rd.get('custom_reason'),
                involved_products = rd.get('involved_products'),
                notes             = rd.get('notes'),
            )
            db.session.add(cr)
            if rd.get('reason_id'):
                new_reason_ids.add(rd['reason_id'])

        if new_reason_ids:
            AftersaleReason.query.filter(
                AftersaleReason.id.in_(new_reason_ids)
            ).update({'use_count': AftersaleReason.use_count + 1},
                     synchronize_session='fetch')

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
