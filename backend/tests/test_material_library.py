import io

import openpyxl
import pytest
from flask import Flask
from sqlalchemy import event
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateTable

from auth import generate_token
from database.base import db
from database.models.product.erp_code_rules import ErpCodeRule
import database.models.product.category  # noqa: F401
from database.models.product.finished import ProductFinished
import database.models.product.resource  # noqa: F401
from database.models.product.import_raw import ImportProductRaw
from database.models.product.material import (
    ErpGroupCategory, MaterialBom, MaterialBomLine, MaterialDisableKeyword, MaterialImage,
    ProductMaterial,
)
from database.repository.account import UserRepository
from routes.product.import_raw import _parse_excel
from routes.product.material import material_bp
from services.product.import_raw import import_product_service
from services.product.material_filter import FilterExpressionError, parse_filter_expression
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
        'code': '14WD001', 'name': '桌面板', 'spec': '1.2米', 'status': None,
        'group_code': '14WD', 'group_name': '原材料_木器',
    }]


def test_product_import_accepts_real_erp_headers():
    data = _workbook(
        ['品号', '品名', '规格', '单位名称', '品号群组', '群组名称', '状态'],
        ['14WD001', '桌面板', '1.2米', 'PCS', '14WD', '原材料_木器', '失效'],
    )
    assert _parse_excel(data)[0]['group_code'] == '14WD'
    assert _parse_excel(data)[0]['status'] == '失效'


def test_product_import_rejects_missing_required_headers():
    data = _workbook(['品号', '品名', '单位'], ['14WD001', '桌面板', 'PCS'])
    with pytest.raises(UploadValidationError, match='分组编码'):
        _parse_excel(data)


def test_material_routes_accept_codes_containing_slash():
    app = Flask(__name__)
    app.register_blueprint(material_bp, url_prefix='/api/material')
    routes = app.url_map.bind('localhost')
    assert routes.match('/api/material/items/A/B')[1] == {'code': 'A/B'}
    assert routes.match('/api/material/items/A/B/images', method='POST')[1] == {'code': 'A/B'}
    assert routes.match('/api/material/items/A/B/images/7', method='PUT') == (
        'material.replace_material_image', {'code': 'A/B', 'image_id': 7})
    assert routes.match('/api/material/items/A/B/images/7', method='DELETE') == (
        'material.delete_material_image', {'code': 'A/B', 'image_id': 7})
    # 保存物料属性的 PUT 不能吞掉图片子路由
    assert routes.match('/api/material/items/A/B', method='PUT')[0] == 'material.save_material'


def test_material_join_keys_declare_mysql_0900_collation():
    material_ddl = str(CreateTable(ProductMaterial.__table__).compile(dialect=mysql.dialect()))
    group_ddl = str(CreateTable(ErpGroupCategory.__table__).compile(dialect=mysql.dialect()))
    assert 'code VARCHAR(255) COLLATE utf8mb4_0900_ai_ci' in material_ddl
    assert 'group_code VARCHAR(64) COLLATE utf8mb4_0900_ai_ci' in group_ddl


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
        MaterialImage.__table__,
        ProductFinished.__table__,
        MaterialBom.__table__,
        MaterialBomLine.__table__,
        MaterialDisableKeyword.__table__,
    ]
    with app.app_context():
        db.metadata.create_all(bind=db.engine, tables=material_tables)
        material_service.invalidate_rule_cache()
        material_service.invalidate_disable_keyword_cache()
        material_service.invalidate_group_config_cache()
        material_service.invalidate_override_cache()
        yield app
        db.session.remove()
        material_service.invalidate_rule_cache()
        material_service.invalidate_disable_keyword_cache()
        material_service.invalidate_group_config_cache()
        material_service.invalidate_override_cache()
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
        saved = material_service.save_item('14WD001', {'remark': '桌面'})
        assert saved.success and ProductMaterial.query.count() == 1
        assert material_service.list_items(1, 20, is_disabled=False).data['total'] == 1
        assert material_service.list_items(1, 20, is_disabled=True).data['total'] == 0


