"""物料 BOM（研发 BOM）：解析、单层拆分、ERP 编码对应、展开与反查。"""
import io

import openpyxl
import pytest
from flask import Flask

from database.base import db
import database.models.product.category  # noqa: F401
import database.models.product.finished  # noqa: F401
import database.models.product.resource  # noqa: F401
from database.models.product.import_raw import ImportProductRaw
from database.models.product.material import MaterialBom, MaterialBomLine
from routes.product.material import material_bp
from services.product.material_bom import (
    build_single_level_boms, material_bom_service, parse_bom_rows,
)
from utils import now_cst


PDM_HEADERS = ['层次', '名称', '一级分类', '二级分类', '三级分类', '物料编码', '版本',
               '数量', '单位', '描述', '规格', '状态']


def _pdm(rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(PDM_HEADERS)
    for level, cat, code, ver, qty, desc in rows:
        ws.append([level, f'{code}.SLDASM', cat, '01_桌类', None, code, ver, qty, 'PCS',
                   desc, None, '已发布'])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


# 成品 F（研发 A01）→ 产成品 P + 螺钉 S×4；产成品 P → 半成品 M ×2；半成品 M → 原材料 R ×3
# 半成品 M 在成品下又直接挂了一次（重复展开只取第一次）
SAMPLE = [
    ('1',       '11_成品',   'F1', 'A01', 1, '书桌'),
    ('1.1',     '12_产成品', 'P1', 'A01', 1, '桌面'),
    ('1.1.1',   '13_半成品', 'M1', 'A01', 2, '钢架'),
    ('1.1.1.1', '14_原材料', 'R1', 'A01', 3, '方管'),
    ('1.2',     '14_原材料', 'S1', 'A01', 4, '螺钉'),
    ('1.3',     '13_半成品', 'M1', 'A01', 1, '钢架'),
    ('1.3.1',   '14_原材料', 'R9', 'A01', 9, '不该出现'),
]


@pytest.fixture
def bom_app():
    app = Flask(__name__)
    app.config.update(SQLALCHEMY_DATABASE_URI='sqlite://', SQLALCHEMY_TRACK_MODIFICATIONS=False)
    db.init_app(app)
    tables = [ImportProductRaw.__table__, MaterialBom.__table__, MaterialBomLine.__table__]
    with app.app_context():
        db.metadata.create_all(bind=db.engine, tables=tables)
        # ERP：成品/产成品只到 -A，半成品/原材料带 -A01；S1 在 ERP 里没有
        for code, name in [('F1-A', 'ERP书桌'), ('P1-A', 'ERP桌面'),
                           ('M1-A01', 'ERP钢架'), ('R1-A01', 'ERP方管')]:
            db.session.add(ImportProductRaw(code=code, name=name, group_code='G',
                                            group_name='组', imported_at=now_cst()))
        db.session.commit()
        yield app
        db.session.remove()
        db.metadata.drop_all(bind=db.engine, tables=list(reversed(tables)))


def test_parse_and_split_single_level():
    rows = parse_bom_rows(_pdm(SAMPLE))
    assert [r['level'] for r in rows] == [s[0] for s in SAMPLE]
    assert rows[0]['category'] == '成品'
    boms = build_single_level_boms(rows)
    assert set(boms) == {('F1', 'A01'), ('P1', 'A01'), ('M1', 'A01')}
    f1 = boms[('F1', 'A01')]['lines']
    assert [(l['code'], l['qty']) for l in f1] == [('P1', 1), ('S1', 4), ('M1', 1)]
    # M1 第二次展开（1.3.1 的 R9）被忽略
    assert [(l['code'], l['qty']) for l in boms[('M1', 'A01')]['lines']] == [('R1', 3)]


def test_import_maps_erp_codes_and_overwrites_same_version(bom_app):
    with bom_app.app_context():
        res = material_bom_service.import_file(_pdm(SAMPLE), 'a.xlsx', 'tester')
        assert res.success, res.message
        assert res.data['created'] == 3 and res.data['updated'] == 0
        assert res.data['roots'] == ['F1-A01']
        assert res.data['unmatched'] == ['R9-A01', 'S1-A01']
        f1 = MaterialBom.query.filter_by(code='F1', version='A01').one()
        assert f1.erp_code == 'F1-A'            # A01 → 退到只有字母的 -A
        m1 = MaterialBom.query.filter_by(code='M1').one()
        assert m1.erp_code == 'M1-A01'          # 半成品完整版本匹配

        # 同一研发版本再导一次：覆盖子件，不新增表头
        changed = [row if row[2] != 'S1' else ('1.2', '14_原材料', 'S1', 'A01', 6, '螺钉')
                   for row in SAMPLE]
        res2 = material_bom_service.import_file(_pdm(changed), 'b.xlsx', 'tester')
        assert res2.data['created'] == 0 and res2.data['updated'] == 3
        assert MaterialBom.query.count() == 3
        s1 = MaterialBomLine.query.filter_by(bom_id=f1.id, code='S1').one()
        assert s1.qty == 6

        # 新研发版本 A02 → 同一个 ERP 物料 F1-A 下多一个版本
        a02 = [(l, c, code, 'A02' if code == 'F1' else v, q, d)
               for l, c, code, v, q, d in SAMPLE]
        material_bom_service.import_file(_pdm(a02), 'c.xlsx', 'tester')
        view = material_bom_service.for_material('F1-A').data
        assert [v['version'] for v in view['versions']] == ['A02', 'A01']
        assert view['selected_id'] == view['versions'][0]['id']


def test_tree_expands_all_levels_with_erp_names(bom_app):
    with bom_app.app_context():
        material_bom_service.import_file(_pdm(SAMPLE), 'a.xlsx', 'tester')
        f1 = MaterialBom.query.filter_by(code='F1').one()
        data = material_bom_service.tree(f1.id).data
        assert data['bom']['name'] == 'ERP书桌'
        top = data['children']
        assert [n['drawing'] for n in top] == ['P1-A01', 'S1-A01', 'M1-A01']
        p1 = top[0]
        assert p1['name'] == 'ERP桌面' and p1['erp_code'] == 'P1-A'
        assert p1['children'][0]['drawing'] == 'M1-A01'
        assert p1['children'][0]['children'][0]['name'] == 'ERP方管'
        assert 'children' not in top[1]          # 螺钉没有下级
        assert top[1]['erp_code'] is None and top[1]['name'] == '螺钉'


def test_where_used_direct_parents_and_top_products(bom_app):
    with bom_app.app_context():
        material_bom_service.import_file(_pdm(SAMPLE), 'a.xlsx', 'tester')
        # 原材料 R1：直接上级 M1，最终产品 F1
        r1 = material_bom_service.for_material('R1-A01').data
        assert r1['versions'] == [] and r1['tree'] == []
        assert [(d['drawing'], d['qty']) for d in r1['direct_parents']] == [('M1-A01', 3)]
        assert [t['drawing'] for t in r1['top_products']] == ['F1-A01']
        # 半成品 M1：直接上级 P1 和 F1（F1 下直接挂了一次），最终产品 F1
        m1 = material_bom_service.for_material('M1-A01').data
        assert sorted(d['drawing'] for d in m1['direct_parents']) == ['F1-A01', 'P1-A01']
        assert [t['drawing'] for t in m1['top_products']] == ['F1-A01']
        assert [n['drawing'] for n in m1['tree']] == ['R1-A01']
        # 顶层成品自己不被任何 BOM 使用
        f1 = material_bom_service.for_material('F1-A').data
        assert f1['direct_parents'] == [] and f1['top_products'] == []
        assert material_bom_service.codes_with_bom(['F1-A', 'R1-A01', 'M1-A01']) == {'F1-A', 'M1-A01'}


def test_import_rejects_unknown_format(bom_app):
    wb = openpyxl.Workbook()
    wb.active.append(['编号', '名字'])
    wb.active.append(['A', 'B'])
    out = io.BytesIO()
    wb.save(out)
    with bom_app.app_context():
        res = material_bom_service.import_file(out.getvalue(), 'x.xlsx', 'tester')
        assert not res.success and '无法识别' in res.message


def test_bom_routes_do_not_collide_with_item_routes():
    app = Flask(__name__)
    app.register_blueprint(material_bp, url_prefix='/api/material')
    routes = app.url_map.bind('localhost')
    assert routes.match('/api/material/items/A/B/bom') == (
        'material.material_item_bom', {'code': 'A/B'})
    assert routes.match('/api/material/items/A/B')[0] == 'material.material_detail'
    assert routes.match('/api/material/boms/3/tree')[0] == 'material.material_bom_tree'
    assert routes.match('/api/material/boms/import', method='POST')[0] == 'material.import_material_bom'
