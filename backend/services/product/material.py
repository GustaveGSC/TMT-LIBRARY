from database.models.product.erp_code_rules import ErpCodeRule, TYPE_LABELS
from database.models.product.import_raw import ImportProductRaw
from database.models.product.material import MaterialDisableKeyword, ProductMaterial
from database.repository.product.material import MaterialRepository
from result import Result
from services.product.material_filter import expression_condition, literal_contains
from services.product.material_price import material_price_service


BOOLEAN_KEYS = ('is_finished', 'is_packaged', 'is_semi', 'is_material', 'is_useless')
CATEGORY_TYPES = ('finished', 'packaged', 'semi', 'material', 'useless')

# 物料类型的判定来源，按优先级从高到低：单独指定 > 编码前缀规则 > 分组默认类型
SOURCE_MANUAL = 'manual'
SOURCE_RULE = 'rule'
SOURCE_GROUP = 'group'


class MaterialService:
    _rule_cache = None
    _disable_keyword_cache = None
    _group_config_cache = None
    _override_cache = None
    # 全量物料类型判定结果 {'by_code': {code: (类型, 来源)}, 'groups': {...}}。
    # 物料清单按类型筛选、分组计数都读它，避免每次请求把 8000+ 行拉出来重新判定。
    # 规则/分组默认/单独指定/ERP 导入任一变化都要失效（各自的 invalidate_* 已串上）。
    _classification_cache = None

    @classmethod
    def invalidate_classification_cache(cls):
        cls._classification_cache = None

    @classmethod
    def invalidate_override_cache(cls):
        cls._override_cache = None
        cls._classification_cache = None

    def _overrides(self):
        if self._override_cache is None:
            self.__class__._override_cache = MaterialRepository.type_overrides()
        return self._override_cache

    @classmethod
    def invalidate_rule_cache(cls):
        cls._rule_cache = None
        cls._classification_cache = None

    @classmethod
    def invalidate_disable_keyword_cache(cls):
        cls._disable_keyword_cache = None

    @classmethod
    def invalidate_group_config_cache(cls):
        cls._group_config_cache = None
        cls._classification_cache = None

    def _group_configs(self):
        if self._group_config_cache is None:
            self.__class__._group_config_cache = MaterialRepository.group_configs()
        return self._group_config_cache

    def _disable_keywords(self):
        if self._disable_keyword_cache is None:
            self.__class__._disable_keyword_cache = [
                row.keyword for row in MaterialRepository.disable_keywords(enabled_only=True)
            ]
        return self._disable_keyword_cache

    def _rules(self):
        if self._rule_cache is not None:
            return self._rule_cache
        rows = ErpCodeRule.query.filter_by(is_disabled=False).all()
        grouped = {}
        for row in rows:
            grouped.setdefault(row.prefix, set()).add(row.type)
        self.__class__._rule_cache = sorted(
            grouped.items(), key=lambda item: len(item[0]), reverse=True
        )
        return self._rule_cache

    @staticmethod
    def _config_categories(config):
        return [name for name in CATEGORY_TYPES if config and getattr(config, f'is_{name}')]

    def _classify(self, code, group_code, rules, configs, overrides):
        """返回 (物料类型列表, 判定来源)；三级均未命中时来源为 None（未分类）。"""
        manual = overrides.get(code)
        if manual:
            return [t for t in CATEGORY_TYPES if t in manual], SOURCE_MANUAL
        # 所有命中的前缀类型都保留，因同一编码允许同时属于成品与产成品。
        result = set()
        for prefix, types in rules:
            if code.startswith(prefix):
                result.update(types)
        if result:
            return sorted(result), SOURCE_RULE
        group_types = self._config_categories(configs.get(group_code))
        return group_types, (SOURCE_GROUP if group_types else None)

    def _categories(self, code, group_code, rules, configs, overrides):
        return self._classify(code, group_code, rules, configs, overrides)[0]

    def _classification(self):
        if self._classification_cache is not None:
            return self._classification_cache
        configs, rules, overrides = self._group_configs(), self._rules(), self._overrides()
        by_code, groups = {}, {}
        for code, group_code, group_name in MaterialRepository.all_raw_identity_rows():
            cats, source = self._classify(code, group_code, rules, configs, overrides)
            by_code[code] = (cats, source)
            item = groups.setdefault(
                group_code, {'names': set(), 'count': 0, 'manual_count': 0, 'rule_count': 0},
            )
            item['names'].add(group_name)
            item['count'] += 1
            # 按实际生效的来源计数：单独指定的物料即使也命中前缀规则，只计入单独指定
            if source == SOURCE_MANUAL:
                item['manual_count'] += 1
            elif source == SOURCE_RULE:
                item['rule_count'] += 1
        self.__class__._classification_cache = {'by_code': by_code, 'groups': groups}
        return self._classification_cache

    def group_categories(self):
        aggregates = self._classification()['groups']
        configs = self._group_configs()
        data = []
        for group_code in sorted(aggregates):
            aggregate, config = aggregates[group_code], configs.get(group_code)
            item = {
                'group_code': group_code,
                'group_name': ' / '.join(sorted(aggregate['names'])),
                'material_count': aggregate['count'],
                'manual_count': aggregate['manual_count'],
                'rule_count': aggregate['rule_count'],
            }
            item.update({key: bool(config and getattr(config, key)) for key in BOOLEAN_KEYS})
            item['remark'] = config.remark if config else None
            data.append(item)
        return Result.ok(data=data)

    def save_group(self, group_code, body, updated_by=None):
        if not MaterialRepository.raw_query(group_code=group_code).first():
            return Result.fail('分组编码不存在')
        values = {key: bool(body.get(key, False)) for key in BOOLEAN_KEYS}
        values.update({'remark': (body.get('remark') or '').strip() or None, 'updated_by': updated_by})
        row = MaterialRepository.save_group(group_code, values)
        self.invalidate_group_config_cache()
        data = row.to_dict()
        data.update({key: bool(getattr(row, key)) for key in BOOLEAN_KEYS})
        return Result.ok(data=data)

    def list_items(self, page, page_size, **filters):
        text_columns = {
            'code': ImportProductRaw.code,
            'name': ImportProductRaw.name,
            'short_name': ProductMaterial.short_name,
        }
        text_conditions = []
        for key, column in text_columns.items():
            value = filters.get(key)
            if value is None:
                continue
            text_conditions.append(
                expression_condition(column, value)
                if filters.get('match_mode') == 'expr'
                else literal_contains(column, value)
            )
        query = MaterialRepository.raw_query(
            filters.get('keyword'), filters.get('group_code'), filters.get('is_disabled'),
            self._disable_keywords(), text_conditions=text_conditions,
            sort_by=filters.get('sort_by', 'code'), sort_dir=filters.get('sort_dir', 'asc'),
            price_state=filters.get('price_state'),
        )
        category = filters.get('category')
        unclassified = filters.get('unclassified')
        exclude_useless = filters.get('exclude_useless')
        by_code = {}
        if category or unclassified or exclude_useless:
            # 物料类型没法直接用 SQL 表达（依赖单独指定/前缀规则/分组默认三级判定），
            # 用缓存的判定结果算出编码白名单或黑名单交给 SQL，筛选、排序、分页仍在数据库完成。
            # 取较短的一边：「不显示无用物料」只需排除约 1000 个编码。
            by_code = self._classification()['by_code']

            def keep(cats):
                if category and category not in cats:
                    return False
                if unclassified and cats:
                    return False
                if exclude_useless and 'useless' in cats:
                    return False
                return True

            matched, dropped = [], []
            for code, (cats, _source) in by_code.items():
                (matched if keep(cats) else dropped).append(code)
            if len(matched) <= len(dropped):
                query = query.filter(ImportProductRaw.code.in_(matched))
            elif dropped:
                query = query.filter(ImportProductRaw.code.notin_(dropped))
        total = query.order_by(None).count()
        raw_rows = query.offset((page - 1) * page_size).limit(page_size).all()
        configs, rules, overrides = self._group_configs(), self._rules(), self._overrides()
        selected = [
            (raw, *(by_code.get(raw.code)
                    or self._classify(raw.code, raw.group_code, rules, configs, overrides)))
            for raw in raw_rows
        ]
        materials = MaterialRepository.materials_for_codes([raw.code for raw, _c, _s in selected])
        items = [
            self._serialize(raw, cats, materials.get(raw.code), source)
            for raw, cats, source in selected
        ]
        if filters.get('include_cost'):
            prices = material_price_service.latest_for_materials([
                item['code'] for item in items
            ])
            for item in items:
                price = prices.get(item['code'])
                item['latest_price'] = price['latest_price'] if price else None
                item['latest_price_source'] = (
                    price['latest_price_source'] if price else None
                )
        return Result.ok(data={
            'items': items,
            'total': total, 'page': page, 'page_size': page_size,
        })

    def detail(self, code, include_cost=False):
        raw = MaterialRepository.raw_by_code(code)
        if not raw:
            return Result.fail('物料不存在')
        cats, source = self._classify(
            code, raw.group_code, self._rules(), self._group_configs(), self._overrides(),
        )
        material = MaterialRepository.materials_for_codes([code]).get(code)
        data = self._serialize(raw, cats, material, source)
        data['images'] = [row.to_dict() for row in MaterialRepository.images_for_code(code)]
        # 卡片需要同时看到「如果不单独指定，规则会判成什么」，方便决定要不要指定
        if source == SOURCE_MANUAL:
            data['rule_categories'], data['rule_source'] = self._classify(
                code, raw.group_code, self._rules(), self._group_configs(), {},
            )
        else:
            data['rule_categories'], data['rule_source'] = cats, source
        if include_cost:
            data.update(material_price_service.detail_fields(data))
        return Result.ok(data=data)

    def disable_keywords(self):
        return Result.ok(data=[row.to_dict() for row in MaterialRepository.disable_keywords()])

    def create_disable_keyword(self, body):
        keyword = (body.get('keyword') or '').strip()
        if not keyword:
            return Result.fail('关键词不能为空')
        if len(keyword) > 64:
            return Result.fail('关键词不能超过 64 个字符')
        if MaterialDisableKeyword.query.filter_by(keyword=keyword).first():
            return Result.fail('关键词已存在')
        row = MaterialRepository.save_disable_keyword(None, {
            'keyword': keyword, 'is_disabled': bool(body.get('is_disabled', False)),
            'remark': (body.get('remark') or '').strip() or None,
        })
        self.invalidate_disable_keyword_cache()
        return Result.ok(data=row.to_dict())

    def update_disable_keyword(self, keyword_id, body):
        row = MaterialRepository.disable_keyword(keyword_id)
        if not row:
            return Result.fail('关键词规则不存在')
        values = {}
        if 'keyword' in body:
            keyword = (body.get('keyword') or '').strip()
            if not keyword or len(keyword) > 64:
                return Result.fail('关键词必须为 1 到 64 个字符')
            duplicate = MaterialDisableKeyword.query.filter(
                MaterialDisableKeyword.keyword == keyword,
                MaterialDisableKeyword.id != keyword_id,
            ).first()
            if duplicate:
                return Result.fail('关键词已存在')
            values['keyword'] = keyword
        if 'is_disabled' in body:
            values['is_disabled'] = bool(body['is_disabled'])
        if 'remark' in body:
            values['remark'] = (body.get('remark') or '').strip() or None
        row = MaterialRepository.save_disable_keyword(row, values)
        self.invalidate_disable_keyword_cache()
        return Result.ok(data=row.to_dict())

    def delete_disable_keyword(self, keyword_id):
        row = MaterialRepository.disable_keyword(keyword_id)
        if not row:
            return Result.fail('关键词规则不存在')
        MaterialRepository.delete_disable_keyword(row)
        self.invalidate_disable_keyword_cache()
        return Result.ok()

    def disable_preview(self):
        status_inactive, keyword_hit, union = MaterialRepository.disable_preview(
            self._disable_keywords()
        )
        return Result.ok(data={
            'status_inactive': int(status_inactive or 0),
            'keyword_hit': int(keyword_hit or 0),
            'union': int(union or 0),
        })

    def save_item(self, code, body):
        raw = MaterialRepository.raw_by_code(code)
        if not raw:
            return Result.fail('物料不存在')
        # 图片改走 material_image（add_image/replace_image/delete_image），这里不再接收封面字段
        allowed = ('short_name', 'category', 'spec', 'remark')
        values = {key: body[key] for key in allowed if key in body}
        for key in ('short_name', 'category', 'spec', 'remark'):
            if key in values:
                values[key] = (values[key] or '').strip() or None
        if 'type_override' in body:
            raw_types = body.get('type_override') or []
            if not isinstance(raw_types, list):
                return Result.fail('物料类型参数格式无效')
            invalid = [t for t in raw_types if t not in CATEGORY_TYPES]
            if invalid:
                return Result.fail('物料类型参数无效')
            # 空列表 = 取消单独指定，恢复按编码前缀规则/分组默认类型判定
            chosen = [t for t in CATEGORY_TYPES if t in raw_types]
            values['type_override'] = ','.join(chosen) or None
        MaterialRepository.save_material(code, values)
        if 'type_override' in values:
            self.invalidate_override_cache()
        return self.detail(code)

    def add_image(self, code, url, orig_url, created_by):
        if not MaterialRepository.raw_by_code(code):
            return Result.fail('物料不存在')
        MaterialRepository.add_image(code, url, orig_url, created_by)
        return self.images(code)

    def replace_image(self, code, image_id, url, orig_url):
        row = MaterialRepository.image(code, image_id)
        if not row:
            return Result.fail('图片不存在')
        MaterialRepository.replace_image(row, url, orig_url)
        return self.images(code)

    def delete_image(self, code, image_id):
        row = MaterialRepository.image(code, image_id)
        if not row:
            return Result.fail('图片不存在')
        MaterialRepository.delete_image(row)
        return self.images(code)

    @staticmethod
    def images(code):
        return Result.ok(data=[row.to_dict() for row in MaterialRepository.images_for_code(code)])

    def _serialize(self, raw, categories, material, source=None):
        manual = material.to_dict() if material else {
            'code': raw.code, 'short_name': None, 'category': None, 'spec': raw.spec,
            'remark': None, 'type_override': [],
        }
        if manual.get('spec') is None:
            manual['spec'] = raw.spec
        manual.update({
            'code': raw.code, 'name': raw.name, 'group_code': raw.group_code,
            'group_name': raw.group_name, 'erp_spec': raw.spec, 'categories': categories,
            'category_labels': [TYPE_LABELS[x] for x in categories],
            'category_source': source,
            'status': raw.status,
        })
        default_disabled = raw.status == '失效' or any(
            keyword in (raw.raw_name or raw.name or '').strip()
            for keyword in self._disable_keywords()
        )
        manual['is_disabled'] = default_disabled
        return manual


material_service = MaterialService()