def test_material_disabled_is_readonly_and_ignores_legacy_override_input(material_app):
    with material_app.app_context():
        db.session.add_all([
            ImportProductRaw(
                code='A1', name='测试物料', raw_name='测试物料（已停用）',
                status='生效', group_code='G', group_name='组',
                imported_at=now_cst(),
            ),
            MaterialDisableKeyword(keyword='停用', is_disabled=False),
        ])
        db.session.commit()
        material_service.invalidate_disable_keyword_cache()
        assert material_service.detail('A1').data['is_disabled'] is True
        saved = material_service.save_item('A1', {
            'remark': '测试备注', 'is_disabled': False,
        })
        row = ProductMaterial.query.filter_by(code='A1').one()
        assert row.is_disabled is None
        assert saved.data['is_disabled'] is True
        assert 'is_disabled_override' not in saved.data


def test_disable_preview_uses_union_not_sum(material_app):
    with material_app.app_context():
        db.session.add_all([
            ImportProductRaw(code='A', name='已停用', status='失效',
                             group_code='G', group_name='组', imported_at=now_cst()),
            ImportProductRaw(code='B', name='已停用', status='生效',
                             group_code='G', group_name='组', imported_at=now_cst()),
            ImportProductRaw(code='C', name='正常', status='失效',
                             group_code='G', group_name='组', imported_at=now_cst()),
            MaterialDisableKeyword(keyword='停用', is_disabled=False),
        ])
        db.session.commit()
        material_service.invalidate_disable_keyword_cache()
        assert material_service.disable_preview().data == {
            'status_inactive': 2, 'keyword_hit': 2, 'union': 3,
        }


def test_default_list_only_loads_manual_rows_for_current_page(material_app, monkeypatch):
    with material_app.app_context():
        db.session.add_all([
            ImportProductRaw(
                code=f'C{i:03d}', name=f'物料{i}', group_code='G', group_name='组',
                imported_at=now_cst(),
            )
            for i in range(25)
        ])
        db.session.commit()
        seen = []
        from database.repository.product.material import MaterialRepository
        real_method = MaterialRepository.materials_for_codes

        def capture(codes):
            seen.append(list(codes))
            return real_method(codes)

        monkeypatch.setattr(MaterialRepository, 'materials_for_codes', capture)
        result = material_service.list_items(2, 10, is_disabled=False)
        assert result.data['total'] == 25
        assert len(result.data['items']) == 10
        assert seen == [[f'C{i:03d}' for i in range(10, 20)]]


def test_material_list_column_filters_and_name_sort(material_app):
    with material_app.app_context():
        db.session.add_all([
            ImportProductRaw(code='A', name='甲物料', group_code='G', group_name='组',
                             imported_at=now_cst()),
            ImportProductRaw(code='B', name='乙物料', group_code='G', group_name='组',
                             imported_at=now_cst()),
            ImportProductRaw(code='C', name='丙物料', group_code='G', group_name='组',
                             imported_at=now_cst()),
            ErpGroupCategory(group_code='G', is_material=True),
        ])
        db.session.commit()

        desc = material_service.list_items(
            1, 20, sort_by='code', sort_dir='desc', is_disabled=False,
        ).data['items']
        filtered = material_service.list_items(
            1, 20, code='B', name='乙', is_disabled=False,
        ).data['items']
        category_sorted = material_service.list_items(
            1, 20, category='material', sort_by='code', sort_dir='desc',
            is_disabled=False,
        ).data['items']

        assert [item['code'] for item in desc] == ['C', 'B', 'A']
        assert [item['code'] for item in filtered] == ['B']
        assert [item['code'] for item in category_sorted] == ['C', 'B', 'A']
        # 简称/分类已删列，列表项不再带这两个字段；规格直接取 ERP
        assert 'short_name' not in desc[0] and 'category' not in desc[0]


