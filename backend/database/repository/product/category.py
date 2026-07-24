from typing import Optional, List
from database.base import db
from database.models.product.category import ProductCategory, ProductSeries, ProductModel, now_cst


class CategoryRepository:

    # ── Category ──────────────────────────────────────────────────────────

    @staticmethod
    def  get_all_tree() -> List[ProductCategory]:
        """获取完整树，按 sort_order 排序"""
        return ProductCategory.query.order_by(ProductCategory.sort_order, ProductCategory.id).all()

    @staticmethod
    def get_all_tree_data() -> List[dict]:
        """Build the complete three-level tree with a fixed three queries."""
        categories = ProductCategory.query.order_by(
            ProductCategory.sort_order, ProductCategory.id,
        ).all()
        series = ProductSeries.query.order_by(
            ProductSeries.sort_order, ProductSeries.id,
        ).all()
        models = ProductModel.query.order_by(
            ProductModel.sort_order, ProductModel.id,
        ).all()

        category_data = []
        category_by_id = {}
        for category in categories:
            item = category.to_dict()
            item['series'] = []
            category_data.append(item)
            category_by_id[category.id] = item

        series_by_id = {}
        for product_series in series:
            item = product_series.to_dict()
            item['models'] = []
            series_by_id[product_series.id] = item
            parent = category_by_id.get(product_series.category_id)
            if parent is not None:
                parent['series'].append(item)

        for model in models:
            parent = series_by_id.get(model.series_id)
            if parent is not None:
                parent['models'].append(model.to_dict())

        return category_data

    @staticmethod
    def get_category(category_id: int) -> Optional[ProductCategory]:
        return db.session.get(ProductCategory, category_id)

    @staticmethod
    def get_category_by_name(name: str) -> Optional[ProductCategory]:
        return ProductCategory.query.filter_by(name=name).first()

    @staticmethod
    def create_category(name: str, sort_order: int = 0) -> ProductCategory:
        obj = ProductCategory(name=name, sort_order=sort_order, created_at=now_cst())
        db.session.add(obj)
        db.session.commit()
        return obj

    @staticmethod
    def update_category(obj: ProductCategory, **kwargs) -> ProductCategory:
        for k, v in kwargs.items():
            if hasattr(obj, k):
                setattr(obj, k, v)
        db.session.commit()
        return obj

    @staticmethod
    def delete_category(obj: ProductCategory) -> None:
        db.session.delete(obj)
        db.session.commit()

    # ── Series ────────────────────────────────────────────────────────────

    @staticmethod
    def get_series(series_id: int) -> Optional[ProductSeries]:
        return db.session.get(ProductSeries, series_id)

    @staticmethod
    def get_series_by_name(category_id: int, name: str) -> Optional[ProductSeries]:
        return ProductSeries.query.filter_by(category_id=category_id, name=name).first()

    @staticmethod
    def get_series_by_code(category_id: int, code: str) -> Optional[ProductSeries]:
        return ProductSeries.query.filter_by(category_id=category_id, code=code).first()

    @staticmethod
    def create_series(category_id: int, code: str, name: str, sort_order: int = 0) -> ProductSeries:
        obj = ProductSeries(category_id=category_id, code=code, name=name,
                            sort_order=sort_order, created_at=now_cst())
        db.session.add(obj)
        db.session.commit()
        return obj

    @staticmethod
    def update_series(obj: ProductSeries, **kwargs) -> ProductSeries:
        for k, v in kwargs.items():
            if hasattr(obj, k):
                setattr(obj, k, v)
        db.session.commit()
        return obj

    @staticmethod
    def delete_series(obj: ProductSeries) -> None:
        db.session.delete(obj)
        db.session.commit()

    # ── Model ─────────────────────────────────────────────────────────────

    @staticmethod
    def get_model(model_id: int) -> Optional[ProductModel]:
        return db.session.get(ProductModel, model_id)

    @staticmethod
    def get_model_by_name(series_id: int, name: str) -> Optional[ProductModel]:
        return ProductModel.query.filter_by(series_id=series_id, name=name).first()

    @staticmethod
    def get_model_by_code(series_id: int, code: str) -> Optional[ProductModel]:
        return ProductModel.query.filter_by(series_id=series_id, code=code).first()

    @staticmethod
    def get_model_by_model_code(model_code: str) -> Optional[ProductModel]:
        return ProductModel.query.filter_by(model_code=model_code).first()

    @staticmethod
    def create_model(series_id: int, code: str, name: str,
                     model_code: str = '', name_en: str = None,
                     sort_order: int = 0) -> ProductModel:
        obj = ProductModel(series_id=series_id, code=code, name=name,
                           model_code=model_code, name_en=name_en or None,
                           sort_order=sort_order, created_at=now_cst())
        db.session.add(obj)
        db.session.commit()
        return obj

    @staticmethod
    def update_model(obj: ProductModel, **kwargs) -> ProductModel:
        for k, v in kwargs.items():
            if hasattr(obj, k):
                setattr(obj, k, v)
        db.session.commit()
        return obj

    @staticmethod
    def delete_model(obj: ProductModel) -> None:
        db.session.delete(obj)
        db.session.commit()
