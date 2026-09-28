"""采购工具 · 导入价格：只取原材料、特例半成品、同日同价跳过、同日不同价新增。"""
import io
from datetime import date

import openpyxl
import pytest
from flask import Flask

from database.base import db
import database.models.product.category  # noqa: F401
import database.models.product.finished  # noqa: F401
import database.models.product.resource  # noqa: F401
import database.models.product.material_supplier  # noqa: F401
from database.models.product.import_raw import ImportProductRaw
from database.models.rd.cost import (
    CostBomLine, CostBomNode, CostMaterialPrice, CostSnapshot, CostSnapshotSku,
)
from routes.purchase import purchase_bp
from services.purchase.price_import import extract_prices, parse_workbook, purchase_price_import_service
from utils import now_cst


HEADERS = ['主件品号', '主件品名', '主件规格', '品号', '品名', '规格', '序号', '组成用量',
           '元件品号', '标准号', '元件品名', '元件规格', '元件品名分类', '单价', '金额']

# 成品 F1 → 产成品 P1（部件）+ 原材料 R1（同一文件里出现两个单价）+ 原材料 R5（单价 0）
# P1 → R2；P1 → 特例半成品 S9（自身有价，下面 R3/R4 全为 0）
LINES = [
    ('F1-A01', 'P1-A01', 1, 0),
    ('F1-A01', 'R1-A01', 2, 1.5),
    ('P1-A01', 'R2-A01', 3, 2),
    ('P1-A01', 'S9-A01', 1, 10),
    ('S9-A01', 'R3-A01', 1, 0),
    ('S9-A01', 'R4-A01', 2, None),
    ('F1-A01', 'R5-A01', 1, 0),
    ('F1-A01', 'R1-A01', 1, 1.6),
]


def _workbook(lines=LINES, order_no='2M2-SC20240620-050'):
    wb = openpyxl.Workbook()
    summary = wb.active
    summary.title = '产品预估单'
    summary.append([f'订单号：{order_no}'])
    ws = wb.create_sheet('F1')
    ws.append(HEADERS)
    for i, (parent, child, qty, price) in enumerate(lines, start=1):
        ws.append(['F1-A01', '书桌', '', parent, '', '', i, qty, child, '', f'名{child}', '', '', price,
                   (price or 0) * qty])
    ws.append([str(len(lines))])   # 合计行
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config.update(SQLALCHEMY_DATABASE_URI='sqlite://', SQLALCHEMY_TRACK_MODIFICATIONS=False)
    db.init_app(app)
    tables = [ImportProductRaw.__table__, CostSnapshot.__table__, CostSnapshotSku.__table__,
              CostBomNode.__table__, CostBomLine.__table__, CostMaterialPrice.__table__]
    with app.app_context():
        db.metadata.create_all(bind=db.engine, tables=tables)
        for code in ('R1-A01', 'R2-A01', 'S9-A01'):
            db.session.add(ImportProductRaw(code=code, name=code, group_code='G', group_name='组',
                                            imported_at=now_cst()))
        db.session.commit()
        yield app
        db.session.remove()
        db.metadata.drop_all(bind=db.engine, tables=list(reversed(tables)))


def test_extract_only_raw_materials_and_special_semi():
    parsed = parse_workbook(_workbook())
    assert parsed['order_no'] == '2M2-SC20240620-050'
    assert parsed['suggested_date'] == '2024-06-20'
    items, zero_items, conflicts = extract_prices(parsed['lines'])
    got = {i['code']: (i['price'], i['kind']) for i in items}
    # P1 是普通部件不导入；S9 下面全是 0 → 导入 S9 自己的价；R3/R4 被 S9 覆盖不算「无价格」
    assert got == {'R1': (1.5, 'material'), 'R2': (2.0, 'material'), 'S9': (10.0, 'semi')}
    assert [z['code'] for z in zero_items] == ['R5']
    assert conflicts == [{'code': 'R1', 'prices': [1.5, 1.6]}]


