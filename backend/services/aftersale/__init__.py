from datetime import date
from result import Result
from database.repository.aftersale import AftersaleRepository
from database.models.aftersale import (
    AftersaleReasonCategory, AftersaleReason,
    AftersaleShippingAlias,
    AftersaleShippingAmbiguousTerm,
    AftersaleCase, AftersaleCaseReason,
)

_repo = AftersaleRepository()


class AftersaleService:

    # ── 一级分类 ───────────────────────────────────────────────────────────────

    def get_categories(self):
        cats = _repo.get_all_categories()
        return Result.ok(data=[c.to_dict() for c in cats])

    def create_category(self, data):
        name = (data.get('name') or '').strip()
        if not name:
            return Result.fail('分类名称不能为空')
        if AftersaleReasonCategory.query.filter_by(name=name).first():
            return Result.fail('该分类名称已存在')
        cat = _repo.create_category(name=name, sort_order=data.get('sort_order', 0))
        return Result.ok(data=cat.to_dict())

    def update_category(self, category_id, data):
        name = (data.get('name') or '').strip()
        if not name:
            return Result.fail('分类名称不能为空')
        # 名称唯一性校验（排除自身）
        existing = AftersaleReasonCategory.query.filter_by(name=name).first()
        if existing and existing.id != category_id:
            return Result.fail('该分类名称已存在')
        cat = _repo.update_category(
            category_id=category_id,
            name=name,
            sort_order=data.get('sort_order'),
        )
        if not cat:
            return Result.fail('分类不存在')
        return Result.ok(data=cat.to_dict())

    def delete_category(self, category_id):
        ok, count = _repo.delete_category(category_id)
        if not ok:
            if count > 0:
                return Result.fail(f'该分类下还有 {count} 个原因，请先移除或删除这些原因',
                                   data={'reason_count': count})
            return Result.fail('分类不存在')
        return Result.ok()


    # ── 二级原因 ───────────────────────────────────────────────────────────────

    def get_reasons(self):
        """按一级分类聚合返回，包含无分类的原因"""
        categories = _repo.get_all_categories()
        all_reasons = _repo.get_all_reasons()

        # 按 category_id 分组
        reason_map = {}
        for r in all_reasons:
            reason_map.setdefault(r.category_id, []).append(r.to_dict())

        # 按分类顺序构建结果
        result = []
        for cat in categories:
            result.append({
                'category_id':   cat.id,
                'category_name': cat.name,
                'sort_order':    cat.sort_order,
                'reasons':       reason_map.get(cat.id, []),
            })

        # 追加未归类原因
        uncategorized = reason_map.get(None, [])
        if uncategorized:
            result.append({
                'category_id':   None,
                'category_name': '未分类',
                'sort_order':    9999,
                'reasons':       uncategorized,
            })

        return Result.ok(data=result)

    def create_reason(self, data):
        name = (data.get('name') or '').strip()
        if not name:
            return Result.fail('原因名称不能为空')
        if AftersaleReason.query.filter_by(name=name).first():
            return Result.fail('该原因名称已存在')
        reason = _repo.create_reason(
            name=name,
            category_id=data.get('category_id'),
            keywords=data.get('keywords', ''),
            sort_order=data.get('sort_order', 0),
        )
        return Result.ok(data=reason.to_dict())

    def update_reason(self, reason_id, data):
        name = (data.get('name') or '').strip()
        if not name:
            return Result.fail('原因名称不能为空')
        reason = _repo.update_reason(
            reason_id=reason_id,
            name=name,
            category_id=data.get('category_id'),
            keywords=data.get('keywords', ''),
            sort_order=data.get('sort_order'),
        )
        if not reason:
            return Result.fail('原因不存在')
        return Result.ok(data=reason.to_dict())

    def delete_reason(self, reason_id):
        usage = _repo.get_reason_usage(reason_id)
        if usage > 0:
            return Result.fail(f'该原因已被 {usage} 条记录引用，无法删除', data={'usage_count': usage})
        ok, _ = _repo.delete_reason(reason_id)
        if not ok:
            return Result.fail('删除失败')
        return Result.ok()

    def get_reason_usage(self, reason_id):
        usage = _repo.get_reason_usage(reason_id)
        return Result.ok(data={'usage_count': usage})

    # ── 发货物料简称库 ─────────────────────────────────────────────────────────

    def get_shipping_aliases(self):
        return Result.ok(data=[a.to_dict() for a in _repo.get_all_shipping_aliases()])

    def create_shipping_alias(self, data):
        name = (data.get('name') or '').strip()
        if not name:
            return Result.fail('简称不能为空')
        if AftersaleShippingAlias.query.filter_by(name=name).first():
            return Result.fail('该简称已存在')
        keywords = [k.strip() for k in (data.get('keywords') or []) if str(k).strip()]
        obj = _repo.create_shipping_alias(name=name, keywords=keywords,
                                          sort_order=data.get('sort_order', 0))
        return Result.ok(data=obj.to_dict())

    def update_shipping_alias(self, alias_id, data):
        name = (data.get('name') or '').strip()
        if not name:
            return Result.fail('简称不能为空')
        existing = AftersaleShippingAlias.query.filter_by(name=name).first()
        if existing and existing.id != alias_id:
            return Result.fail('该简称已存在')
        keywords = [k.strip() for k in (data.get('keywords') or []) if str(k).strip()]
        obj = _repo.update_shipping_alias(alias_id, name=name, keywords=keywords,
                                          sort_order=data.get('sort_order'))
        if not obj:
            return Result.fail('简称不存在')
        return Result.ok(data=obj.to_dict())

    def delete_shipping_alias(self, alias_id):
        ok = _repo.delete_shipping_alias(alias_id)
        if not ok:
            return Result.fail('简称不存在')
        return Result.ok()

    # ── 待处理订单 ──────────────────────────────────────────────────────────

    def get_pending_orders(self, page, page_size, search, date_start, date_end):
        items, total = _repo.get_pending_orders(
            page=page, page_size=page_size,
            search=search, date_start=date_start, date_end=date_end,
        )
        return Result.ok(data={'items': items, 'total': total, 'page': page, 'page_size': page_size})

    def get_pending_count(self):
        count = _repo.get_pending_count()
        return Result.ok(data={'count': count})

    # ── 工单 ────────────────────────────────────────────────────────────────

    def get_cases(self, page, page_size, status, date_start, date_end,
                  reason_id, channel_name, province, city, district,
                  reason_category, reason_name, shipping_alias,
                  model_code=None, search=None, sort_by=None, sort_order='desc'):
        items, total = _repo.get_cases(
            page=page, page_size=page_size,
            status=status, date_start=date_start, date_end=date_end,
            reason_id=reason_id, channel_name=channel_name,
            province=province, city=city, district=district,
            reason_category=reason_category, reason_name=reason_name,
            shipping_alias=shipping_alias,
            model_code=model_code, search=search,
            sort_by=sort_by, sort_order=sort_order,
        )
        return Result.ok(data={
            'items':     [c.to_dict(include_reasons=False) for c in items],
            'total':     total,
            'page':      page,
            'page_size': page_size,
        })

    def get_cases_reasons(self, case_ids):
        """批量返回指定工单的 reasons，用于前端两阶段加载"""
        if not case_ids:
            return Result.ok(data={})
        from sqlalchemy.orm import selectinload
        cases = (
            AftersaleCase.query
            .filter(AftersaleCase.id.in_(case_ids))
            .options(
                selectinload(AftersaleCase.case_reasons)
                .selectinload(AftersaleCaseReason.reason)
                .selectinload(AftersaleReason.category_obj),
                selectinload(AftersaleCase.case_reasons)
                .selectinload(AftersaleCaseReason.product_model),
                selectinload(AftersaleCase.case_reasons)
                .selectinload(AftersaleCaseReason.shipping_alias),
            )
            .all()
        )
        return Result.ok(data={
            str(c.id): [r.to_dict() for r in c.case_reasons]
            for c in cases
        })

    def get_filter_options(self):
        return Result.ok(data=_repo.get_filter_options())

    def get_case(self, case_id):
        case = _repo.get_case_by_id(case_id)
        if not case:
            return Result.fail('工单不存在')
        return Result.ok(data=case.to_dict(include_reasons=True))

    def confirm_case(self, data):
        order_no = (data.get('ecommerce_order_no') or '').strip()
        if not order_no:
            return Result.fail('订单号不能为空')

        reasons_data = data.get('reasons', [])

        # 解析日期
        shipped_date = None
        if data.get('shipped_date'):
            try:
                shipped_date = date.fromisoformat(data['shipped_date'])
            except ValueError:
                pass

        case = _repo.confirm_case(
            order_no=order_no,
            products=data.get('products', []),
            seller_remark=data.get('seller_remark'),
            buyer_remark=data.get('buyer_remark'),
            shipped_date=shipped_date,
            operator=data.get('operator'),
            channel_name=data.get('channel_name'),
            province=data.get('province'),
            reasons_data=reasons_data,
            city=data.get('city'),
            district=data.get('district'),
        )
        return Result.ok(data=case.to_dict(include_reasons=True))

    def update_case(self, case_id, data):
        reasons_data = data.get('reasons', [])
        case = _repo.update_case(
            case_id=case_id,
            reasons_data=reasons_data,
            assigned_models=data.get('assigned_models'),
            shipping_materials=data.get('shipping_materials'),
            aftersale_materials=data.get('aftersale_materials'),
        )
        if not case:
            return Result.fail('工单不存在')
        return Result.ok(data=case.to_dict(include_reasons=True))

    def ignore_case(self, order_no):
        if not order_no:
            return Result.fail('订单号不能为空')
        case = _repo.ignore_case(order_no)
        return Result.ok(data=case.to_dict())

    # ── 产品型号推断 ────────────────────────────────────────────────────────

    def suggest_product(self, data):
        products      = data.get('products', [])
        product_codes = [p.get('code') for p in products if p.get('code')]
        purchase_date = data.get('purchase_date')
        seller_remark = data.get('seller_remark')
        buyer_remark  = data.get('buyer_remark')
        result = _repo.suggest_product(product_codes, purchase_date, seller_remark, buyer_remark, products)
        return Result.ok(data=result)

    # ── 自动匹配 ────────────────────────────────────────────────────────────

    def auto_match(self, text, buyer_remark=None):
        if not text:
            return Result.ok(data={'items': [], 'cleaned_text': ''})
        result = _repo.auto_match(text, buyer_remark=buyer_remark)
        return Result.ok(data=result)

    # ── 统计 & 图表 ─────────────────────────────────────────────────────────

    def get_stats(self):
        stats = _repo.get_stats()
        return Result.ok(data=stats)

    def get_cross_filter_options(self, data: dict):
        max_days = data.get('max_days_since_purchase')
        filters = {
            'date_start':               data.get('date_start'),
            'date_end':                 data.get('date_end'),
            'max_days_since_purchase':  int(max_days) if max_days is not None else None,
            'channel_names':            data.get('channel_names') or [],
            'provinces':                data.get('provinces') or [],
            'cities':                   data.get('cities') or [],
            'category_ids':             data.get('category_ids') or [],
            'series_ids':               data.get('series_ids') or [],
            'model_ids':                data.get('model_ids') or [],
            'reason_ids':               data.get('reason_ids') or [],
            'reason_category_ids':      data.get('reason_category_ids') or [],
            'shipping_alias_ids':       data.get('shipping_alias_ids') or [],
        }
        opts = _repo.get_cross_filter_options(filters)
        return Result.ok(data=opts)

    def get_chart_options(self):
        opts = _repo.get_chart_options()
        return Result.ok(data=opts)

    def get_chart_data(self, data):
        group_by = data.get('group_by', 'reason')
        if group_by not in ('product', 'reason', 'shipping_alias', 'channel', 'province'):
            return Result.fail('group_by 参数无效')
        max_days = data.get('max_days_since_purchase')
        filters = {
            'group_by':                group_by,
            'date_start':              data.get('date_start'),
            'date_end':                data.get('date_end'),
            'max_days_since_purchase': int(max_days) if max_days is not None else None,
            'channel_names':           data.get('channel_names') or [],
            'provinces':               data.get('provinces') or [],
            'cities':                  data.get('cities') or [],
            'category_ids':            data.get('category_ids') or [],
            'series_ids':              data.get('series_ids') or [],
            'model_ids':               data.get('model_ids') or [],
            'reason_ids':              data.get('reason_ids') or [],
            'reason_category_ids':     data.get('reason_category_ids') or [],
            'shipping_alias_ids':      data.get('shipping_alias_ids') or [],
        }
        result = _repo.get_chart_data(filters)
        return Result.ok(data=result)

    # ── 发货物料匹配过滤词 ────────────────────────────────────────────────────

    def get_ignore_terms(self):
        return Result.ok(data=[t.to_dict() for t in _repo.get_all_ignore_terms()])

    def create_ignore_term(self, data):
        term = (data.get('term') or '').strip()
        if not term:
            return Result.fail('过滤词不能为空')
        from database.models.aftersale import AftersaleShippingIgnoreTerm
        if AftersaleShippingIgnoreTerm.query.filter_by(term=term).first():
            return Result.fail('该过滤词已存在')
        obj = _repo.create_ignore_term(term=term)
        return Result.ok(data=obj.to_dict())

    def delete_ignore_term(self, term_id):
        ok = _repo.delete_ignore_term(term_id)
        if not ok:
            return Result.fail('过滤词不存在')
        return Result.ok()

    # ── 发货物料歧义词 ─────────────────────────────────────────────────────────

    def get_ambiguous_terms(self):
        return Result.ok(data=[t.to_dict() for t in _repo.get_all_ambiguous_terms()])

    def create_ambiguous_term(self, data):
        term = (data.get('term') or '').strip()
        if not term:
            return Result.fail('词不能为空')
        if AftersaleShippingAmbiguousTerm.query.filter_by(term=term).first():
            return Result.fail('该词已存在')
        obj = _repo.create_ambiguous_term(term=term)
        return Result.ok(data=obj.to_dict())

    def delete_ambiguous_term(self, term_id):
        ok = _repo.delete_ambiguous_term(term_id)
        if not ok:
            return Result.fail('词不存在')
        return Result.ok()

    # ── 词典自动建议 ────────────────────────────────────────────────────────────

    def get_dict_suggestions(self, type_filter=None, status='pending'):
        items = _repo.get_dict_suggestions(type_filter=type_filter, status=status)
        return Result.ok(data=[s.to_dict() for s in items])

    def accept_dict_suggestion(self, sug_id):
        sug, err = _repo.accept_dict_suggestion(sug_id)
        if err:
            return Result.fail(err)
        return Result.ok(data=sug.to_dict())

    def reject_dict_suggestion(self, sug_id):
        sug = _repo.reject_dict_suggestion(sug_id)
        if not sug:
            return Result.fail('建议不存在或已处理')
        return Result.ok(data=sug.to_dict())

    # ── 原因-简称亲和度 ──────────────────────────────────────────────────────────

    def get_alias_affinity(self, reason_id, alias_ids):
        affinity = _repo.get_alias_affinity(reason_id, alias_ids)
        return Result.ok(data=affinity)

    # ── 管理工具 ────────────────────────────────────────────────────────────────

    def migrate_alias_keywords(self):
        total, changed = _repo.migrate_alias_keywords()
        return Result.ok(data={'total': total, 'changed': changed},
                         message=f'迁移完成：共 {total} 条简称，更新 {changed} 条')

    # ── 售后原因关键词词典（标准档）────────────────────────────────────────────

    def get_reason_keyword_rules(self):
        return Result.ok(data=_repo.get_reason_keyword_rules())

    def update_reason_keyword_rules(self, data):
        stopwords = data.get('stopwords') or []
        if 'short_keep_terms' not in data:
            short_keep_terms = _repo.get_reason_keyword_rules().get('short_keep_terms', [])
        else:
            short_keep_terms = data.get('short_keep_terms')
            if not isinstance(short_keep_terms, list):
                return Result.fail('short_keep_terms 必须为数组')
        if not isinstance(stopwords, list):
            return Result.fail('词典字段必须为数组')
        _repo.replace_reason_keyword_rules(
            stopwords=stopwords,
            short_keep_terms=short_keep_terms,
        )
        return Result.ok(data=_repo.get_reason_keyword_rules())

    # ── 产品留言词典（材质/颜色/驱动/尺寸）────────────────────────────────────

    def get_product_remark_dict(self):
        return Result.ok(data=_repo.get_product_remark_dict())

    def put_product_remark_dict(self, items):
        if not isinstance(items, list):
            return Result.fail('items 必须为数组')
        valid_types = {'material', 'color', 'drive_type', 'size', 'series_alias'}
        for item in items:
            if item.get('type') not in valid_types:
                return Result.fail(f'无效的 type: {item.get("type")}')
            if not (item.get('value') or '').strip():
                return Result.fail('value 不能为空')
            if item.get('type') == 'size' and not (item.get('display') or '').strip():
                return Result.fail('size 类型必须填写 display（米制表达）')
            if item.get('type') == 'series_alias' and not (item.get('display') or '').strip():
                return Result.fail('series_alias 类型必须填写 display（官方系列名）')
        _repo.replace_product_remark_dict(items)
        return Result.ok(data=_repo.get_product_remark_dict())

    def cleanup_keyword_candidates(self, min_count=2, top_per_reason=200):
        result = _repo.cleanup_keyword_candidates(min_count=min_count, top_per_reason=top_per_reason)
        return Result.ok(data=result,
                         message=f'清理完成：噪声 {result["deleted_noise"]} 条，溢出 {result["deleted_overflow"]} 条，剩余 {result["remaining"]} 条')

    def get_keyword_candidate_stats(self):
        return Result.ok(data=_repo.get_keyword_candidate_stats())

    def get_series_monthly_by_model_id(self, model_id: int):
        data = _repo.get_series_monthly_by_model_id(model_id)
        return Result.ok(data=data)

    # ── 通用设置 ────────────────────────────────────────────────────────────

    def get_settings(self):
        return Result.ok(data=_repo.get_settings())

    def update_setting(self, data):
        key   = (data.get('key') or '').strip()
        value = data.get('value')
        if not key:
            return Result.fail('key 不能为空')
        if value is None:
            return Result.fail('value 不能为空')
        ok, err = _repo.update_setting(key, value)
        if not ok:
            return Result.fail(err)
        return Result.ok(message='保存成功')
