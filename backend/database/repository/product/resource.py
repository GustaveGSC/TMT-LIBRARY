from collections import defaultdict

from database.base import db
from database.models.product.resource import ProductResourceType, ProductResource, finished_resource, resource_tag, resource_model
from database.models.product.finished import ProductFinished, finished_tag


def _evaluate_condition_node(node: dict, product_tag_set: set) -> bool:
    """递归计算单个条件节点（新树形格式）"""
    if 'tag_id' in node:
        result = node['tag_id'] in product_tag_set
        return (not result) if node.get('not') else result
    op    = node.get('op', 'AND')
    items = node.get('items', [])
    if not items:
        return True
    if op == 'AND':
        return all(_evaluate_condition_node(item, product_tag_set) for item in items)
    return any(_evaluate_condition_node(item, product_tag_set) for item in items)


def _matches_tag_condition(tag_condition, resource_tag_set: set, product_tag_set: set) -> bool:
    """
    判断资料的标签条件是否与产品的标签集合匹配。

    tag_condition=None          → 旧 OR 逻辑：资料有任意标签与产品标签有交集即匹配
    tag_condition=[[1,5],[3]]   → 旧 OR-of-AND 格式（向后兼容）
    tag_condition={op,items}    → 新树形格式，支持 AND/OR/NOT 任意嵌套
    """
    if not tag_condition:
        return bool(resource_tag_set & product_tag_set)
    # 旧格式：列表的列表
    if isinstance(tag_condition, list):
        for and_group in tag_condition:
            if and_group and all(tid in product_tag_set for tid in and_group):
                return True
        return False
    # 新格式：树形对象
    if isinstance(tag_condition, dict):
        return _evaluate_condition_node(tag_condition, product_tag_set)
    return False


def _extract_condition_tag_ids(tag_condition) -> set:
    """提取条件树里出现过的所有标签 id，用于缩小候选产品范围。"""
    if not tag_condition:
        return set()
    if isinstance(tag_condition, list):
        tag_ids = set()
        for group in tag_condition:
            if isinstance(group, list):
                tag_ids.update(group)
        return tag_ids
    if isinstance(tag_condition, dict):
        if 'tag_id' in tag_condition:
            return {tag_condition['tag_id']}
        tag_ids = set()
        for item in tag_condition.get('items', []):
            tag_ids.update(_extract_condition_tag_ids(item))
        return tag_ids
    return set()


