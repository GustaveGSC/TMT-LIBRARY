from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict
from database.base import db
from database.models.product.param import ProductParamKey, ProductFinishedParam

CST = timezone(timedelta(hours=8))
def now_cst(): return datetime.now(CST).replace(tzinfo=None)

VALID_GROUPS = ('dimension', 'config', 'brand', 'other')


class ParamRepository:

    # ── 键名管理 ─────────────────────────────────────────────────────────

    @staticmethod
    def get_all_keys() -> List[ProductParamKey]:
        """获取所有参数键名，按分组+排序号排列"""
        return ProductParamKey.query.order_by(
            ProductParamKey.group_name, ProductParamKey.sort_order
        ).all()

    @staticmethod
    def get_key_by_id(key_id: int) -> Optional[ProductParamKey]:
        return ProductParamKey.query.get(key_id)

    @staticmethod
    def get_key_by_name_group(name: str, group_name: str) -> Optional[ProductParamKey]:
        return ProductParamKey.query.filter_by(name=name, group_name=group_name).first()

    @staticmethod
    def create_key(name: str, group_name: str, sort_order: int = 0) -> ProductParamKey:
        key = ProductParamKey(name=name, group_name=group_name, sort_order=sort_order, created_at=now_cst())
        db.session.add(key)
        db.session.commit()
        return key

    @staticmethod
    def update_key(key: ProductParamKey, **kwargs) -> ProductParamKey:
        for field, val in kwargs.items():
            if hasattr(key, field):
                setattr(key, field, val)
        db.session.commit()
        return key

    @staticmethod
    def delete_key(key: ProductParamKey) -> None:
        db.session.delete(key)
        db.session.commit()

    @staticmethod
    def count_key_usage(key_id: int) -> int:
        """统计有多少成品使用了该键名"""
        return ProductFinishedParam.query.filter_by(key_id=key_id).count()

    # ── 成品参数值 ────────────────────────────────────────────────────────

    @staticmethod
    def get_params_for_finished(finished_id: int) -> List[ProductFinishedParam]:
        """获取某成品的所有参数，按排序号排列"""
        return (ProductFinishedParam.query
                .filter_by(finished_id=finished_id)
                .join(ProductParamKey, ProductFinishedParam.key_id == ProductParamKey.id)
                .order_by(ProductParamKey.group_name, ProductFinishedParam.sort_order)
                .all())

    @staticmethod
    def save_params_for_finished(finished_id: int, params_list: List[Dict]) -> None:
        """Upsert 方式保存成品参数：已有的更新，新增的插入，不在列表里的删除。
        params_list: [{key_id, value, sort_order}, ...]
        """
        now = now_cst()

        # 以 key_id 为索引，获取已有记录
        existing = {
            p.key_id: p
            for p in ProductFinishedParam.query.filter_by(finished_id=finished_id).all()
        }

        incoming_key_ids = set()
        for item in params_list:
            key_id = item.get('key_id')
            if not key_id:
                continue
            incoming_key_ids.add(key_id)
            if key_id in existing:
                # 更新已有记录
                rec = existing[key_id]
                rec.value      = item.get('value', '')
                rec.sort_order = item.get('sort_order', 0)
                rec.updated_at = now
            else:
                # 插入新记录
                db.session.add(ProductFinishedParam(
                    finished_id=finished_id,
                    key_id=key_id,
                    value=item.get('value', ''),
                    sort_order=item.get('sort_order', 0),
                    created_at=now,
                    updated_at=now,
                ))

        # 删除不在提交列表里的旧记录
        for key_id, rec in existing.items():
            if key_id not in incoming_key_ids:
                db.session.delete(rec)

        db.session.commit()