def test_material_list_exclude_useless_hides_only_useless_items(material_app):
    with material_app.app_context():
        db.session.add_all([
            ImportProductRaw(code='U1', name='无用件', group_code='G', group_name='组',
                             imported_at=now_cst()),
            ImportProductRaw(code='M1', name='原材料件', group_code='G', group_name='组',
                             imported_at=now_cst()),
            ErpCodeRule(prefix='U', type='useless', is_disabled=False),
            ErpCodeRule(prefix='M', type='material', is_disabled=False),
        ])
        db.session.commit()

        plain = material_service.list_items(1, 20, is_disabled=False).data['items']
        excluded = material_service.list_items(
            1, 20, is_disabled=False, exclude_useless=True,
        ).data['items']

        assert {item['code'] for item in plain} == {'U1', 'M1'}
        assert {item['code'] for item in excluded} == {'M1'}


def test_material_type_priority_manual_over_rule_over_group(material_app):
    with material_app.app_context():
        db.session.add_all([
            ImportProductRaw(code='R1', name='规则命中', group_code='G', group_name='组',
                             imported_at=now_cst()),
            ImportProductRaw(code='X1', name='走分组默认', group_code='G', group_name='组',
                             imported_at=now_cst()),
            ErpCodeRule(prefix='R', type='finished', is_disabled=False),
            ErpGroupCategory(group_code='G', is_material=True),
        ])
        db.session.commit()

        assert material_service.detail('R1').data['categories'] == ['finished']
        assert material_service.detail('R1').data['category_source'] == 'rule'
        assert material_service.detail('X1').data['categories'] == ['material']
        assert material_service.detail('X1').data['category_source'] == 'group'

        # 单独指定优先级最高，同时压过前缀规则和分组默认
        saved = material_service.save_item('R1', {'type_override': ['useless']}).data
        assert saved['categories'] == ['useless']
        assert saved['category_source'] == 'manual'
        assert saved['type_override'] == ['useless']
        assert saved['rule_categories'] == ['finished']
        assert saved['rule_source'] == 'rule'

        listed = material_service.list_items(
            1, 20, is_disabled=False, exclude_useless=True,
        ).data['items']
        assert [item['code'] for item in listed] == ['X1']

        groups = {g['group_code']: g for g in material_service.group_categories().data}
        assert groups['G']['material_count'] == 2
        assert groups['G']['manual_count'] == 1
        assert groups['G']['rule_count'] == 0

        # 空列表 = 取消单独指定，恢复规则判定
        cleared = material_service.save_item('R1', {'type_override': []}).data
        assert cleared['categories'] == ['finished']
        assert cleared['category_source'] == 'rule'
        assert cleared['type_override'] == []

        assert not material_service.save_item('R1', {'type_override': ['bogus']}).success


def test_material_images_add_replace_delete_keep_order(material_app):
    with material_app.app_context():
        db.session.add(ImportProductRaw(code='P1', name='件', group_code='G', group_name='组',
                                        imported_at=now_cst()))
        db.session.commit()

        assert material_service.detail('P1').data['images'] == []
        material_service.add_image('P1', 'u1', None, 'tester')
        images = material_service.add_image('P1', 'u2', 'o2', 'tester').data
        assert [i['url'] for i in images] == ['u1', 'u2']
        assert [i['sort_order'] for i in images] == [0, 1]

        first_id, second_id = images[0]['id'], images[1]['id']
        replaced = material_service.replace_image('P1', first_id, 'u1b', 'o1b').data
        assert [(i['id'], i['url'], i['orig_url']) for i in replaced] == [
            (first_id, 'u1b', 'o1b'), (second_id, 'u2', 'o2'),
        ]

        remaining = material_service.delete_image('P1', first_id).data
        assert [i['url'] for i in remaining] == ['u2']
        assert material_service.detail('P1').data['images'] == remaining

        # 图片 id 必须属于该物料，不能跨物料删改
        assert not material_service.delete_image('OTHER', second_id).success
        assert not material_service.add_image('NOPE', 'u', None, 'tester').success


