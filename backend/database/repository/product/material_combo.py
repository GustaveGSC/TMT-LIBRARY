"""售后物料组合的数据访问。"""

from sqlalchemy import exists, func, or_

from database.base import db
from database.models.product.import_raw import ImportProductRaw
from database.models.product.material import MaterialDisableKeyword, ProductMaterial
from database.models.product.material_combo import MaterialCombo, MaterialComboItem


class MaterialComboRepository:
    @staticmethod
    def list_combos(keyword=None, category=None, is_disabled=None):
        query = MaterialCombo.query
        if keyword:
            query = query.filter(MaterialCombo.name.contains(keyword))
        if category:
            query = query.filter(MaterialCombo.category == category)
        if is_disabled is not None:
            query = query.filter(MaterialCombo.is_disabled == is_disabled)
        return query.order_by(
            MaterialCombo.sort_order.asc(), MaterialCombo.name.asc(), MaterialCombo.id.asc(),
        ).all()

    @staticmethod
    def get(combo_id):
        return db.session.get(MaterialCombo, combo_id)

    @staticmethod
    def items_for_combos(combo_ids):
        if not combo_ids:
            return []
        return MaterialComboItem.query.filter(
            MaterialComboItem.combo_id.in_(combo_ids)
        ).order_by(
            MaterialComboItem.combo_id.asc(), MaterialComboItem.sort_order.asc(),
            MaterialComboItem.id.asc(),
        ).all()

    @staticmethod
    def material_details(codes):
        if not codes:
            return {}
        source_name = func.coalesce(ImportProductRaw.raw_name, ImportProductRaw.name)
        keyword_hit = exists().where(
            MaterialDisableKeyword.is_disabled.is_(False),
            func.instr(source_name, MaterialDisableKeyword.keyword) > 0,
        )
        effective_disabled = or_(
            ImportProductRaw.status == '失效', keyword_hit,
        ).label('is_disabled')
        rows = db.session.query(
            ImportProductRaw.code, ImportProductRaw.name, ImportProductRaw.group_name,
            ProductMaterial.short_name, effective_disabled,
        ).outerjoin(
            ProductMaterial, ProductMaterial.code == ImportProductRaw.code,
        ).filter(ImportProductRaw.code.in_(codes)).all()
        return {
            row.code: {
                'material_name': row.name, 'short_name': row.short_name,
                'group_name': row.group_name, 'is_missing': False,
                'is_disabled': bool(row.is_disabled),
            }
            for row in rows
        }

    @staticmethod
    def save(combo, values, items):
        if combo is None:
            combo = MaterialCombo()
            db.session.add(combo)
        for key, value in values.items():
            setattr(combo, key, value)
        db.session.flush()
        MaterialComboItem.query.filter_by(combo_id=combo.id).delete(
            synchronize_session=False
        )
        db.session.add_all([
            MaterialComboItem(combo_id=combo.id, **item) for item in items
        ])
        db.session.commit()
        return combo

    @staticmethod
    def delete(combo):
        db.session.delete(combo)
        db.session.commit()

    @staticmethod
    def categories():
        return [
            value for value, in db.session.query(MaterialCombo.category).filter(
                MaterialCombo.category.is_not(None), MaterialCombo.category != '',
            ).distinct().order_by(MaterialCombo.category.asc()).all()
        ]
