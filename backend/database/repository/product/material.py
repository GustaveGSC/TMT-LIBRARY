from sqlalchemy import case, false, func, or_

from database.base import db
from database.models.product.import_raw import ImportProductRaw
from database.models.product.finished import ProductFinished
from database.models.product.material import (
    ErpGroupCategory, MaterialDisableKeyword, MaterialImage, ProductMaterial,
)
from database.models.rd.cost import CostBomNode, CostMaterialPrice


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
    def effective_disabled_expression(keywords):
        source_name = func.coalesce(ImportProductRaw.raw_name, ImportProductRaw.name)
        keyword_match = or_(*[
            source_name.like(f'%{keyword}%') for keyword in keywords
        ]) if keywords else false()
        return func.coalesce(
            or_(ImportProductRaw.status == '失效', keyword_match), false()
        )

    @staticmethod
    def raw_query(
        keyword=None, group_code=None, disabled=None, disable_keywords=(),
        text_conditions=(), sort_by='code', sort_dir='asc', price_state=None,
    ):
        query = ImportProductRaw.query.outerjoin(
            ProductMaterial, ProductMaterial.code == ImportProductRaw.code,
        )
        if keyword:
            like = f'%{keyword}%'
            query = query.filter(or_(ImportProductRaw.code.like(like), ImportProductRaw.name.like(like)))
        if group_code:
            query = query.filter(ImportProductRaw.group_code == group_code)
        if text_conditions:
            query = query.filter(*text_conditions)
        if disabled is not None:
            query = query.filter(
                MaterialRepository.effective_disabled_expression(disable_keywords) == disabled
            )
        if price_state:
            # 显式 COLLATE 跨过生产历史表的 unicode_ci / 0900_ai_ci 裂缝。
            node_code = CostBomNode.code_with_version
            if db.session.get_bind().dialect.name == 'mysql':
                node_code = node_code.collate('utf8mb4_0900_ai_ci')
            has_price = db.exists().where(
                CostMaterialPrice.node_id == CostBomNode.id,
                CostMaterialPrice.unit_price.is_not(None),
                node_code == ImportProductRaw.code,
            )
            query = query.filter(has_price if price_state == 'has' else ~has_price)
        sort_columns = {
            'code': ImportProductRaw.code,
            'name': ImportProductRaw.name,
            'short_name': ProductMaterial.short_name,
            'group_code': ImportProductRaw.group_code,
        }
        column = sort_columns[sort_by]
        direction = column.desc() if sort_dir == 'desc' else column.asc()
        if sort_by == 'short_name':
            # MySQL 的 NULL 默认会在 ASC 最前；两个方向均显式放到最后。
            return query.order_by(ProductMaterial.short_name.is_(None).asc(), direction)
        return query.order_by(direction)

    @staticmethod
    def raw_for_codes(codes):
        if not codes:
            return []
        rows = ImportProductRaw.query.filter(ImportProductRaw.code.in_(codes)).all()
        by_code = {row.code: row for row in rows}
        return [by_code[code] for code in codes if code in by_code]

    @staticmethod
    def materials_for_codes(codes):
        if not codes:
            return {}
        return {
            row.code: row for row in ProductMaterial.query
            .filter(ProductMaterial.code.in_(codes)).all()
        }

    @staticmethod
    def product_cover(code):
        """产品库里同编码成品的主图（缩略图, 原图），没有则返回 None。"""
        return (
            db.session.query(ProductFinished.cover_image, ProductFinished.cover_image_original)
            .filter(ProductFinished.code == code).first()
        )

    @staticmethod
    def images_for_code(code):
        return (
            MaterialImage.query.filter_by(code=code)
            .order_by(MaterialImage.sort_order.asc(), MaterialImage.id.asc()).all()
        )

    @staticmethod
    def image(code, image_id):
        return MaterialImage.query.filter_by(code=code, id=image_id).first()

    @staticmethod
    def add_image(code, url, orig_url, created_by):
        last = (
            MaterialImage.query.filter_by(code=code)
            .order_by(MaterialImage.sort_order.desc()).first()
        )
        row = MaterialImage(
            code=code, url=url, orig_url=orig_url, created_by=created_by,
            sort_order=(last.sort_order + 1) if last else 0,
        )
        db.session.add(row)
        db.session.commit()
        return row

    @staticmethod
    def replace_image(row, url, orig_url):
        row.url = url
        row.orig_url = orig_url
        db.session.commit()
        return row

    @staticmethod
    def delete_image(row):
        db.session.delete(row)
        db.session.commit()

    @staticmethod
    def type_overrides():
        """全部单独指定了物料类型的物料：{code: [type, ...]}。行数很少，一次查全。"""
        rows = ProductMaterial.query.with_entities(
            ProductMaterial.code, ProductMaterial.type_override,
        ).filter(ProductMaterial.type_override.isnot(None)).all()
        return {
            code: [t for t in value.split(',') if t]
            for code, value in rows if value
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

    @staticmethod
    def disable_keywords(enabled_only=False):
        query = MaterialDisableKeyword.query
        if enabled_only:
            query = query.filter_by(is_disabled=False)
        return query.order_by(MaterialDisableKeyword.id.asc()).all()

    @staticmethod
    def disable_keyword(keyword_id):
        return db.session.get(MaterialDisableKeyword, keyword_id)

    @staticmethod
    def save_disable_keyword(row, values):
        if row is None:
            row = MaterialDisableKeyword()
            db.session.add(row)
        for key, value in values.items():
            setattr(row, key, value)
        db.session.commit()
        return row

    @staticmethod
    def delete_disable_keyword(row):
        db.session.delete(row)
        db.session.commit()

    @staticmethod
    def disable_preview(keywords):
        source_name = func.coalesce(ImportProductRaw.raw_name, ImportProductRaw.name)
        keyword_match = or_(*[
            source_name.like(f'%{keyword}%') for keyword in keywords
        ]) if keywords else false()
        status_match = func.coalesce(ImportProductRaw.status == '失效', false())
        return db.session.query(
            func.sum(case((status_match, 1), else_=0)),
            func.sum(case((keyword_match, 1), else_=0)),
            func.sum(case((or_(status_match, keyword_match), 1), else_=0)),
        ).one()