def test_material_type_filter_cache_refreshes_on_rule_group_and_import(material_app):
    from services.product.erp_code_rules import erp_code_rule_service
    with material_app.app_context():
        db.session.add_all([
            ImportProductRaw(code='K1', name='保留', group_code='G', group_name='组',
                             imported_at=now_cst()),
            ImportProductRaw(code='U1', name='无用', group_code='G', group_name='组',
                             imported_at=now_cst()),
        ])
        db.session.commit()

        def visible():
            data = material_service.list_items(1, 20, is_disabled=False, exclude_useless=True).data
            assert data['total'] == len(data['items'])
            return sorted(item['code'] for item in data['items'])

        assert visible() == ['K1', 'U1']
        # 新增前缀规则 -> 缓存失效，U1 立即被排除
        assert erp_code_rule_service.create('U', 'useless').success
        assert visible() == ['K1']
        # 分组默认改成无用 -> K1 也被排除（U1 仍由前缀规则判定）
        assert material_service.save_group('G', {'is_useless': True}).success
        assert visible() == []
        assert material_service.save_group('G', {'is_material': True}).success
        assert visible() == ['K1']
        # ERP 导入新编码 -> 缓存失效，新编码按分组默认出现
        import_product_service.import_rows([{
            'code': 'K2', 'name': '新导入', 'group_code': 'G', 'group_name': '组',
        }])
        assert visible() == ['K1', 'K2']
        groups = {g['group_code']: g for g in material_service.group_categories().data}
        assert groups['G']['material_count'] == 3
        assert groups['G']['rule_count'] == 1


def test_material_category_filter_uses_database_sort_and_paging(material_app):
    with material_app.app_context():
        db.session.add_all([
            ImportProductRaw(code=f'M{i:02d}', name=f'料{i}', group_code='G', group_name='组',
                             imported_at=now_cst())
            for i in range(30)
        ] + [
            ImportProductRaw(code='X01', name='成品', group_code='F', group_name='成品组',
                             imported_at=now_cst()),
            ErpGroupCategory(group_code='G', is_material=True),
            ErpGroupCategory(group_code='F', is_finished=True),
        ])
        db.session.commit()
        page2 = material_service.list_items(
            2, 10, is_disabled=False, category='material', sort_by='code', sort_dir='desc',
        ).data
        assert page2['total'] == 30
        assert [item['code'] for item in page2['items']] == [f'M{i:02d}' for i in range(19, 9, -1)]
        only_finished = material_service.list_items(1, 50, is_disabled=False, category='finished').data
        assert [item['code'] for item in only_finished['items']] == ['X01']


def test_material_route_rejects_invalid_sort_field(material_app, monkeypatch):
    material_app.register_blueprint(material_bp, url_prefix='/api/material')
    monkeypatch.setattr(UserRepository, 'get_auth_state', lambda _id: (True, 0))
    client = material_app.test_client()
    viewer = {
        'id': 1, 'username': 'viewer', 'roles': [],
        'permissions': ['material:view'], 'token_version': 0,
    }
    client.set_cookie('tmt_session', generate_token(viewer, csrf_token='csrf'))
    response = client.get('/api/material/items?sort_by=code;DROP TABLE product_material')
    assert response.status_code == 400
    assert response.get_json()['message'] == '排序字段无效'


def test_default_sorted_list_keeps_four_business_queries_when_caches_are_warm(material_app):
    with material_app.app_context():
        db.session.add_all([
            ImportProductRaw(code='A', name='甲', group_code='G', group_name='组',
                             imported_at=now_cst()),
            ProductMaterial(code='A', remark='备注'),
        ])
        db.session.commit()
        material_service._rules()
        material_service._disable_keywords()
        material_service._group_configs()
        material_service._overrides()
        statements = []

        def capture(_conn, _cursor, statement, _parameters, _context, _executemany):
            if statement.lstrip().upper().startswith('SELECT'):
                statements.append(statement)

        event.listen(db.engine, 'before_cursor_execute', capture)
        try:
            material_service.list_items(
                1, 50, code='A', sort_by='name',
                sort_dir='asc', is_disabled=False,
            )
        finally:
            event.remove(db.engine, 'before_cursor_execute', capture)

        # 计数、当前页、人工维护字段、当前页的研发 BOM 标记
        assert len(statements) == 4


