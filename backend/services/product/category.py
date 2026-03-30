from database.repository.product.category import CategoryRepository
from result import Result


class CategoryService:

    # ── Tree ──────────────────────────────────────────────────────────────

    def get_tree(self) -> Result:
        """返回完整三级树"""
        categories = CategoryRepository.get_all_tree()
        return Result.ok(data=[c.to_dict(with_children=True) for c in categories])

    # ── Category ──────────────────────────────────────────────────────────

    def create_category(self, name: str, sort_order: int = 0) -> Result:
        name = (name or '').strip()
        if not name:
            return Result.fail('分类名称不能为空')
        if CategoryRepository.get_category_by_name(name):
            return Result.fail(f'分类「{name}」已存在')
        obj = CategoryRepository.create_category(name, sort_order)
        return Result.ok(data=obj.to_dict(), message='分类创建成功')

    def update_category(self, category_id: int, **kwargs) -> Result:
        obj = CategoryRepository.get_category(category_id)
        if not obj:
            return Result.fail('分类不存在')
        if 'name' in kwargs:
            kwargs['name'] = kwargs['name'].strip()
            if not kwargs['name']:
                return Result.fail('名称不能为空')
            exist = CategoryRepository.get_category_by_name(kwargs['name'])
            if exist and exist.id != category_id:
                return Result.fail(f'分类「{kwargs["name"]}」已存在')
        obj = CategoryRepository.update_category(obj, **kwargs)
        return Result.ok(data=obj.to_dict(), message='更新成功')

    def delete_category(self, category_id: int) -> Result:
        obj = CategoryRepository.get_category(category_id)
        if not obj:
            return Result.fail('分类不存在')
        if obj.series.count() > 0:
            return Result.fail('请先删除该分类下的所有系列')
        CategoryRepository.delete_category(obj)
        return Result.ok(message='删除成功')

    # ── Series ────────────────────────────────────────────────────────────

    def create_series(self, category_id: int, code: str, name: str, sort_order: int = 0) -> Result:
        code = (code or '').strip()
        name = (name or '').strip()
        if not code:
            return Result.fail('系列编码不能为空')
        if not name:
            return Result.fail('系列名称不能为空')
        if not CategoryRepository.get_category(category_id):
            return Result.fail('所属分类不存在')
        if CategoryRepository.get_series_by_code(category_id, code):
            return Result.fail(f'编码「{code}」在该品类下已存在')
        if CategoryRepository.get_series_by_name(category_id, name):
            return Result.fail(f'系列「{name}」已存在')
        obj = CategoryRepository.create_series(category_id, code, name, sort_order)
        return Result.ok(data=obj.to_dict(), message='系列创建成功')

    def update_series(self, series_id: int, **kwargs) -> Result:
        obj = CategoryRepository.get_series(series_id)
        if not obj:
            return Result.fail('系列不存在')
        if 'code' in kwargs:
            kwargs['code'] = kwargs['code'].strip()
            if not kwargs['code']:
                return Result.fail('编码不能为空')
            exist = CategoryRepository.get_series_by_code(obj.category_id, kwargs['code'])
            if exist and exist.id != series_id:
                return Result.fail(f'编码「{kwargs["code"]}」在该品类下已存在')
        if 'name' in kwargs:
            kwargs['name'] = kwargs['name'].strip()
            if not kwargs['name']:
                return Result.fail('名称不能为空')
            exist = CategoryRepository.get_series_by_name(obj.category_id, kwargs['name'])
            if exist and exist.id != series_id:
                return Result.fail(f'系列「{kwargs["name"]}」已存在')
        obj = CategoryRepository.update_series(obj, **kwargs)
        return Result.ok(data=obj.to_dict(), message='更新成功')

    def delete_series(self, series_id: int) -> Result:
        obj = CategoryRepository.get_series(series_id)
        if not obj:
            return Result.fail('系列不存在')
        if obj.models.count() > 0:
            return Result.fail('请先删除该系列下的所有型号')
        CategoryRepository.delete_series(obj)
        return Result.ok(message='删除成功')

    # ── Model ─────────────────────────────────────────────────────────────

    def create_model(self, series_id: int, code: str, name: str,
                     model_code: str = '', name_en: str = '',
                     sort_order: int = 0) -> Result:
        code       = (code       or '').strip()
        name       = (name       or '').strip()
        model_code = (model_code or '').strip()
        name_en    = (name_en    or '').strip() or None
        if not code:
            return Result.fail('ERP编码不能为空')
        if not name:
            return Result.fail('型号名称不能为空')
        if not model_code:
            return Result.fail('型号编码不能为空')
        if not CategoryRepository.get_series(series_id):
            return Result.fail('所属系列不存在')
        if CategoryRepository.get_model_by_code(series_id, code):
            return Result.fail(f'ERP编码「{code}」在该系列下已存在')
        if CategoryRepository.get_model_by_model_code(model_code):
            return Result.fail(f'型号编码「{model_code}」已存在')
        if CategoryRepository.get_model_by_name(series_id, name):
            return Result.fail(f'型号「{name}」已存在')
        obj = CategoryRepository.create_model(series_id, code, name,
                                              model_code=model_code, name_en=name_en,
                                              sort_order=sort_order)
        return Result.ok(data=obj.to_dict(), message='型号创建成功')

    def update_model(self, model_id: int, **kwargs) -> Result:
        obj = CategoryRepository.get_model(model_id)
        if not obj:
            return Result.fail('型号不存在')
        if 'code' in kwargs:
            kwargs['code'] = kwargs['code'].strip()
            if not kwargs['code']:
                return Result.fail('ERP编码不能为空')
            exist = CategoryRepository.get_model_by_code(obj.series_id, kwargs['code'])
            if exist and exist.id != model_id:
                return Result.fail(f'ERP编码「{kwargs["code"]}」在该系列下已存在')
        if 'model_code' in kwargs:
            kwargs['model_code'] = kwargs['model_code'].strip()
            if not kwargs['model_code']:
                return Result.fail('型号编码不能为空')
            exist = CategoryRepository.get_model_by_model_code(kwargs['model_code'])
            if exist and exist.id != model_id:
                return Result.fail(f'型号编码「{kwargs["model_code"]}」已存在')
        if 'name' in kwargs:
            kwargs['name'] = kwargs['name'].strip()
            if not kwargs['name']:
                return Result.fail('名称不能为空')
            exist = CategoryRepository.get_model_by_name(obj.series_id, kwargs['name'])
            if exist and exist.id != model_id:
                return Result.fail(f'型号「{kwargs["name"]}」已存在')
        if 'name_en' in kwargs:
            kwargs['name_en'] = (kwargs['name_en'] or '').strip() or None
        obj = CategoryRepository.update_model(obj, **kwargs)
        return Result.ok(data=obj.to_dict(), message='更新成功')

    def delete_model(self, model_id: int) -> Result:
        obj = CategoryRepository.get_model(model_id)
        if not obj:
            return Result.fail('型号不存在')
        CategoryRepository.delete_model(obj)
        return Result.ok(message='删除成功')


category_service = CategoryService()