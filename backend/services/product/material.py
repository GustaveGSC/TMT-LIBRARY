from database.models.product.erp_code_rules import ErpCodeRule, TYPE_LABELS
from database.repository.product.material import MaterialRepository
from result import Result


BOOLEAN_KEYS = ('is_finished', 'is_packaged', 'is_semi', 'is_material', 'is_useless')
CATEGORY_TYPES = ('finished', 'packaged', 'semi', 'material', 'useless')


class MaterialService:
    _rule_cache = None

    @classmethod
    def invalidate_rule_cache(cls):
        cls._rule_cache = None

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
        configs, rules = MaterialRepository.group_configs(), self._rules()
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
        data = row.to_dict()
        data.update({key: bool(getattr(row, key)) for key in BOOLEAN_KEYS})
        return Result.ok(data=data)

    def list_items(self, page, page_size, **filters):
        query = MaterialRepository.raw_query(filters.get('keyword'), filters.get('group_code'))
        raw_rows = query.all()
        configs, rules = MaterialRepository.group_configs(), self._rules()
        classified = [(raw, self._categories(raw.code, raw.group_code, rules, configs)) for raw in raw_rows]
        category = filters.get('category')
        if category:
            classified = [x for x in classified if category in x[1]]
        if filters.get('unclassified'):
            classified = [x for x in classified if not x[1]]
        materials = MaterialRepository.materials_for_codes([raw.code for raw, _ in classified])
        disabled = filters.get('is_disabled')
        if disabled is not None:
            classified = [
                x for x in classified
                if bool(materials.get(x[0].code) and materials[x[0].code].is_disabled) == disabled
            ]
        total = len(classified)
        selected = classified[(page - 1) * page_size:page * page_size]
        return Result.ok(data={
            'items': [self._serialize(raw, cats, materials.get(raw.code)) for raw, cats in selected],
            'total': total, 'page': page, 'page_size': page_size,
        })

    def detail(self, code):
        raw = MaterialRepository.raw_by_code(code)
        if not raw:
            return Result.fail('物料不存在')
        cats = self._categories(code, raw.group_code, self._rules(), MaterialRepository.group_configs())
        material = MaterialRepository.materials_for_codes([code]).get(code)
        return Result.ok(data=self._serialize(raw, cats, material))

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
            values['is_disabled'] = bool(values['is_disabled'])
        MaterialRepository.save_material(code, values)
        return self.detail(code)

    @staticmethod
    def _serialize(raw, categories, material):
        manual = material.to_dict() if material else {
            'code': raw.code, 'short_name': None, 'category': None, 'spec': raw.spec,
            'cover_image': None, 'cover_image_original': None, 'img_updated_at': None,
            'remark': None, 'is_disabled': False,
        }
        if manual.get('spec') is None:
            manual['spec'] = raw.spec
        manual.update({
            'code': raw.code, 'name': raw.name, 'group_code': raw.group_code,
            'group_name': raw.group_name, 'erp_spec': raw.spec, 'categories': categories,
            'category_labels': [TYPE_LABELS[x] for x in categories],
        })
        return manual


material_service = MaterialService()
