"""供应商主数据及其价格反向汇总。"""

from sqlalchemy import distinct, func

from database.base import db
from database.models.product.import_raw import ImportProductRaw
from database.models.product.material_supplier import MaterialSupplier
from database.models.rd.cost import CostBomNode, CostMaterialPrice


class MaterialSupplierRepository:
    @staticmethod
    def all():
        return MaterialSupplier.query.order_by(MaterialSupplier.name.asc()).all()

    @staticmethod
    def get(supplier_id):
        return db.session.get(MaterialSupplier, supplier_id)

    @staticmethod
    def by_name(name):
        return MaterialSupplier.query.filter_by(name=name).first()

    @staticmethod
    def summary():
        node_code = CostBomNode.code_with_version
        if db.session.get_bind().dialect.name == 'mysql':
            node_code = node_code.collate('utf8mb4_0900_ai_ci')
        return db.session.query(
            CostMaterialPrice.supplier_id,
            func.count(distinct(CostBomNode.id)).label('material_count'),
            func.group_concat(distinct(ImportProductRaw.group_code)).label('group_codes'),
            func.count(distinct(ImportProductRaw.group_code)).label('group_count'),
            func.max(CostMaterialPrice.price_date).label('last_quote_date'),
        ).join(CostBomNode, CostBomNode.id == CostMaterialPrice.node_id).outerjoin(
            ImportProductRaw, ImportProductRaw.code == node_code,
        ).filter(CostMaterialPrice.supplier_id.is_not(None)).group_by(
            CostMaterialPrice.supplier_id
        ).all()

    @staticmethod
    def group_names(codes):
        if not codes:
            return {}
        rows = db.session.query(
            ImportProductRaw.group_code, func.min(ImportProductRaw.group_name),
        ).filter(ImportProductRaw.group_code.in_(codes)).group_by(
            ImportProductRaw.group_code
        ).all()
        return {code: name for code, name in rows}

    @staticmethod
    def materials(supplier_id):
        node_code = CostBomNode.code_with_version
        if db.session.get_bind().dialect.name == 'mysql':
            node_code = node_code.collate('utf8mb4_0900_ai_ci')
        return db.session.query(
            CostBomNode.id.label('node_id'), CostBomNode.code_with_version.label('code'),
            ImportProductRaw.name, ImportProductRaw.group_code, ImportProductRaw.group_name,
            CostMaterialPrice.unit_price, CostMaterialPrice.price_date,
            CostMaterialPrice.created_at,
        ).join(CostBomNode, CostBomNode.id == CostMaterialPrice.node_id).outerjoin(
            ImportProductRaw, ImportProductRaw.code == node_code,
        ).filter(CostMaterialPrice.supplier_id == supplier_id).order_by(
            CostBomNode.id, CostMaterialPrice.price_date.desc(),
            CostMaterialPrice.created_at.desc(), CostMaterialPrice.id.desc(),
        ).all()

    @staticmethod
    def price_count(supplier_id):
        return CostMaterialPrice.query.filter_by(supplier_id=supplier_id).count()

    @staticmethod
    def save(row, values):
        if row is None:
            row = MaterialSupplier()
            db.session.add(row)
        old_name = row.name
        for key, value in values.items():
            setattr(row, key, value)
        db.session.flush()
        if old_name and old_name != row.name:
            CostMaterialPrice.query.filter_by(supplier_id=row.id).update(
                {'supplier_name': row.name}, synchronize_session=False,
            )
        db.session.commit()
        return row

    @staticmethod
    def delete(row):
        db.session.delete(row)
        db.session.commit()
