import io

import openpyxl
import pytest
from flask import Flask

from database.base import db
from database.models.product.erp_code_rules import ErpCodeRule
import database.models.product.category  # noqa: F401
import database.models.product.finished  # noqa: F401
import database.models.product.resource  # noqa: F401
from database.models.product.import_raw import ImportProductRaw
from database.models.product.material import ErpGroupCategory, ProductMaterial
from routes.product.import_raw import _parse_excel
from services.product.import_raw import import_product_service
from services.product.material import material_service
from upload_validation import UploadValidationError
from utils import now_cst


def _workbook(headers, row):
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(headers)
    sheet.append(row)
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


def test_product_import_maps_columns_by_header_name():
    data = _workbook(
        ['单位', '分组名称', '规格型号', '品号', '分组编码', '品名'],
        ['PCS', '原材料_木器', '1.2米', '14WD001', '14WD', '桌面板'],
    )
    assert _parse_excel(data) == [{
        'code': '14WD001', 'name': '桌面板', 'spec': '1.2米',
        'group_code': '14WD', 'group_name': '原材料_木器',
    }]


def test_product_import_rejects_missing_required_headers():
    data = _workbook(['品号', '品名', '单位'], ['14WD001', '桌面板', 'PCS'])
    with pytest.raises(UploadValidationError, match='分组编码'):
        _parse_excel(data)


def test_product_reimport_updates_changed_erp_fields(material_app):
    with material_app.app_context():
        first = import_product_service.import_rows([{
            'code': '14WD001', 'name': '桌面板', 'spec': '1.2米',
            'group_code': 'PCS', 'group_name': '1509',
        }])
        second = import_product_service.import_rows([{
            'code': '14WD001', 'name': '桌面板', 'spec': '1.4米',
            'group_code': '14WD', 'group_name': '原材料_木器',
        }])
        third = import_product_service.import_rows([{
            'code': '14WD001', 'name': '桌面板', 'spec': '1.4米',
            'group_code': '14WD', 'group_name': '原材料_木器',
        }])
        row = ImportProductRaw.query.filter_by(code='14WD001').one()
        assert first['inserted'] == 1
        assert second['updated'] == 1
        assert third['unchanged'] == 1
        assert (row.group_code, row.group_name, row.spec) == ('14WD', '原材料_木器', '1.4米')


@pytest.fixture()
def material_app():
    app = Flask(__name__)
    app.config.update(SQLALCHEMY_DATABASE_URI='sqlite://', SQLALCHEMY_TRACK_MODIFICATIONS=False)
    db.init_app(app)
    material_tables = [
        ImportProductRaw.__table__,
        ErpCodeRule.__table__,
        ErpGroupCategory.__table__,
        ProductMaterial.__table__,
    ]
    with app.app_context():
        db.metadata.create_all(bind=db.engine, tables=material_tables)
        yield app
        db.session.remove()
        db.metadata.drop_all(bind=db.engine, tables=list(reversed(material_tables)))


def test_material_categories_preserve_multiple_prefix_types(material_app):
    with material_app.app_context():
        db.session.add_all([
            ImportProductRaw(code='1101LA001', name='测试物料', spec=None,
                             group_code='1101', group_name='成品', imported_at=now_cst()),
            ErpCodeRule(prefix='1101', type='finished', is_disabled=False),
            ErpCodeRule(prefix='1101LA', type='packaged', is_disabled=False),
        ])
        db.session.commit()
        material_service.invalidate_rule_cache()

        item = material_service.detail('1101LA001').data
        assert item['categories'] == ['finished', 'packaged']


def test_material_save_is_lazy_and_list_filters_disabled(material_app):
    with material_app.app_context():
        db.session.add(ImportProductRaw(
            code='14WD001', name='桌面板 1.2米', spec='1.2米',
            group_code='14WD', group_name='原材料_木器', imported_at=now_cst(),
        ))
        db.session.add(ErpGroupCategory(group_code='14WD', is_material=True))
        db.session.commit()

        assert ProductMaterial.query.count() == 0
        saved = material_service.save_item('14WD001', {
            'short_name': '桌面', 'is_disabled': True,
        })
        assert saved.success and ProductMaterial.query.count() == 1
        assert material_service.list_items(1, 20, is_disabled=False).data['total'] == 0
        assert material_service.list_items(1, 20, is_disabled=True).data['total'] == 1
