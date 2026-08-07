"""把研发 BOM 的同一份成本价格安全地暴露给物料库。"""

from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy.exc import IntegrityError

from database.base import db
from database.models.rd.cost import CostBomNode, CostMaterialPrice
from database.repository.product.material_price import MaterialPriceRepository
from result import Result
from services.rd.cost_import import _strip_version


class MaterialPriceService:
    @staticmethod
    def _node_type(categories):
        if 'semi' in categories:
            return 'semi'
        if 'finished' in categories or 'packaged' in categories:
            return 'finished'
        return 'material'

    @staticmethod
    def _price_value(value):
        try:
            price = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            raise ValueError('单价格式无效')
        if not price.is_finite() or price <= 0 or price >= Decimal('100000000'):
            raise ValueError('单价必须是大于 0 且小于 100000000 的数字')
        return price

    @staticmethod
    def _optional_text(value, maximum, label):
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError(f'{label}格式无效')
        value = value.strip()
        if len(value) > maximum:
            raise ValueError(f'{label}不能超过 {maximum} 个字符')
        return value or None

    @staticmethod
    def _date(value):
        if not value:
            return None
        if not isinstance(value, str):
            raise ValueError('日期格式错误')
        try:
            return date.fromisoformat(value)
        except ValueError:
            raise ValueError('日期格式错误')

    @staticmethod
    def _node(material):
        code = material['code']
        base_code = _strip_version(code)
        node = MaterialPriceRepository.node_for_code(code, base_code)
        if node:
            return node
        if len(code) > 64 or len(base_code) > 64:
            raise ValueError('物料编码过长，无法创建成本节点')
        return CostBomNode(
            code=base_code, code_with_version=code,
            name=(material.get('name') or '')[:128] or None,
            spec=material.get('spec') or None,
            category=material.get('group_name') or None,
            node_type=MaterialPriceService._node_type(material.get('categories') or []),
        )

    def latest_for_materials(self, codes):
        bases = [_strip_version(code) for code in codes]
        return MaterialPriceRepository.latest_for_codes(codes, bases)

    def detail_fields(self, material):
        code = material['code']
        node = MaterialPriceRepository.node_for_code(code, _strip_version(code))
        if not node:
            return {
                'has_cost_node': False, 'cost_node_id': None,
                'latest_price': None, 'latest_price_source': None,
                'cost_notes': '', 'is_purchased_semi': False,
                'cost_node_type': None,
            }
        latest = self.latest_for_materials([code]).get(code)
        return {
            'has_cost_node': True, 'cost_node_id': node.id,
            'latest_price': latest['latest_price'] if latest else None,
            'latest_price_source': latest['latest_price_source'] if latest else None,
            'cost_notes': node.notes or '',
            'is_purchased_semi': bool(node.is_purchased_semi),
            'cost_node_type': node.node_type,
        }

    def list_prices(self, material):
        node = MaterialPriceRepository.node_for_code(
            material['code'], _strip_version(material['code'])
        )
        if not node:
            return Result.ok(data=[])
        prices = MaterialPriceRepository.prices(node.id)
        order_map = MaterialPriceRepository.snapshot_order_map({
            row.snapshot_id for row in prices if row.snapshot_id
        })
        data = []
        for row in prices:
            item = row.to_dict()
            item['order_no'] = order_map.get(row.snapshot_id, '') if row.snapshot_id else ''
            data.append(item)
        return Result.ok(data=data)

    def add_price(self, material, body, username):
        if not isinstance(body, dict):
            return Result.fail('请求体格式无效')
        try:
            price = CostMaterialPrice(
                unit_price=self._price_value(body.get('unit_price')),
                price_date=self._date(body.get('price_date')),
                supplier_name=self._optional_text(
                    body.get('supplier_name'), 64, '供应商名称'
                ),
                source='manual',
                notes=self._optional_text(body.get('notes'), 65535, '价格备注'),
                created_by=(username or '')[:64] or None,
            )
            node = self._node(material)
            return Result.ok(
                data=MaterialPriceRepository.add_price(node, price).to_dict(),
                message='已添加',
            )
        except ValueError as exc:
            db.session.rollback()
            return Result.fail(str(exc))
        except IntegrityError:
            # 并发或历史版本撞到 cost_bom_node.code UNIQUE 时，复用胜出的节点重试价格写入。
            db.session.rollback()
            node = MaterialPriceRepository.node_for_code(
                material['code'], _strip_version(material['code'])
            )
            if not node:
                return Result.fail('成本节点创建冲突，请重试')
            price.node_id = node.id
            db.session.add(price)
            db.session.commit()
            return Result.ok(data=price.to_dict(), message='已添加')

    def update_price(self, price_id, body):
        if not isinstance(body, dict):
            return Result.fail('请求体格式无效')
        price = MaterialPriceRepository.price(price_id)
        if not price:
            return Result.fail('价格记录不存在')
        try:
            if 'supplier_name' not in body:
                return Result.fail('缺少 supplier_name')
            price.supplier_name = self._optional_text(
                body.get('supplier_name'), 64, '供应商名称'
            )
            MaterialPriceRepository.commit()
            return Result.ok(data=price.to_dict(), message='已更新')
        except ValueError as exc:
            db.session.rollback()
            return Result.fail(str(exc))

    @staticmethod
    def delete_price(price_id):
        price = MaterialPriceRepository.price(price_id)
        if not price:
            return Result.fail('价格记录不存在')
        MaterialPriceRepository.delete_price(price)
        return Result.ok(message='已删除')

    def usages(self, material):
        node = MaterialPriceRepository.node_for_code(
            material['code'], _strip_version(material['code'])
        )
        if not node:
            return Result.ok(data=[])
        data = [{
            'snapshot_id': row.snapshot_id,
            'order_no': row.order_no or '',
            'snapshot_date': row.snapshot_date.strftime('%Y-%m-%d')
            if row.snapshot_date else '',
            'sku_id': row.sku_id,
            'finished_code': row.finished_code,
            'finished_name': row.finished_name or '',
            'unit_price': float(row.unit_price) if row.unit_price is not None else None,
            'quantity': float(row.quantity) if row.quantity is not None else None,
        } for row in MaterialPriceRepository.usages(node.id)]
        return Result.ok(data=data)


material_price_service = MaterialPriceService()