class ResourceRepository:

    # ── 类型 ──────────────────────────────────────────────────────────────

    @staticmethod
    def list_types() -> list[ProductResourceType]:
        return ProductResourceType.query.order_by(ProductResourceType.sort_order, ProductResourceType.id).all()

    @staticmethod
    def get_type(type_id: int) -> ProductResourceType | None:
        return ProductResourceType.query.get(type_id)

    @staticmethod
    def type_has_resources(type_id: int) -> bool:
        return db.session.query(
            ProductResource.query.filter_by(type_id=type_id).exists()
        ).scalar()

    @staticmethod
    def create_type(name: str, sort_order: int = 0) -> ProductResourceType:
        t = ProductResourceType(name=name, sort_order=sort_order)
        db.session.add(t)
        db.session.commit()
        return t

    @staticmethod
    def update_type(t: ProductResourceType, **kwargs) -> ProductResourceType:
        for k, v in kwargs.items():
            if hasattr(t, k):
                setattr(t, k, v)
        db.session.commit()
        return t

    @staticmethod
    def delete_type(t: ProductResourceType) -> None:
        db.session.delete(t)
        db.session.commit()

    # ── 资料条目 ──────────────────────────────────────────────────────────

    @staticmethod
    def list_resources(type_id: int = None, search: str = None,
                       page: int = 1, size: int = 50):
        """返回 (items_with_linked_count, total)。"""
        q = db.session.query(ProductResource)
        if type_id == 'none':
            q = q.filter(ProductResource.type_id.is_(None))
        elif type_id is not None:
            q = q.filter(ProductResource.type_id == type_id)
        if search:
            q = q.filter(ProductResource.title.ilike(f'%{search}%'))

        total = q.count()
        rows  = q.order_by(ProductResource.id.desc()).offset((page - 1) * size).limit(size).all()
        linked_counts = ResourceRepository._count_linked_finished(rows)
        items = [r.to_dict(linked_count=linked_counts.get(r.id, 0)) for r in rows]
        return items, total

    @staticmethod
    def _count_linked_finished(resources: list[ProductResource]) -> dict[int, int]:
        """统计资料关联产品数，标签关联必须遵守 tag_condition 条件树。"""
        resource_ids = [r.id for r in resources]
        if not resource_ids:
            return {}

        linked_ids_by_resource = defaultdict(set)

        direct_rows = (
            db.session.query(finished_resource.c.resource_id, finished_resource.c.finished_id)
            .filter(finished_resource.c.resource_id.in_(resource_ids))
            .all()
        )
        for resource_id, finished_id in direct_rows:
            linked_ids_by_resource[resource_id].add(finished_id)

        model_rows = (
            db.session.query(resource_model.c.resource_id, ProductFinished.id)
            .join(ProductFinished, ProductFinished.model_id == resource_model.c.model_id)
            .filter(resource_model.c.resource_id.in_(resource_ids))
            .all()
        )
        for resource_id, finished_id in model_rows:
            linked_ids_by_resource[resource_id].add(finished_id)

        tag_rows = (
            db.session.query(resource_tag.c.resource_id, resource_tag.c.tag_id)
            .filter(resource_tag.c.resource_id.in_(resource_ids))
            .all()
        )
        resource_tag_map = defaultdict(set)
        for resource_id, tag_id in tag_rows:
            resource_tag_map[resource_id].add(tag_id)

        match_tag_map = {}
        for r in resources:
            condition_tag_ids = _extract_condition_tag_ids(r.tag_condition)
            match_tag_map[r.id] = condition_tag_ids or resource_tag_map.get(r.id, set())

        all_tag_ids = set().union(*match_tag_map.values()) if match_tag_map else set()
        if all_tag_ids:
            product_tag_rows = (
                db.session.query(finished_tag.c.finished_id, finished_tag.c.tag_id)
                .filter(finished_tag.c.tag_id.in_(all_tag_ids))
                .all()
            )
            product_tag_map = defaultdict(set)
            for finished_id, tag_id in product_tag_rows:
                product_tag_map[finished_id].add(tag_id)

            for r in resources:
                match_tag_ids = match_tag_map.get(r.id, set())
                if not match_tag_ids:
                    continue
                for finished_id, product_tag_set in product_tag_map.items():
                    if not (match_tag_ids & product_tag_set):
                        continue
                    current_resource_tags = resource_tag_map.get(r.id, match_tag_ids)
                    if _matches_tag_condition(r.tag_condition, current_resource_tags, product_tag_set):
                        linked_ids_by_resource[r.id].add(finished_id)

        return {resource_id: len(finished_ids) for resource_id, finished_ids in linked_ids_by_resource.items()}

    @staticmethod
    def get_resource(resource_id: int) -> ProductResource | None:
        return ProductResource.query.get(resource_id)

    @staticmethod
    def create_resource(**kwargs) -> ProductResource:
        r = ProductResource(**kwargs)
        db.session.add(r)
        db.session.commit()
        return r

    @staticmethod
    def update_resource(r: ProductResource, **kwargs) -> ProductResource:
        for k, v in kwargs.items():
            if hasattr(r, k):
                setattr(r, k, v)
        db.session.commit()
        return r

    @staticmethod
    def delete_resource(r: ProductResource) -> None:
        db.session.delete(r)
        db.session.commit()

    # ── 产品-资料关联 ─────────────────────────────────────────────────────

    @staticmethod
    def get_finished_by_code(code: str) -> ProductFinished | None:
        return ProductFinished.query.filter_by(code=code).first()

    @staticmethod
    def get_product_resources(finished_id: int) -> list[dict]:
        """返回该成品的资料列表：直接关联 + 标签继承，去重（直接关联优先）。"""
        # 1. 直接关联
        direct_rows = (
            db.session.query(ProductResource, finished_resource.c.sort_order)
            .join(finished_resource, finished_resource.c.resource_id == ProductResource.id)
            .filter(finished_resource.c.finished_id == finished_id)
            .order_by(finished_resource.c.sort_order, ProductResource.id)
            .all()
        )
        direct_ids = {r.id for r, _ in direct_rows}
        result = [r.to_dict(sort_order=so, link_type='direct') for r, so in direct_rows]

        # 2. 标签继承：找该产品的所有 tag_id，再查绑定了这些标签的资料
        tag_ids = [
            row[0] for row in
            db.session.query(finished_tag.c.tag_id)
            .filter(finished_tag.c.finished_id == finished_id)
            .all()
        ]
        seen_ids = set(direct_ids)

        if tag_ids:
            product_tag_set = set(tag_ids)
            # 拉候选：资料只要有任意标签在产品 tag 集合里就进候选（一条 SQL）
            candidates = (
                db.session.query(ProductResource)
                .join(resource_tag, resource_tag.c.resource_id == ProductResource.id)
                .filter(resource_tag.c.tag_id.in_(tag_ids))
                .filter(ProductResource.id.notin_(seen_ids))
                .distinct()
                .order_by(ProductResource.type_id, ProductResource.id)
                .all()
            )
            # Python 层 OR-of-AND 过滤（tags 已 lazy='joined' 随 SQL 一起加载，无 N+1）
            for r in candidates:
                resource_tag_set = {t.id for t in r.tags}
                if _matches_tag_condition(r.tag_condition, resource_tag_set, product_tag_set):
                    seen_ids.add(r.id)
                    result.append(r.to_dict(sort_order=0, link_type='tag'))

        # 3. 型号继承：找该产品的 model_id，查绑定了该型号的资料
        model_id_row = db.session.query(ProductFinished.model_id).filter(
            ProductFinished.id == finished_id
        ).first()
        if model_id_row and model_id_row[0]:
            model_rows = (
                db.session.query(ProductResource)
                .join(resource_model, resource_model.c.resource_id == ProductResource.id)
                .filter(resource_model.c.model_id == model_id_row[0])
                .filter(ProductResource.id.notin_(seen_ids))
                .order_by(ProductResource.type_id, ProductResource.id)
                .all()
            )
            result += [r.to_dict(sort_order=0, link_type='model') for r in model_rows]

        return result

    @staticmethod
    def set_resource_tags(resource_id: int, tag_ids: list[int], tag_condition=None) -> None:
        """替换资料的全部标签关联，并保存 OR-of-AND 条件结构。"""
        db.session.execute(
            resource_tag.delete().where(resource_tag.c.resource_id == resource_id)
        )
        if tag_ids:
            db.session.execute(
                resource_tag.insert(),
                [{'resource_id': resource_id, 'tag_id': tid} for tid in tag_ids],
            )
        # 更新条件结构
        r = ProductResource.query.get(resource_id)
        if r is not None:
            r.tag_condition = tag_condition
        db.session.commit()

    @staticmethod
    def set_resource_models(resource_id: int, model_ids: list[int]) -> None:
        """替换资料的全部型号关联。"""
        db.session.execute(
            resource_model.delete().where(resource_model.c.resource_id == resource_id)
        )
        if model_ids:
            db.session.execute(
                resource_model.insert(),
                [{'resource_id': resource_id, 'model_id': mid} for mid in model_ids],
            )
        db.session.commit()

    @staticmethod
    def link_resource(finished_id: int, resource_id: int, sort_order: int = 0) -> None:
        """关联资料，若已关联则忽略。"""
        exists = db.session.execute(
            finished_resource.select().where(
                finished_resource.c.finished_id == finished_id,
                finished_resource.c.resource_id == resource_id,
            )
        ).first()
        if not exists:
            db.session.execute(
                finished_resource.insert().values(
                    finished_id=finished_id,
                    resource_id=resource_id,
                    sort_order=sort_order,
                )
            )
            db.session.commit()

    @staticmethod
    def unlink_resource(finished_id: int, resource_id: int) -> bool:
        result = db.session.execute(
            finished_resource.delete().where(
                finished_resource.c.finished_id == finished_id,
                finished_resource.c.resource_id == resource_id,
            )
        )
        db.session.commit()
        return result.rowcount > 0

    @staticmethod
    def update_order(finished_id: int, ordered_ids: list[int]) -> None:
        """按传入的 id 顺序更新 sort_order。"""
        for idx, resource_id in enumerate(ordered_ids):
            db.session.execute(
                finished_resource.update()
                .where(
                    finished_resource.c.finished_id == finished_id,
                    finished_resource.c.resource_id == resource_id,
                )
                .values(sort_order=idx)
            )
        db.session.commit()
