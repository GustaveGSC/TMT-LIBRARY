from database.models.product.erp_code_rules import ErpCodeRule, TYPE_LABELS
from database.models.product.import_raw import ImportProductRaw
from database.models.product.material import MaterialDisableKeyword, ProductMaterial
from database.repository.product.material import MaterialRepository
from result import Result
from services.product.material_filter import expression_condition, literal_contains


BOOLEAN_KEYS = ('is_finished', 'is_packaged', 'is_semi', 'is_material', 'is_useless')
CATEGORY_TYPES = ('finished', 'packaged', 'semi', 'material', 'useless')


class MaterialService:
    _rule_cache = None
    _disable_keyword_cache = None
    _group_config_cache = None

    @classmethod
    def invalidate_rule_cache(cls):
        cls._rule_cache = None

    @classmethod
    def invalidate_disable_keyword_cache(cls):
        cls._disable_keyword_cache = None

    @classmethod
    def invalidate_group_config_cache(cls):
        cls._group_config_cache = None

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

    def _categories(self, code, group_code, rules, configs):
        # 所有命中的前缀类型都保留，因同一编码允许同时属于成品与产成品。
        result = set()
        for prefix, types in rules:
            if code.startswith(prefix):
                result.update(types)
        return sorted(result) if result else self._config_categories(configs.get(group_code))

    def group_categories(self):
        raw_rows = MaterialRepository.all_raw_identity_rows()
        configs, rules = self._group_configs(), self._rules()
        aggregates = {}
        for code, group_code, group_name in raw_rows:
            item = aggregates.setdefault(group_code, {'names': set(), 'count': 0, 'override_count': 0})
            item['names'].add(group_name)
            item['count'] += 1
            if any(code.startswith(prefix) for prefix, _types in rules):
                item['override_count'] += 1
        data = []
        for group_code in sorted(aggregates):
            aggregate, config = aggregates[group_code], configs.get(group_code)
            item = {
                'group_code': group_code,
                'group_name': ' / '.join(sorted(aggregate['names'])),
                'material_count': aggregate['count'],
                'override_count': aggregate['override_count'],
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
        )
        configs, rules = self._group_configs(), self._rules()
        category = filters.get('category')
        if not category and not filters.get('unclassified'):
            total = query.order_by(None).count()
            raw_rows = query.offset((page - 1) * page_size).limit(page_size).all()
            selected = [
                (raw, self._categories(raw.code, raw.group_code, rules, configs))
                for raw in raw_rows
            ]
        else:
            identities = query.with_entities(
                ImportProductRaw.code, ImportProductRaw.group_code,
                ImportProductRaw.name, ProductMaterial.short_name,
            ).all()
            classified = [
                {
                    'code': code, 'group_code': group_code, 'name': name,
                    'short_name': short_name,
                    'categories': self._categories(code, group_code, rules, configs),
                }
                for code, group_code, name, short_name in identities
            ]
            if category:
                classified = [item for item in classified if category in item['categories']]
            else:
                classified = [item for item in classified if not item['categories']]
            sort_by = filters.get('sort_by', 'code')
            non_null = [item for item in classified if item[sort_by] is not None]
            nulls = [item for item in classified if item[sort_by] is None]
            non_null.sort(
                key=lambda item: item[sort_by],
                reverse=filters.get('sort_dir') == 'desc',
            )
            classified = non_null + nulls
            total = len(classified)
            page_rows = classified[(page - 1) * page_size:page * page_size]
            categories_by_code = {
                item['code']: item['categories'] for item in page_rows
            }
            raw_rows = MaterialRepository.raw_for_codes([item['code'] for item in page_rows])
            selected = [(raw, categories_by_code[raw.code]) for raw in raw_rows]
        materials = MaterialRepository.materials_for_codes([raw.code for raw, _ in selected])
        return Result.ok(data={
            'items': [self._serialize(raw, cats, materials.get(raw.code)) for raw, cats in selected],
            'total': total, 'page': page, 'page_size': page_size,
        })

    def detail(self, code):
        raw = MaterialRepository.raw_by_code(code)
        if not raw:
            return Result.fail('物料不存在')
        cats = self._categories(code, raw.group_code, self._rules(), self._group_configs())
        material = MaterialRepository.materials_for_codes([code]).get(code)
        return Result.ok(data=self._serialize(raw, cats, material))

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
        allowed = ('short_name', 'category', 'spec', 'remark', 'is_disabled',
                   'cover_image', 'cover_image_original', 'img_updated_at')
        values = {key: body[key] for key in allowed if key in body}
        for key in ('short_name', 'category', 'spec', 'remark'):
            if key in values:
                values[key] = (values[key] or '').strip() or None
        if 'is_disabled' in values:
            values['is_disabled'] = (
                None if values['is_disabled'] is None else bool(values['is_disabled'])
            )
        MaterialRepository.save_material(code, values)
        return self.detail(code)

    def _serialize(self, raw, categories, material):
        manual = material.to_dict() if material else {
            'code': raw.code, 'short_name': None, 'category': None, 'spec': raw.spec,
            'cover_image': None, 'cover_image_original': None, 'img_updated_at': None,
            'remark': None, 'is_disabled_override': None,
        }
        if manual.get('spec') is None:
            manual['spec'] = raw.spec
        manual.update({
            'code': raw.code, 'name': raw.name, 'group_code': raw.group_code,
            'group_name': raw.group_name, 'erp_spec': raw.spec, 'categories': categories,
            'category_labels': [TYPE_LABELS[x] for x in categories],
            'status': raw.status,
        })
        default_disabled = raw.status == '失效' or any(
            keyword in (raw.raw_name or raw.name or '').strip()
            for keyword in self._disable_keywords()
        )
        override = manual.get('is_disabled_override')
        manual['is_disabled'] = default_disabled if override is None else bool(override)
        return manual


material_service = MaterialService()
