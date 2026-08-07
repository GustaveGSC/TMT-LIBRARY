"""物料库对研发 BOM 成本节点与价格的访问适配。"""

from sqlalchemy import or_

from database.base import db
from database.models.rd.cost import (
    CostBomLine, CostBomNode, CostMaterialPrice, CostSnapshot, CostSnapshotSku,
)


class MaterialPriceRepository:
    @staticmethod
    def node_for_code(code_with_version, base_code):
        return CostBomNode.query.filter(or_(
            CostBomNode.code_with_version == code_with_version,
            CostBomNode.code == base_code,
        )).order_by(
            (CostBomNode.code_with_version == code_with_version).desc(),
            CostBomNode.id.asc(),
        ).first()

    @staticmethod
    def latest_for_codes(codes, base_codes):
        if not codes:
            return {}
        rows = db.session.query(
            CostBomNode.id, CostBomNode.code, CostBomNode.code_with_version,
            CostBomNode.notes, CostBomNode.is_purchased_semi, CostBomNode.node_type,
            CostMaterialPrice.unit_price, CostMaterialPrice.source,
        ).join(
            CostMaterialPrice, CostMaterialPrice.node_id == CostBomNode.id,
        ).filter(or_(
            CostBomNode.code_with_version.in_(codes),
            CostBomNode.code.in_(base_codes),
        )).order_by(
            CostBomNode.id.asc(), CostMaterialPrice.price_date.desc(),
            CostMaterialPrice.created_at.desc(), CostMaterialPrice.id.desc(),
        ).all()
        latest_by_node = {}
        node_by_exact, node_by_base = {}, {}
        for row in rows:
            node_by_base.setdefault(row.code, row)
            if row.code_with_version:
                node_by_exact.setdefault(row.code_with_version, row)
            latest_by_node.setdefault(row.id, row)
        result = {}
        for code, base in zip(codes, base_codes):
            node = node_by_exact.get(code) or node_by_base.get(base)
            if not node:
                continue
            latest = latest_by_node[node.id]
            result[code] = {
                'cost_node_id': node.id,
                'latest_price': float(latest.unit_price),
                'latest_price_source': latest.source,
                'cost_notes': node.notes or '',
                'is_purchased_semi': bool(node.is_purchased_semi),
                'cost_node_type': node.node_type,
            }
        return result

    @staticmethod
    def prices(node_id):
        return CostMaterialPrice.query.filter_by(node_id=node_id).order_by(
            CostMaterialPrice.price_date.desc(), CostMaterialPrice.created_at.desc(),
            CostMaterialPrice.id.desc(),
        ).all()

    @staticmethod
    def snapshot_order_map(snapshot_ids):
        if not snapshot_ids:
            return {}
        rows = db.session.query(CostSnapshot.id, CostSnapshot.order_no).filter(
            CostSnapshot.id.in_(snapshot_ids)
        ).all()
        return {row.id: row.order_no or '' for row in rows}

    @staticmethod
    def usages(node_id):
        return db.session.query(
            CostBomLine.unit_price, CostBomLine.quantity,
            CostSnapshotSku.finished_code, CostSnapshotSku.finished_name,
            CostSnapshotSku.id.label('sku_id'), CostSnapshot.order_no,
            CostSnapshot.snapshot_date, CostSnapshot.id.label('snapshot_id'),
        ).join(
            CostSnapshotSku, CostBomLine.sku_id == CostSnapshotSku.id,
        ).join(
            CostSnapshot, CostSnapshotSku.snapshot_id == CostSnapshot.id,
        ).filter(CostBomLine.child_node_id == node_id).order_by(
            CostSnapshot.snapshot_date.desc(), CostSnapshot.id.desc(),
        ).all()

    @staticmethod
    def add_price(node, price):
        db.session.add(node)
        db.session.flush()
        price.node_id = node.id
        db.session.add(price)
        db.session.commit()
        return price

    @staticmethod
    def price(price_id):
        return db.session.get(CostMaterialPrice, price_id)

    @staticmethod
    def commit():
        db.session.commit()

    @staticmethod
    def delete_price(price):
        db.session.delete(price)
        db.session.commit()
