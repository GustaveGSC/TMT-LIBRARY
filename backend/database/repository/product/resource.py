from sqlalchemy import func, text, union_all
from database.base import db
from database.models.product.resource import ProductResourceType, ProductResource, finished_resource, resource_tag, resource_model
from database.models.product.finished import ProductFinished, finished_tag


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
        # 子查询：linked_count = 直接关联 + 标签继承 + 型号继承（UNION 去重）
        direct_q = db.session.query(
            finished_resource.c.resource_id.label('resource_id'),
            finished_resource.c.finished_id.label('finished_id'),
        )
        tag_q = db.session.query(
            resource_tag.c.resource_id.label('resource_id'),
            finished_tag.c.finished_id.label('finished_id'),
        ).join(finished_tag, finished_tag.c.tag_id == resource_tag.c.tag_id)
        model_q = db.session.query(
            resource_model.c.resource_id.label('resource_id'),
            ProductFinished.id.label('finished_id'),
        ).join(ProductFinished, ProductFinished.model_id == resource_model.c.model_id)

        all_links = union_all(direct_q, tag_q, model_q).subquery('all_links')
        linked_sq = (
            db.session.query(
                all_links.c.resource_id,
                func.count(func.distinct(all_links.c.finished_id)).label('cnt'),
            )
            .group_by(all_links.c.resource_id)
            .subquery('linked_sq')
        )

        q = (
            db.session.query(ProductResource, func.coalesce(linked_sq.c.cnt, 0).label('linked_count'))
            .outerjoin(linked_sq, linked_sq.c.resource_id == ProductResource.id)
        )
        if type_id == 'none':
            q = q.filter(ProductResource.type_id.is_(None))
        elif type_id is not None:
            q = q.filter(ProductResource.type_id == type_id)
        if search:
            q = q.filter(ProductResource.title.ilike(f'%{search}%'))

        total = q.count()
        rows  = q.order_by(ProductResource.id.desc()).offset((page - 1) * size).limit(size).all()
        items = [r.to_dict(linked_count=cnt) for r, cnt in rows]
        return items, total

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
            tag_rows = (
                db.session.query(ProductResource)
                .join(resource_tag, resource_tag.c.resource_id == ProductResource.id)
                .filter(resource_tag.c.tag_id.in_(tag_ids))
                .filter(ProductResource.id.notin_(seen_ids))
                .order_by(ProductResource.type_id, ProductResource.id)
                .all()
            )
            for r in tag_rows:
                seen_ids.add(r.id)
            result += [r.to_dict(sort_order=0, link_type='tag') for r in tag_rows]

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
    def set_resource_tags(resource_id: int, tag_ids: list[int]) -> None:
        """替换资料的全部标签关联。"""
        db.session.execute(
            resource_tag.delete().where(resource_tag.c.resource_id == resource_id)
        )
        if tag_ids:
            db.session.execute(
                resource_tag.insert(),
                [{'resource_id': resource_id, 'tag_id': tid} for tid in tag_ids],
            )
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
