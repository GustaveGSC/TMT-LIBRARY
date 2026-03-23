from result import Result
from database.repository.product.param import ParamRepository, VALID_GROUPS

GROUP_LABELS = {
    'dimension': '尺寸',
    'config':    '配置',
    'brand':     '品牌',
    'other':     '其他',
}


def _group_keys(keys):
    """将键名列表按分组聚合成 dict"""
    grouped = {g: [] for g in VALID_GROUPS}
    for k in keys:
        if k.group_name in grouped:
            grouped[k.group_name].append(k.to_dict())
    return grouped


def _group_params(params):
    """将参数值列表按分组聚合"""
    grouped = {g: [] for g in VALID_GROUPS}
    for p in params:
        gname = p.key.group_name if p.key else None
        if gname in grouped:
            grouped[gname].append(p.to_dict())
    return grouped


class ParamService:

    # ── 键名管理 ─────────────────────────────────────────────────────────

    @staticmethod
    def get_all_keys() -> Result:
        keys = ParamRepository.get_all_keys()
        return Result.ok(data=_group_keys(keys))

    @staticmethod
    def create_key(name: str, group_name: str, sort_order: int = 0) -> Result:
        name = (name or '').strip()
        if not name:
            return Result.fail('参数名称不能为空')
        if group_name not in VALID_GROUPS:
            return Result.fail(f'无效分组：{group_name}')
        if ParamRepository.get_key_by_name_group(name, group_name):
            return Result.fail(f'该分组下已存在同名参数：{name}')
        key = ParamRepository.create_key(name, group_name, sort_order)
        return Result.ok(data=key.to_dict(), message='创建成功')

    @staticmethod
    def update_key(key_id: int, name: str = None, group_name: str = None, sort_order: int = None) -> Result:
        key = ParamRepository.get_key_by_id(key_id)
        if not key:
            return Result.fail('参数键名不存在')
        updates = {}
        if name is not None:
            name = name.strip()
            if not name:
                return Result.fail('参数名称不能为空')
            # 检查改名后是否与同分组其他键名重复
            target_group = group_name if group_name else key.group_name
            existing = ParamRepository.get_key_by_name_group(name, target_group)
            if existing and existing.id != key_id:
                return Result.fail(f'该分组下已存在同名参数：{name}')
            updates['name'] = name
        if group_name is not None:
            if group_name not in VALID_GROUPS:
                return Result.fail(f'无效分组：{group_name}')
            updates['group_name'] = group_name
        if sort_order is not None:
            updates['sort_order'] = sort_order
        key = ParamRepository.update_key(key, **updates)
        return Result.ok(data=key.to_dict(), message='更新成功')

    @staticmethod
    def delete_key(key_id: int) -> Result:
        key = ParamRepository.get_key_by_id(key_id)
        if not key:
            return Result.fail('参数键名不存在')
        usage = ParamRepository.count_key_usage(key_id)
        ParamRepository.delete_key(key)
        return Result.ok(data={'usage': usage}, message=f'已删除（影响 {usage} 个成品）')

    # ── 成品参数值 ────────────────────────────────────────────────────────

    @staticmethod
    def get_params_for_finished(finished_id: int) -> Result:
        from database.models.product.finished import ProductFinished
        if not ProductFinished.query.get(finished_id):
            return Result.fail('成品不存在')
        params = ParamRepository.get_params_for_finished(finished_id)
        return Result.ok(data=_group_params(params))

    @staticmethod
    def save_params_for_finished(finished_id: int, groups: dict) -> Result:
        from database.models.product.finished import ProductFinished
        if not ProductFinished.query.get(finished_id):
            return Result.fail('成品不存在')

        # 将各分组数据展平；key_id 存在则直接用，否则按 key_name find-or-create
        flat = []
        seen_key_ids = set()
        for group_name, items in groups.items():
            if group_name not in VALID_GROUPS:
                continue
            for idx, item in enumerate(items or []):
                key_id   = item.get('key_id')
                key_name = (item.get('key_name') or '').strip()
                if key_id:
                    key = ParamRepository.get_key_by_id(key_id)
                    if not key:
                        continue  # 已被删除，跳过
                elif key_name:
                    # 自由输入的键名：find-or-create
                    key = ParamRepository.get_key_by_name_group(key_name, group_name)
                    if not key:
                        key = ParamRepository.create_key(key_name, group_name)
                    key_id = key.id
                else:
                    continue  # 既无 key_id 又无 key_name，跳过
                if key_id in seen_key_ids:
                    continue  # 同一成品同一 key 只保留第一条
                seen_key_ids.add(key_id)
                flat.append({
                    'key_id':     key_id,
                    'value':      item.get('value', ''),
                    'sort_order': item.get('sort_order', idx),
                })

        ParamRepository.save_params_for_finished(finished_id, flat)
        # 返回最新数据
        params = ParamRepository.get_params_for_finished(finished_id)
        return Result.ok(data=_group_params(params), message='保存成功')
