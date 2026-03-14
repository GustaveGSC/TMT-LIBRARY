from result import Result
from database.repository.product.tag import TagRepository
from database.repository.product.finished import FinishedRepository


class TagService:

    # ── 标签 CRUD ─────────────────────────────────────────────────────────

    @staticmethod
    def get_all() -> Result:
        tags = TagRepository.get_all()
        return Result.ok(data=[t.to_dict() for t in tags])

    @staticmethod
    def create(name: str, color: str) -> Result:
        name = name.strip()
        if not name:
            return Result.fail('名称不能为空')
        if len(name) > 32:
            return Result.fail('名称不能超过 32 个字符')
        if TagRepository.get_by_name(name):
            return Result.fail(f'标签「{name}」已存在')
        tag = TagRepository.create(name=name, color=color or '#c4883a')
        return Result.ok(data=tag.to_dict(), message='创建成功')

    @staticmethod
    def update(tag_id: int, name: str, color: str) -> Result:
        tag = TagRepository.get_by_id(tag_id)
        if not tag:
            return Result.fail('标签不存在')
        name = name.strip()
        if not name:
            return Result.fail('名称不能为空')
        if len(name) > 32:
            return Result.fail('名称不能超过 32 个字符')
        # 检查重名（排除自身）
        existing = TagRepository.get_by_name(name)
        if existing and existing.id != tag_id:
            return Result.fail(f'标签「{name}」已存在')
        tag = TagRepository.update(tag, name=name, color=color or '#c4883a')
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