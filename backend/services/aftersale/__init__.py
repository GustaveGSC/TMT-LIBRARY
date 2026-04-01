from datetime import date
from result import Result
from database.repository.aftersale import AftersaleRepository
from database.models.aftersale import AftersaleReasonCategory, AftersaleReason, AftersaleProductAlias

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

    # ── 物料简称 ───────────────────────────────────────────────────────────────

    def get_aliases(self):
        aliases = _repo.get_all_aliases()
        return Result.ok(data=[a.to_dict() for a in aliases])

    def create_alias(self, data):
        alias = (data.get('alias') or '').strip()
        if not alias:
            return Result.fail('简称不能为空')
        codes = [c.strip() for c in (data.get('product_codes') or []) if str(c).strip()]
        if not codes:
            return Result.fail('至少填写一个产品代码')
        if AftersaleProductAlias.query.filter_by(alias=alias).first():
            return Result.fail('该简称已存在')
        obj = _repo.create_alias(alias=alias, product_codes=codes,
                                  sort_order=data.get('sort_order', 0))
        return Result.ok(data=obj.to_dict())

    def update_alias(self, alias_id, data):
        alias = (data.get('alias') or '').strip()
        if not alias:
            return Result.fail('简称不能为空')
        codes = [c.strip() for c in (data.get('product_codes') or []) if str(c).strip()]
        if not codes:
            return Result.fail('至少填写一个产品代码')
        # 名称唯一性校验（排除自身）
        existing = AftersaleProductAlias.query.filter_by(alias=alias).first()
        if existing and existing.id != alias_id:
            return Result.fail('该简称已存在')
        obj = _repo.update_alias(alias_id=alias_id, alias=alias, product_codes=codes,
                                  sort_order=data.get('sort_order'))
        if not obj:
            return Result.fail('简称不存在')
        return Result.ok(data=obj.to_dict())

    def delete_alias(self, alias_id):
        ok = _repo.delete_alias(alias_id)
        if not ok:
            return Result.fail('简称不存在')
        return Result.ok()

    def get_product_code_suggestions(self, q=None):
        items = _repo.get_product_code_suggestions(q)
        return Result.ok(data=items)

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
                  reason_id, channel_name, province, search):
        items, total = _repo.get_cases(
            page=page, page_size=page_size,
            status=status, date_start=date_start, date_end=date_end,
            reason_id=reason_id, channel_name=channel_name,
            province=province, search=search,
        )
        return Result.ok(data={
            'items':     [c.to_dict(include_reasons=True) for c in items],
            'total':     total,
            'page':      page,
            'page_size': page_size,
        })

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
            assigned_models=data.get('assigned_models'),
            shipping_materials=data.get('shipping_materials'),
            aftersale_materials=data.get('aftersale_materials'),
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

    # ── 自动匹配 ────────────────────────────────────────────────────────────

    def auto_match(self, text):
        if not text:
            return Result.ok(data=[])
        results = _repo.auto_match(text)
        return Result.ok(data=results)

    # ── 统计 & 图表 ─────────────────────────────────────────────────────────

    def get_stats(self):
        stats = _repo.get_stats()
        return Result.ok(data=stats)

    def get_chart_options(self):
        opts = _repo.get_chart_options()
        return Result.ok(data=opts)

    def get_chart_data(self, data):
        group_by = data.get('group_by', 'reason')
        if group_by not in ('reason', 'channel', 'province', 'month'):
            return Result.fail('group_by 参数无效')
        result = _repo.get_chart_data(
            group_by=group_by,
            date_start=data.get('date_start'),
            date_end=data.get('date_end'),
            channel_names=data.get('channel_names'),
            provinces=data.get('provinces'),
            category_id=data.get('category_id'),
        )
        return Result.ok(data=result)
