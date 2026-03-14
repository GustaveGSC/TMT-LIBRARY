from typing import List, Optional
from database.base import db
from database.models.product.finished import ProductTag, ProductFinished


class TagRepository:

    # ── 标签 CRUD ─────────────────────────────────────────────────────────

    @staticmethod
    def get_all() -> List[ProductTag]:
        return ProductTag.query.order_by(ProductTag.name).all()

    @staticmethod
    def get_by_id(tag_id: int) -> Optional[ProductTag]:
        return db.session.get(ProductTag, tag_id)

    @staticmethod
    def get_by_name(name: str) -> Optional[ProductTag]:
        return ProductTag.query.filter_by(name=name).first()

    @staticmethod
    def create(name: str, color: str) -> ProductTag:
        tag = ProductTag(name=name, color=color)
        db.session.add(tag)
        db.session.commit()
        return tag

    @staticmethod
    def update(tag: ProductTag, name: str, color: str) -> ProductTag:
        tag.name  = name
        tag.color = color
        db.session.commit()
        return tag

    @staticmethod
    def delete(tag: ProductTag) -> None:
        db.session.delete(tag)
        db.session.commit()

    # ── 成品关联 ──────────────────────────────────────────────────────────

    @staticmethod
    def add_tag_to_finished(finished: ProductFinished, tag: ProductTag) -> None:
        if tag not in finished.tags:
            finished.tags.append(tag)
            db.session.commit()

    @staticmethod
    def remove_tag_from_finished(finished: ProductFinished, tag: ProductTag) -> None:
        if tag in finished.tags:
            finished.tags.remove(tag)
            db.session.commit()