def test_import_dedupes_same_day_same_price_only(app):
    with app.app_context():
        res = purchase_price_import_service.import_prices(_workbook(), '2024-06-20', 'buyer')
        assert res.success, res.message
        assert res.data['created'] == 3 and res.data['skipped'] == 0
        assert res.data['special_semis'] == 1 and res.data['zero_count'] == 1
        # 订单包含的成品（每个 Sheet 的主件品号）被记下，不记 BOM 明细
        batch = CostSnapshot.query.filter_by(id=res.data['batch_id']).one()
        assert [k.finished_code for k in CostSnapshotSku.query.filter_by(snapshot_id=batch.id)] == ['F1-A01']
        assert CostBomLine.query.count() == 0
        s9 = CostBomNode.query.filter_by(code='S9').one()
        assert s9.is_purchased_semi and s9.node_type == 'semi'
        price = CostMaterialPrice.query.filter_by(node_id=s9.id).one()
        assert price.price_date == date(2024, 6, 20) and float(price.unit_price) == 10
        assert price.source == 'bom_import'

        # 同一日期再导一次：全部「同日同价」跳过
        again = purchase_price_import_service.import_prices(_workbook(), '2024-06-20', 'buyer')
        assert again.data['created'] == 0 and again.data['skipped'] == 3

        # 同一日期、R2 价格不同：只新增 R2，R2 当天有两条价格
        changed = [l if l[1] != 'R2-A01' else ('P1-A01', 'R2-A01', 3, 2.5) for l in LINES]
        third = purchase_price_import_service.import_prices(_workbook(changed), '2024-06-20', 'buyer')
        assert third.data['created'] == 1 and third.data['skipped'] == 2
        r2 = CostBomNode.query.filter_by(code='R2').one()
        assert sorted(float(p.unit_price) for p in CostMaterialPrice.query.filter_by(node_id=r2.id)) == [2.0, 2.5]

        # 不同日期：全部新增（每个物料可以有多条不同日期的价格）
        other_day = purchase_price_import_service.import_prices(_workbook(), '2024-07-01', 'buyer')
        assert other_day.data['created'] == 3
        # 不写部件推算价
        assert CostMaterialPrice.query.filter_by(source='bom_calc').count() == 0
        # 导入记录
        history = purchase_price_import_service.history().data
        assert [h['price_date'] for h in history][:2] == ['2024-07-01', '2024-06-20']
        assert history[0]['price_count'] == 3


def test_preview_marks_new_and_skip_by_date(app):
    with app.app_context():
        purchase_price_import_service.import_prices(_workbook(), '2024-06-20', 'buyer')
        same = purchase_price_import_service.preview(_workbook()).data   # 默认用订单号日期
        assert same['price_date'] == '2024-06-20'
        assert same['new_count'] == 0 and same['skip_count'] == 3
        other = purchase_price_import_service.preview(_workbook(), '2024-08-01').data
        assert other['new_count'] == 3 and other['skip_count'] == 0
        by_code = {i['code']: i for i in other['items']}
        assert by_code['R1']['in_erp'] and not {z['code']: z for z in other['zero_items']}['R5']['in_erp']
        assert [s['code'] for s in other['special_semis']] == ['S9']


def test_import_requires_confirmed_date(app):
    with app.app_context():
        res = purchase_price_import_service.import_prices(_workbook(), '', 'buyer')
        assert not res.success and '价格日期' in res.message
        assert CostMaterialPrice.query.count() == 0


def test_purchase_routes_registered():
    flask_app = Flask(__name__)
    flask_app.register_blueprint(purchase_bp, url_prefix='/api/purchase')
    routes = flask_app.url_map.bind('localhost')
    assert routes.match('/api/purchase/price-import/preview', method='POST')[0] == 'purchase.preview_price_import'
    assert routes.match('/api/purchase/price-import', method='POST')[0] == 'purchase.run_price_import'
    assert routes.match('/api/purchase/price-import/history')[0] == 'purchase.price_import_history'


def test_price_batches_list_orders_with_dates_newest_first(app):
    from services.product.material_price import material_price_service
    with app.app_context():
        purchase_price_import_service.import_prices(_workbook(order_no='2M2-SC20240620-050'), '2024-06-20', 'buyer')
        purchase_price_import_service.import_prices(_workbook(order_no='2M2-SC20250101-001'), '2025-01-01', 'buyer')
        # 全部同日同价跳过、没有写入价格的批次不列出
        purchase_price_import_service.import_prices(_workbook(order_no='2M2-SC20250101-002'), '2025-01-01', 'buyer')
        data = material_price_service.price_batches().data
        assert [(b['order_no'], b['price_date'], b['price_count']) for b in data] == [
            ('2M2-SC20250101-001', '2025-01-01', 3), ('2M2-SC20240620-050', '2024-06-20', 3)]
