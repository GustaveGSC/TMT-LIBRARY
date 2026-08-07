"""售后物料组合的校验、事务与响应组装。"""

from sqlalchemy.exc import IntegrityError

from database.base import db
from database.repository.product.material_combo import MaterialComboRepository
from result import Result


class MaterialComboService:
    @staticmethod
    def _optional_text(value, maximum, label):
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError(f'{label}格式无效')
        value = value.strip()
        if len(value) > maximum:
            raise ValueError(f'{label}不能超过 {maximum} 个字符')
        return value or None

    @staticmethod
    def _integer(value, label, *, minimum=None):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f'{label}必须是整数')
        if minimum is not None and value < minimum:
            raise ValueError(f'{label}必须是正整数')
        return value

    def _payload(self, body, *, created_by=None):
        if not isinstance(body, dict):
            raise ValueError('请求体格式无效')
        name = self._optional_text(body.get('name'), 200, '组合名称')
        if not name:
            raise ValueError('组合名称不能为空')
        raw_items = body.get('items', [])
        if not isinstance(raw_items, list):
            raise ValueError('items 必须是数组')
        items, seen = [], set()
        for index, raw in enumerate(raw_items):
            if not isinstance(raw, dict):
                raise ValueError(f'第 {index + 1} 条明细格式无效')
            code = raw.get('material_code')
            if not isinstance(code, str) or not code.strip():
                raise ValueError(f'第 {index + 1} 条明细的物料编码不能为空')
            code = code.strip()
            if len(code) > 255:
                raise ValueError(f'物料编码「{code[:30]}…」不能超过 255 个字符')
            normalized = code.casefold()
            if normalized in seen:
                raise ValueError(f'物料编码「{code}」重复')
            seen.add(normalized)
            quantity = self._integer(raw.get('quantity'), f'物料「{code}」的数量', minimum=1)
            sort_order = raw.get('sort_order', index)
            sort_order = self._integer(sort_order, f'物料「{code}」的排序')
            items.append({
                'material_code': code, 'quantity': quantity, 'sort_order': sort_order,
            })
        is_disabled = body.get('is_disabled', False)
        if not isinstance(is_disabled, bool):
            raise ValueError('停用状态必须是布尔值')
        sort_order = self._integer(body.get('sort_order', 0), '组合排序')
        values = {
            'name': name,
            'category': self._optional_text(body.get('category'), 100, '分类'),
            'remark': self._optional_text(body.get('remark'), 65535, '备注'),
            'is_disabled': is_disabled,
            'sort_order': sort_order,
        }
        if created_by is not None:
            values['created_by'] = created_by
        return values, items

    @staticmethod
    def _serialize(combos, items, material_details):
        items_by_combo = {combo.id: [] for combo in combos}
        for item in items:
            detail = material_details.get(item.material_code, {
                'material_name': None, 'short_name': None,
                'group_name': None, 'is_missing': True, 'is_disabled': False,
            })
            payload = item.to_dict()
            payload.update(detail)
            items_by_combo.setdefault(item.combo_id, []).append(payload)
        result = []
        for combo in combos:
            payload = combo.to_dict()
            payload['items'] = items_by_combo.get(combo.id, [])
            result.append(payload)
        return result

    def _load(self, combos):
        items = MaterialComboRepository.items_for_combos([combo.id for combo in combos])
        details = MaterialComboRepository.material_details(
            list(dict.fromkeys(item.material_code for item in items))
        )
        return self._serialize(combos, items, details)

    def list(self, keyword=None, category=None, is_disabled=None):
        combos = MaterialComboRepository.list_combos(keyword, category, is_disabled)
        return Result.ok(data={'items': self._load(combos), 'total': len(combos)})

    def get_one(self, combo_id):
        combo = MaterialComboRepository.get(combo_id)
        if not combo:
            return Result.fail('物料组合不存在')
        return Result.ok(data=self._load([combo])[0])

    def save(self, body, *, combo_id=None, created_by=None):
        combo = MaterialComboRepository.get(combo_id) if combo_id is not None else None
        if combo_id is not None and not combo:
            return Result.fail('物料组合不存在')
        try:
            values, items = self._payload(
                body, created_by=created_by if combo is None else None,
            )
            combo = MaterialComboRepository.save(combo, values, items)
            return self.get_one(combo.id)
        except ValueError as exc:
            db.session.rollback()
            return Result.fail(str(exc))
        except IntegrityError as exc:
            db.session.rollback()
            detail = str(getattr(exc, 'orig', exc))
            if 'uq_material_combo_name' in detail or 'material_combo.name' in detail:
                return Result.fail('组合名称已存在')
            return Result.fail('明细物料编码重复')

    def delete(self, combo_id):
        combo = MaterialComboRepository.get(combo_id)
        if not combo:
            return Result.fail('物料组合不存在')
        MaterialComboRepository.delete(combo)
        return Result.ok()

    @staticmethod
    def categories():
        return Result.ok(data=MaterialComboRepository.categories())


material_combo_service = MaterialComboService()
