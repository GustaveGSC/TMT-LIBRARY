from collections import defaultdict

from database.base import db
from database.models.product.detail_package import (
    ProductDetailPackage, ProductDetailPackageMedia,
    package_category, package_model, package_series, package_tag,
)
from database.models.product.category import ProductModel, ProductSeries
from database.models.product.finished import ProductFinished, finished_tag
from database.repository.product.resource import _matches_tag_condition


class DetailPackageRepository:
    @staticmethod
    def list_packages(search=None, page=1, size=50):
        query = ProductDetailPackage.query
        if search:
            query = query.filter(ProductDetailPackage.name.ilike(f'%{search}%'))
        total = query.count()
        packages = query.order_by(ProductDetailPackage.updated_at.desc(), ProductDetailPackage.id.desc()).offset(
            (page - 1) * size,
        ).limit(size).all()
        ids = [package.id for package in packages]
        aggregate = {
            row.package_id: (int(row.media_count), row.cover)
            for row in db.session.query(
                ProductDetailPackageMedia.package_id,
                db.func.count(ProductDetailPackageMedia.id).label('media_count'),
                db.func.min(ProductDetailPackageMedia.oss_url).label('cover'),
            ).filter(ProductDetailPackageMedia.package_id.in_(ids)).group_by(
                ProductDetailPackageMedia.package_id,
            ).all()
        } if ids else {}
        return [package.to_dict(
            media_count=aggregate.get(package.id, (0, None))[0],
            cover_thumbnail=aggregate.get(package.id, (0, None))[1],
        ) for package in packages], total

    @staticmethod
    def get(package_id):
        return db.session.get(ProductDetailPackage, package_id)

    @staticmethod
    def create(name):
        package = ProductDetailPackage(name=name)
        db.session.add(package)
        db.session.commit()
        return package

    @staticmethod
    def update(package, **kwargs):
        for key, value in kwargs.items():
            setattr(package, key, value)
        db.session.commit()
        return package

    @staticmethod
    def set_tags(package, tag_ids, tag_condition):
        db.session.execute(package_tag.delete().where(package_tag.c.package_id == package.id))
        if tag_ids:
            db.session.execute(package_tag.insert(), [
                {'package_id': package.id, 'tag_id': tag_id} for tag_id in sorted(set(tag_ids))
            ])
        package.tag_condition = tag_condition
        db.session.commit()

    @staticmethod
    def set_models(package, model_ids):
        db.session.execute(package_model.delete().where(package_model.c.package_id == package.id))
        if model_ids:
            db.session.execute(package_model.insert(), [
                {'package_id': package.id, 'model_id': model_id} for model_id in sorted(set(model_ids))
            ])
        db.session.commit()

    @staticmethod
    def set_series(package, series_ids):
        db.session.execute(package_series.delete().where(package_series.c.package_id == package.id))
        if series_ids:
            db.session.execute(package_series.insert(), [
                {'package_id': package.id, 'series_id': series_id}
                for series_id in sorted(set(series_ids))
            ])
        db.session.commit()

    @staticmethod
    def set_categories(package, category_ids):
        db.session.execute(package_category.delete().where(package_category.c.package_id == package.id))
        if category_ids:
            db.session.execute(package_category.insert(), [
                {'package_id': package.id, 'category_id': category_id}
                for category_id in sorted(set(category_ids))
            ])
        db.session.commit()

    @staticmethod
    def media_for_packages(package_ids):
        grouped = defaultdict(list)
        if not package_ids:
            return grouped
        rows = ProductDetailPackageMedia.query.filter(
            ProductDetailPackageMedia.package_id.in_(package_ids),
        ).order_by(ProductDetailPackageMedia.package_id, ProductDetailPackageMedia.sort_order, ProductDetailPackageMedia.id).all()
        for row in rows:
            grouped[row.package_id].append(row)
        return grouped

    @staticmethod
    def matching_finished_packages(code):
        finished = ProductFinished.query.filter_by(code=code).first()
        if not finished:
            return None, []
        product_tag_set = {
            row[0] for row in db.session.query(finished_tag.c.tag_id).filter(
                finished_tag.c.finished_id == finished.id,
            ).all()
        }
        model_scope = None
        if finished.model_id:
            model_scope = db.session.query(
                ProductModel.series_id, ProductSeries.category_id,
            ).join(
                ProductSeries, ProductSeries.id == ProductModel.series_id,
            ).filter(ProductModel.id == finished.model_id).one_or_none()
        series_id = model_scope.series_id if model_scope else None
        category_id = model_scope.category_id if model_scope else None
        # Constant query count: all packages + selectin-loaded ranges, then exact
        # condition evaluation in Python. This preserves NOT-only conditions.
        packages = ProductDetailPackage.query.order_by(ProductDetailPackage.id).all()
        matched = []
        for package in packages:
            model_match = bool(finished.model_id and finished.model_id in {model.id for model in package.models})
            series_match = bool(series_id and series_id in {series.id for series in package.series})
            category_match = bool(category_id and category_id in {category.id for category in package.categories})
            tag_set = {tag.id for tag in package.tags}
            tag_match = bool(tag_set and _matches_tag_condition(package.tag_condition, tag_set, product_tag_set))
            if model_match or series_match or category_match or tag_match:
                matched.append(package)
        media = DetailPackageRepository.media_for_packages([package.id for package in matched])
        return finished, [(package, media[package.id]) for package in matched]
