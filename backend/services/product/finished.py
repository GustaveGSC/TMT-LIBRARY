from database.repository.product.finished import FinishedRepository
from database.models.product.finished import VALID_STATUSES
from result import Result

VALID_SEARCH_FIELDS = {
    'code', 'name', 'name_en', 'category', 'series_code', 'series_name', 'model_code'
}


class FinishedService:

    # ── 成品列表 ──────────────────────────────────────────────────────────

    def get_finished_list(self, page: int, size: int,
                          search_field: str = '', search_value: str = '',
                          status: str = '') -> Result:
        try:
            # 状态筛选在 Python 层过滤（查询量不大，200条以内）
            total, items = FinishedRepository.query_finished_list(
                page, size, search_field, search_value
            )
            if status:
                items = [i for i in items if i['status'] == status]
                total = len(items)
            return Result.ok(data={
                'total': total,
                'page':  page,
                'size':  size,
                'items': items,
            })
        except Exception as e:
            return Result.fail(f'查询失败：{str(e)}')

    # ── 保存成品信息 ──────────────────────────────────────────────────────

    def save_finished(self, code: str, **kwargs) -> Result:
        if not code:
            return Result.fail('code 不能为空')

        allowed = {'status', 'model_id', 'listed_yymm', 'delisted_yymm', 'cover_image'}
        data = {k: v for k, v in kwargs.items() if k in allowed}

        if 'status' in data and data['status'] not in VALID_STATUSES:
            return Result.fail(f'status 无效，可选值：{", ".join(VALID_STATUSES)}')

        obj = FinishedRepository.get_finished_by_code(code)
        if obj:
            obj = FinishedRepository.update_finished(obj, **data)
        else:
            data.setdefault('status', 'recorded')
            obj = FinishedRepository.create_finished(code, **data)

        return Result.ok(data=obj.to_dict(), message='保存成功')

    # ── 产成品候选（不分页，供下拉选项）─────────────────────────────────

    def get_all_packaged_candidate_codes(self) -> Result:
        try:
            items = FinishedRepository.get_all_packaged_candidate_codes()
            return Result.ok(data=items)
        except Exception as e:
            return Result.fail(f'查询失败：{str(e)}')

    # ── 全量产成品（供前端预加载）────────────────────────────────────────

    def get_all_packaged(self) -> Result:
        try:
            items = FinishedRepository.get_all_packaged()
            return Result.ok(data=items)
        except Exception as e:
            return Result.fail(f'查询失败：{str(e)}')

    # ── 产成品候选列表 ────────────────────────────────────────────────────

    def get_packaged_candidates(self, search: str = '',
                                page: int = 1, size: int = 20) -> Result:
        try:
            total, items = FinishedRepository.query_packaged_candidates(search, page, size)
            return Result.ok(data={'total': total, 'page': page, 'size': size, 'items': items})
        except Exception as e:
            return Result.fail(f'查询失败：{str(e)}')

    # ── 保存产成品信息 ────────────────────────────────────────────────────

    def save_packaged(self, code: str, name: str, **kwargs) -> Result:
        if not code or not name:
            return Result.fail('code 和 name 不能为空')

        allowed = {'length', 'width', 'height', 'volume', 'gross_weight', 'net_weight'}
        data = {k: v for k, v in kwargs.items() if k in allowed}

        obj = FinishedRepository.get_packaged_by_code(code)
        if obj:
            obj = FinishedRepository.update_packaged(obj, name=name, **data)
        else:
            obj = FinishedRepository.create_packaged(code, name, **data)

        return Result.ok(data=obj.to_dict(), message='保存成功')

    # ── 关联管理 ──────────────────────────────────────────────────────────

    def get_packaged_by_finished(self, finished_id: int) -> Result:
        items = FinishedRepository.get_packaged_by_finished(finished_id)
        return Result.ok(data=[p.to_dict() for p in items])

    def add_packaged_relation(self, finished_id: int, packaged_id: int) -> Result:
        fin = FinishedRepository.get_finished_by_id(finished_id)
        if not fin:
            return Result.fail('成品不存在')
        pkg = FinishedRepository.get_packaged_by_id(packaged_id)
        if not pkg:
            return Result.fail('产成品不存在')
        FinishedRepository.add_packaged_to_finished(fin, pkg)
        return Result.ok(message='关联成功')

    def remove_packaged_relation(self, finished_id: int, packaged_id: int) -> Result:
        fin = FinishedRepository.get_finished_by_id(finished_id)
        if not fin:
            return Result.fail('成品不存在')
        pkg = FinishedRepository.get_packaged_by_id(packaged_id)
        if not pkg:
            return Result.fail('产成品不存在')
        FinishedRepository.remove_packaged_from_finished(fin, pkg)
        return Result.ok(message='移除成功')


finished_service = FinishedService()