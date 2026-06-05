from typing import List, Optional
from database.base import db
from database.models.product.finished import ProductTag, ProductTagCategory, ProductFinished


class TagCategoryRepository:

    @staticmethod
    def get_all() -> List[ProductTagCategory]:
        return ProductTagCategory.query.order_by(ProductTagCategory.sort_order, ProductTagCategory.name).all()

    @staticmethod
    def get_by_id(category_id: int) -> Optional[ProductTagCategory]:
        return db.session.get(ProductTagCategory, category_id)

    @staticmethod
    def get_by_name(name: str) -> Optional[ProductTagCategory]:
        return ProductTagCategory.query.filter_by(name=name).first()

    @staticmethod
    def create(name: str, color: str, sort_order: int = 0) -> ProductTagCategory:
        cat = ProductTagCategory(name=name, color=color, sort_order=sort_order)
        db.session.add(cat)
        db.session.commit()
        return cat

    @staticmethod
    def update(cat: ProductTagCategory, name: str, color: str, sort_order: int) -> ProductTagCategory:
        cat.name       = name
        cat.color      = color
        cat.sort_order = sort_order
        db.session.commit()
        return cat

    @staticmethod
    def delete(cat: ProductTagCategory) -> None:
        db.session.delete(cat)
        db.session.commit()


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
    def create(name: str, category_id: Optional[int] = None) -> ProductTag:
        # color 列数据库仍为 NOT NULL，始终写入默认值
        tag = ProductTag(name=name, color='#c4883a', category_id=category_id)
        db.session.add(tag)
        db.session.commit()
        return tag

    @staticmethod
    def update(tag: ProductTag, name: str, category_id: Optional[int]) -> ProductTag:
        tag.name        = name
        tag.category_id = category_id
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
