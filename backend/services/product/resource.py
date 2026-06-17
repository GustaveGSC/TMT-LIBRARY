from sqlalchemy.exc import IntegrityError
from result import Result
from database.repository.product.resource import ResourceRepository
from database.base import db


class ResourceService:

    # ── 类型 ──────────────────────────────────────────────────────────────

    def list_types(self) -> Result:
        types = ResourceRepository.list_types()
        return Result.ok(data=[t.to_dict() for t in types])

    def create_type(self, name: str, sort_order: int = 0) -> Result:
        name = (name or '').strip()
        if not name:
            return Result.fail('类型名称不能为空')
        try:
            t = ResourceRepository.create_type(name, sort_order)
            return Result.ok(data=t.to_dict())
        except IntegrityError:
            db.session.rollback()
            return Result.fail('类型名称已存在')

    def update_type(self, type_id: int, **kwargs) -> Result:
        t = ResourceRepository.get_type(type_id)
        if not t:
            return Result.fail('类型不存在')
        t = ResourceRepository.update_type(t, **kwargs)
        return Result.ok(data=t.to_dict())

    def delete_type(self, type_id: int) -> Result:
        t = ResourceRepository.get_type(type_id)
        if not t:
            return Result.fail('类型不存在')
        if ResourceRepository.type_has_resources(type_id):
            return Result.fail('该类型下还有资料，请先移除或修改这些资料的类型')
        ResourceRepository.delete_type(t)
        return Result.ok()

    # ── 资料条目 ──────────────────────────────────────────────────────────

    def list_resources(self, type_id=None, search=None, page=1, size=50) -> Result:
        items, total = ResourceRepository.list_resources(type_id, search, page, size)
        return Result.ok(data={'items': items, 'total': total, 'page': page, 'size': size})

    def get_resource(self, resource_id: int) -> Result:
        r = ResourceRepository.get_resource(resource_id)
        if not r:
            return Result.fail('资料不存在')
        return Result.ok(data=r.to_dict())

    def _validate_type_id(self, type_id) -> Result | None:
        """若传了 type_id，校验其存在；返回 None 表示合法，返回 Result 表示错误。"""
        if type_id is not None and not ResourceRepository.get_type(type_id):
            return Result.fail(f'资料类型 {type_id} 不存在')
        return None

    def create_resource(self, title: str, url: str, **kwargs) -> Result:
        title = (title or '').strip()
        url   = (url   or '').strip()
        if not title or not url:
            return Result.fail('标题和链接不能为空')
        err = self._validate_type_id(kwargs.get('type_id'))
        if err: return err
        try:
            r = ResourceRepository.create_resource(title=title, url=url, **kwargs)
            return Result.ok(data=r.to_dict())
        except IntegrityError:
            db.session.rollback()
            return Result.fail('数据冲突，请检查输入')

    def update_resource(self, resource_id: int, **kwargs) -> Result:
        r = ResourceRepository.get_resource(resource_id)
        if not r:
            return Result.fail('资料不存在')
        if 'type_id' in kwargs:
            err = self._validate_type_id(kwargs['type_id'])
            if err: return err
        try:
            r = ResourceRepository.update_resource(r, **kwargs)
            return Result.ok(data=r.to_dict())
        except IntegrityError:
            db.session.rollback()
            return Result.fail('数据冲突，请检查输入')

    def delete_resource(self, resource_id: int) -> Result:
        r = ResourceRepository.get_resource(resource_id)
        if not r:
            return Result.fail('资料不存在')
        ResourceRepository.delete_resource(r)
        return Result.ok()

    # ── 产品-资料关联 ─────────────────────────────────────────────────────

    def get_product_resources(self, code: str) -> Result:
        finished = ResourceRepository.get_finished_by_code(code)
        if not finished:
            return Result.fail('成品不存在')
        items = ResourceRepository.get_product_resources(finished.id)
        return Result.ok(data=items)

    def link_resource(self, code: str, resource_id: int, sort_order: int = 0) -> Result:
        finished = ResourceRepository.get_finished_by_code(code)
        if not finished:
            return Result.fail('成品不存在')
        r = ResourceRepository.get_resource(resource_id)
        if not r:
            return Result.fail('资料不存在')
        ResourceRepository.link_resource(finished.id, resource_id, sort_order)
        return Result.ok()

    def unlink_resource(self, code: str, resource_id: int) -> Result:
        finished = ResourceRepository.get_finished_by_code(code)
        if not finished:
            return Result.fail('成品不存在')
        ResourceRepository.unlink_resource(finished.id, resource_id)
        return Result.ok()

    def set_resource_models(self, resource_id: int, model_ids: list) -> Result:
        r = ResourceRepository.get_resource(resource_id)
        if not r:
            return Result.fail('资料不存在')
        ResourceRepository.set_resource_models(resource_id, model_ids)
        return Result.ok()

    def set_resource_tags(self, resource_id: int, tag_ids: list) -> Result:
        r = ResourceRepository.get_resource(resource_id)
        if not r:
            return Result.fail('资料不存在')
        ResourceRepository.set_resource_tags(resource_id, tag_ids)
        return Result.ok()

    def update_order(self, code: str, ordered_ids: list) -> Result:
        finished = ResourceRepository.get_finished_by_code(code)
        if not finished:
            return Result.fail('成品不存在')
        ResourceRepository.update_order(finished.id, ordered_ids)
        return Result.ok()


resource_service = ResourceService()
