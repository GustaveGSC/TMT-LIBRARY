"""供应商主数据管理与自由文本自动登记。"""

from sqlalchemy.exc import IntegrityError

from database.base import db
from database.models.product.material_supplier import MaterialSupplier
from database.repository.product.material_supplier import MaterialSupplierRepository
from result import Result

_GROUP_LIMIT = 20


class MaterialSupplierService:
    @staticmethod
    def _text(value, maximum, label, required=False):
        if value is None:
            value = ''
        if not isinstance(value, str):
            raise ValueError(f'{label}格式无效')
        value = value.strip()
        if required and not value:
            raise ValueError(f'{label}不能为空')
        if len(value) > maximum:
            raise ValueError(f'{label}不能超过 {maximum} 个字符')
        return value or None

    def list(self):
        rows = MaterialSupplierRepository.all()
        summaries = {row.supplier_id: row for row in MaterialSupplierRepository.summary()}
        parsed = {}
        all_codes = set()
        for supplier_id, summary in summaries.items():
            codes = sorted(set((summary.group_codes or '').split(','))) if summary.group_codes else []
            codes = [code for code in codes if code][:_GROUP_LIMIT]
            parsed[supplier_id] = codes
            all_codes.update(codes)
        names = MaterialSupplierRepository.group_names(all_codes)
        data = []
        for row in rows:
            item = row.to_dict()
            summary = summaries.get(row.id)
            codes = parsed.get(row.id, [])
            group_count = int(summary.group_count or 0) if summary else 0
            item.update({
                'material_count': int(summary.material_count or 0) if summary else 0,
                'group_codes': codes,
                'groups': [{'code': code, 'name': names.get(code) or ''} for code in codes],
                'group_count': group_count,
                'groups_truncated': group_count > len(codes),
                'last_quote_date': summary.last_quote_date.strftime('%Y-%m-%d')
                if summary and summary.last_quote_date else '',
            })
            data.append(item)
        return Result.ok(data={'items': data, 'total': len(data)})

    @staticmethod
    def options():
        return Result.ok(data=[{'id': row.id, 'name': row.name}
                               for row in MaterialSupplierRepository.all()])

    @staticmethod
    def materials(supplier_id):
        if not MaterialSupplierRepository.get(supplier_id):
            return Result.fail('供应商不存在')
        result, seen = [], set()
        for row in MaterialSupplierRepository.materials(supplier_id):
            if row.node_id in seen:
                continue
            seen.add(row.node_id)
            result.append({
                'code': row.code or '', 'name': row.name or '',
                'group_code': row.group_code or '', 'group_name': row.group_name or '',
                'unit_price': float(row.unit_price),
                'price_date': row.price_date.strftime('%Y-%m-%d') if row.price_date else '',
            })
        return Result.ok(data=result)

    def create(self, body, username):
        if not isinstance(body, dict):
            return Result.fail('请求体格式无效')
        try:
            values = {
                'name': self._text(body.get('name'), 64, '供应商名称', True),
                'contact': self._text(body.get('contact'), 64, '联系方式'),
                'remark': self._text(body.get('remark'), 65535, '备注'),
                'created_by': (username or '')[:64] or None,
            }
            return Result.ok(data=MaterialSupplierRepository.save(None, values).to_dict())
        except ValueError as exc:
            return Result.fail(str(exc))
        except IntegrityError:
            db.session.rollback()
            return Result.fail('供应商名称已存在')

    def update(self, supplier_id, body):
        if not isinstance(body, dict):
            return Result.fail('请求体格式无效')
        row = MaterialSupplierRepository.get(supplier_id)
        if not row:
            return Result.fail('供应商不存在')
        try:
            values = {}
            for key, maximum, label, required in (
                ('name', 64, '供应商名称', True), ('contact', 64, '联系方式', False),
                ('remark', 65535, '备注', False),
            ):
                if key in body:
                    values[key] = self._text(body.get(key), maximum, label, required)
            return Result.ok(data=MaterialSupplierRepository.save(row, values).to_dict())
        except ValueError as exc:
            db.session.rollback()
            return Result.fail(str(exc))
        except IntegrityError:
            db.session.rollback()
            return Result.fail('供应商名称已存在')

    @staticmethod
    def delete(supplier_id, force=False):
        row = MaterialSupplierRepository.get(supplier_id)
        if not row:
            return Result.fail('供应商不存在')
        count = MaterialSupplierRepository.price_count(supplier_id)
        if count and not force:
            return Result.fail(
                f'该供应商仍关联 {count} 条价格记录，删除后这些记录将保留但不再归属任何供应商',
                data={'price_count': count},
            )
        MaterialSupplierRepository.delete(row)
        return Result.ok(data={'price_count': count})

    @staticmethod
    def resolve(supplier_id=None, supplier_name=None, username=None):
        if supplier_id not in (None, ''):
            try:
                supplier_id = int(supplier_id)
            except (TypeError, ValueError):
                raise ValueError('supplier_id 格式无效')
            row = MaterialSupplierRepository.get(supplier_id)
            if not row:
                raise ValueError('供应商不存在')
            return row
        if supplier_name is not None and not isinstance(supplier_name, str):
            raise ValueError('供应商名称格式无效')
        name = (supplier_name or '').strip()
        if not name:
            return None
        if len(name) > 64:
            raise ValueError('供应商名称不能超过 64 个字符')
        row = MaterialSupplierRepository.by_name(name)
        if row:
            return row
        try:
            with db.session.begin_nested():
                row = MaterialSupplier(name=name, created_by=(username or '')[:64] or None)
                db.session.add(row)
                db.session.flush()
            return row
        except IntegrityError:
            return MaterialSupplierRepository.by_name(name)


material_supplier_service = MaterialSupplierService()
