from result import Result
from database.repository.product.tag import TagRepository, TagCategoryRepository
from database.repository.product.finished import FinishedRepository


class TagCategoryService:

    @staticmethod
    def get_all() -> Result:
        cats = TagCategoryRepository.get_all()
        # 每个分类附带旗下标签列表
        result = []
        for cat in cats:
            d = cat.to_dict()
            d['tags'] = [t.to_dict() for t in cat.tags.order_by('name').all()]
            result.append(d)
        return Result.ok(data=result)

    @staticmethod
    def create(name: str, color: str, sort_order: int = 0) -> Result:
        name = name.strip()
        if not name:
            return Result.fail('名称不能为空')
        if len(name) > 32:
            return Result.fail('名称不能超过 32 个字符')
        if TagCategoryRepository.get_by_name(name):
            return Result.fail(f'分类「{name}」已存在')
        cat = TagCategoryRepository.create(name=name, color=color or '#c4883a', sort_order=sort_order)
        return Result.ok(data=cat.to_dict(), message='创建成功')

    @staticmethod
    def update(category_id: int, name: str, color: str, sort_order: int = 0) -> Result:
        cat = TagCategoryRepository.get_by_id(category_id)
        if not cat:
            return Result.fail('分类不存在')
        name = name.strip()
        if not name:
            return Result.fail('名称不能为空')
        if len(name) > 32:
            return Result.fail('名称不能超过 32 个字符')
        existing = TagCategoryRepository.get_by_name(name)
        if existing and existing.id != category_id:
            return Result.fail(f'分类「{name}」已存在')
        cat = TagCategoryRepository.update(cat, name=name, color=color or '#c4883a', sort_order=sort_order)
        return Result.ok(data=cat.to_dict(), message='更新成功')

    @staticmethod
    def delete(category_id: int) -> Result:
        cat = TagCategoryRepository.get_by_id(category_id)
        if not cat:
            return Result.fail('分类不存在')
        # 将旗下标签的 category_id 置空（移至未分类）
        for tag in cat.tags.all():
            tag.category_id = None
        from database.base import db
        db.session.commit()
        TagCategoryRepository.delete(cat)
        return Result.ok(message='删除成功，旗下标签已移至未分类')


class TagService:

    # ── 标签 CRUD ─────────────────────────────────────────────────────────

    @staticmethod
    def get_all() -> Result:
        tags = TagRepository.get_all()
        return Result.ok(data=[t.to_dict() for t in tags])

    @staticmethod
    def create(name: str, category_id=None, color: str = None) -> Result:
        name = name.strip()
        if not name:
            return Result.fail('名称不能为空')
        if len(name) > 32:
            return Result.fail('名称不能超过 32 个字符')
        if TagRepository.get_by_name(name):
            return Result.fail(f'标签「{name}」已存在')
        # 若传了 category_id，验证分类存在
        if category_id:
            cat = TagCategoryRepository.get_by_id(int(category_id))
            if not cat:
                return Result.fail('所选分类不存在')
        tag = TagRepository.create(name=name, category_id=int(category_id) if category_id else None)
        # 兼容旧调用方传 color
        if color and not category_id:
            tag.color = color
            from database.base import db
            db.session.commit()
        return Result.ok(data=tag.to_dict(), message='创建成功')

    @staticmethod
    def update(tag_id: int, name: str, category_id=None, color: str = None) -> Result:
        tag = TagRepository.get_by_id(tag_id)
        if not tag:
            return Result.fail('标签不存在')
        name = name.strip()
        if not name:
            return Result.fail('名称不能为空')
        if len(name) > 32:
            return Result.fail('名称不能超过 32 个字符')
        existing = TagRepository.get_by_name(name)
        if existing and existing.id != tag_id:
            return Result.fail(f'标签「{name}」已存在')
        if category_id:
            cat = TagCategoryRepository.get_by_id(int(category_id))
            if not cat:
                return Result.fail('所选分类不存在')
        tag = TagRepository.update(tag, name=name, category_id=int(category_id) if category_id else None)
        return Result.ok(data=tag.to_dict(), message='更新成功')

    @staticmethod
    def delete(tag_id: int) -> Result:
        tag = TagRepository.get_by_id(tag_id)
        if not tag:
            return Result.fail('标签不存在')
        TagRepository.delete(tag)
        return Result.ok(message='删除成功')

    # ── 成品关联 ──────────────────────────────────────────────────────────

    @staticmethod
    def add_to_finished(finished_id: int, tag_id: int) -> Result:
        finished = FinishedRepository.get_finished_by_id(finished_id)
        if not finished:
            return Result.fail('成品不存在')
        tag = TagRepository.get_by_id(tag_id)
        if not tag:
            return Result.fail('标签不存在')
        TagRepository.add_tag_to_finished(finished, tag)
        return Result.ok(message='关联成功')

    @staticmethod
    def remove_from_finished(finished_id: int, tag_id: int) -> Result:
        finished = FinishedRepository.get_finished_by_id(finished_id)
        if not finished:
            return Result.fail('成品不存在')
        tag = TagRepository.get_by_id(tag_id)
        if not tag:
            return Result.fail('标签不存在')
        TagRepository.remove_tag_from_finished(finished, tag)
        return Result.ok(message='取消关联成功')