def test_material_expression_filters_and_literal_like_escaping(material_app):
    with material_app.app_context():
        db.session.add_all([
            ImportProductRaw(code='MJ120_A', name='红色桌腿', group_code='14ME', group_name='金属',
                             imported_at=now_cst()),
            ImportProductRaw(code='MJ120XA', name='黑色桌腿', group_code='14ME', group_name='金属',
                             imported_at=now_cst()),
            ImportProductRaw(code='14WD001', name='桌面 (V1.1)', group_code='14WD', group_name='木器',
                             imported_at=now_cst()),
        ])
        db.session.commit()
        expression = material_service.list_items(
            1, 20, name='桌腿 & !红色', match_mode='expr', is_disabled=False,
        ).data['items']
        grouped = material_service.list_items(
            1, 20, name='(桌腿 | 桌面) & !红色', match_mode='expr', is_disabled=False,
        ).data['items']
        quoted = material_service.list_items(
            1, 20, name='"(V1.1)"', match_mode='expr', is_disabled=False,
        ).data['items']
        escaped_like = material_service.list_items(
            1, 20, code='MJ120_A', match_mode='like', is_disabled=False,
        ).data['items']
        single_expr = material_service.list_items(
            1, 20, name='桌腿', match_mode='expr', is_disabled=False,
        ).data['items']
        single_like = material_service.list_items(
            1, 20, name='桌腿', match_mode='like', is_disabled=False,
        ).data['items']
        assert [item['code'] for item in expression] == ['MJ120XA']
        assert [item['code'] for item in grouped] == ['14WD001', 'MJ120XA']
        assert [item['code'] for item in quoted] == ['14WD001']
        assert [item['code'] for item in escaped_like] == ['MJ120_A']
        assert [item['code'] for item in single_expr] == [item['code'] for item in single_like]


@pytest.mark.parametrize(('expression', 'message'), [
    ('(桌腿', '括号不匹配'),
    ('桌腿)', '括号不匹配'),
    ('桌腿 &', '缺少操作数'),
    ('& 桌腿', '缺少操作数'),
    ('!', '缺少操作数'),
    ('""', '操作数不能为空'),
    ('   ', '操作数不能为空'),
    ('"桌腿', '引号不匹配'),
])
def test_material_expression_parser_errors(expression, message):
    with pytest.raises(FilterExpressionError, match=message):
        parse_filter_expression(expression)


def test_material_expression_complexity_limits():
    with pytest.raises(FilterExpressionError, match='表达式过于复杂'):
        parse_filter_expression('(' * 11 + 'A' + ')' * 11)
    with pytest.raises(FilterExpressionError, match='表达式过于复杂'):
        parse_filter_expression(' | '.join(f'A{i}' for i in range(30)))


def test_material_route_returns_expression_error_as_400(material_app, monkeypatch):
    material_app.register_blueprint(material_bp, url_prefix='/api/material')
    monkeypatch.setattr(UserRepository, 'get_auth_state', lambda _id: (True, 0))
    client = material_app.test_client()
    viewer = {
        'id': 1, 'username': 'viewer', 'roles': [],
        'permissions': ['material:view'], 'token_version': 0,
    }
    client.set_cookie('tmt_session', generate_token(viewer, csrf_token='csrf'))
    response = client.get(
        '/api/material/items', query_string={'match_mode': 'expr', 'code': '(桌腿'},
    )
    assert response.status_code == 400
    assert response.get_json()['message'] == '括号不匹配'


def test_material_detail_reuses_product_library_cover(material_app):
    with material_app.app_context():
        for code in ('F1', 'F2', 'M1'):
            db.session.add(ImportProductRaw(code=code, name='件', group_code='G', group_name='组',
                                            imported_at=now_cst()))
        db.session.add(ProductFinished(code='F1', cover_image='thumb.png',
                                       cover_image_original='orig.png'))
        db.session.add(ProductFinished(code='F2'))
        db.session.commit()

        assert material_service.detail('F1').data['product_images'] == [
            {'url': 'thumb.png', 'orig_url': 'orig.png'},
        ]
        # 产品库图片不进 material_image，也不影响物料自己的图片列表
        assert material_service.detail('F1').data['images'] == []
        assert material_service.detail('F2').data['product_images'] == []
        assert material_service.detail('M1').data['product_images'] == []
