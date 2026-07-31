from sqlalchemy import or_

from database.base import db
from database.models.product.import_raw import ImportProductRaw
from database.models.product.material import ErpGroupCategory, ProductMaterial


class MaterialRepository:
    @staticmethod
    def all_raw_identity_rows():
        return db.session.query(
            ImportProductRaw.code, ImportProductRaw.group_code, ImportProductRaw.group_name,
        ).all()

    @staticmethod
    def group_configs():
        return {row.group_code: row for row in ErpGroupCategory.query.all()}

    @staticmethod
    def save_group(group_code, values):
        row = ErpGroupCategory.query.filter_by(group_code=group_code).first()
        if row is None:
            row = ErpGroupCategory(group_code=group_code)
            db.session.add(row)
        for key, value in values.items():
            setattr(row, key, value)
        db.session.commit()
        return row

    @staticmethod
    def raw_query(keyword=None, group_code=None):
        query = ImportProductRaw.query
        if keyword:
            like = f'%{keyword}%'
            query = query.filter(or_(ImportProductRaw.code.like(like), ImportProductRaw.name.like(like)))
        if group_code:
            query = query.filter(ImportProductRaw.group_code == group_code)
        return query.order_by(ImportProductRaw.code.asc())

    @staticmethod
    def materials_for_codes(codes):
        if not codes:
            return {}
        return {
            row.code: row for row in ProductMaterial.query
            .filter(ProductMaterial.code.in_(codes)).all()
        }

    @staticmethod
    def raw_by_code(code):
        return ImportProductRaw.query.filter_by(code=code).first()

    @staticmethod
    def save_material(code, values):
        row = ProductMaterial.query.filter_by(code=code).first()
        if row is None:
            row = ProductMaterial(code=code)
            db.session.add(row)
        for key, value in values.items():
            setattr(row, key, value)
        db.session.commit()
        return row
