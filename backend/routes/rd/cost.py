"""
BOM 成本库路由 Blueprint
挂载路径：/api/rd/cost
"""
import os
import tempfile
from datetime import date
from flask import Blueprint, request, g
from auth import require_auth
from result import Result
from database.base import db
from database.models.rd.cost import (
    CostSnapshot, CostSnapshotSku, CostBomNode,
    CostBomLine, CostMaterialSupplier, CostMaterialRule, CostMaterialPrice,
)

cost_bp = Blueprint('rd_cost', __name__)


def _require_edit():
    """检查 rd:edit 权限。"""
    user = g.get('current_user')
    if not user:
        return Result.fail('未登录').to_response()
    from auth import has_permission
    if not has_permission(user, 'rd:edit'):
        return Result.fail('权限不足').to_response()
    return None


# ─────────────────────────────────────────────────────────────
# 快照管理
# ─────────────────────────────────────────────────────────────

@cost_bp.get('/snapshots')
@require_auth
def list_snapshots():
    """按产成品分组返回，每行含多个订单条目。"""
    page     = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 30))

    # 取所有记录（不分页），在 Python 侧分组后再分页
    rows = (
        db.session.query(CostSnapshotSku, CostSnapshot)
        .join(CostSnapshot, CostSnapshotSku.snapshot_id == CostSnapshot.id)
        .order_by(CostSnapshotSku.finished_code, CostSnapshot.snapshot_date.desc())
        .all()
    )

    from collections import OrderedDict
    groups = OrderedDict()
    for sku, snap in rows:
        fc = sku.finished_code
        if fc not in groups:
            groups[fc] = {
                'finished_code': fc,
                'finished_name': sku.finished_name or '',
                'orders': [],
            }
        groups[fc]['orders'].append({
            'sku_id':        sku.id,
            'snapshot_id':   snap.id,
            'order_no':      snap.order_no or '',
            'snapshot_date': snap.snapshot_date.strftime('%Y-%m-%d') if snap.snapshot_date else '',
            'created_at':    snap.created_at.strftime('%Y-%m-%d') if snap.created_at else '',
            'created_by':    snap.created_by or '',
            'total_cost':    float(sku.total_cost) if sku.total_cost is not None else None,
        })

    all_items = list(groups.values())
    total     = len(all_items)
    page_items = all_items[(page - 1) * per_page: page * per_page]
    return Result.ok(data={'total': total, 'items': page_items}).to_response()


@cost_bp.post('/preview')
@require_auth
def preview_snapshot():
    file = request.files.get('file')
    if not file or not file.filename:
        return Result.fail('请上传 Excel 文件').to_response()

    suffix = os.path.splitext(file.filename)[1] or '.xlsx'
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        file.save(tmp.name)
        tmp_path = tmp.name

    try:
        from services.rd.cost_import import preview_excel
        result = preview_excel(tmp_path)
    except Exception as e:
        return Result.fail(f'解析失败：{e}').to_response()
    finally:
        os.unlink(tmp_path)

    # 用产品库匹配成品名称（查 product_packaged 表）
    try:
        from database.models.product.finished import ProductPackaged
        codes = [s['finished_code'] for s in result.get('skus', []) if s.get('finished_code')]
        if codes:
            rows = ProductPackaged.query.filter(ProductPackaged.code.in_(codes)).with_entities(
                ProductPackaged.code, ProductPackaged.name
            ).all()
            code_to_name = {r.code: r.name for r in rows}
            for sku in result['skus']:
                name = code_to_name.get(sku['finished_code'])
                if name:
                    sku['finished_name'] = name
    except Exception:
        pass  # 查询失败不影响预览

    return Result.ok(data=result).to_response()


@cost_bp.post('/import')
@require_auth
def import_snapshot():
    err = _require_edit()
    if err:
        return err

    created_by = g.current_user.get('username', '')

    # ── JSON 模式：从（可能已编辑的）预览数据导入 ──────────
    if request.is_json:
        body = request.get_json(force=True)
        preview_data      = body.get('preview_data', {})
        snapshot_date_str = body.get('snapshot_date', '')
        notes             = body.get('notes', '')

        snapshot_date = None
        if snapshot_date_str:
            try:
                snapshot_date = date.fromisoformat(snapshot_date_str)
            except ValueError:
                return Result.fail('日期格式错误，应为 YYYY-MM-DD').to_response()

        try:
            from services.rd.cost_import import import_from_data
            result = import_from_data(preview_data, snapshot_date, notes, created_by)
        except Exception as e:
            db.session.rollback()
            return Result.fail(f'导入失败：{e}').to_response()

        return Result.ok(data=result, message='导入成功').to_response()

    # ── 文件模式：上传 Excel 直接解析导入 ─────────────────
    file = request.files.get('file')
    if not file or not file.filename:
        return Result.fail('请上传 Excel 文件').to_response()

    snapshot_date_str = request.form.get('snapshot_date', '')
    notes      = request.form.get('notes', '')

    snapshot_date = None
    if snapshot_date_str:
        try:
            snapshot_date = date.fromisoformat(snapshot_date_str)
        except ValueError:
            return Result.fail('日期格式错误，应为 YYYY-MM-DD').to_response()

    suffix = os.path.splitext(file.filename)[1] or '.xlsx'
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        file.save(tmp.name)
        tmp_path = tmp.name

    try:
        from services.rd.cost_import import import_excel
        result = import_excel(tmp_path, snapshot_date, notes, created_by)
    except Exception as e:
        db.session.rollback()
        return Result.fail(f'解析失败：{e}').to_response()
    finally:
        os.unlink(tmp_path)

    return Result.ok(data=result, message='导入成功').to_response()


@cost_bp.delete('/snapshots/<int:snapshot_id>')
@require_auth
def delete_snapshot(snapshot_id):
    err = _require_edit()
    if err:
        return err

    snapshot = CostSnapshot.query.get(snapshot_id)
    if not snapshot:
        return Result.fail('快照不存在').to_response()

    db.session.delete(snapshot)
    db.session.commit()
    return Result.ok(message='已删除').to_response()


@cost_bp.delete('/skus/<int:sku_id>')
@require_auth
def delete_sku(sku_id):
    """删除单个 SKU 及其 BOM 明细行；若快照内已无 SKU 则顺带删快照。"""
    err = _require_edit()
    if err:
        return err

    sku = CostSnapshotSku.query.get(sku_id)
    if not sku:
        return Result.fail('SKU 不存在').to_response()

    snapshot_id = sku.snapshot_id
    db.session.delete(sku)
    db.session.flush()

    # 若快照内已无其他 SKU，删除快照本身
    remaining = CostSnapshotSku.query.filter_by(snapshot_id=snapshot_id).count()
    if remaining == 0:
        snapshot = CostSnapshot.query.get(snapshot_id)
        if snapshot:
            db.session.delete(snapshot)

    db.session.commit()
    return Result.ok(message='已删除').to_response()


@cost_bp.get('/snapshots/<int:snapshot_id>/skus')
@require_auth
def get_snapshot_skus(snapshot_id):
    snapshot = CostSnapshot.query.get(snapshot_id)
    if not snapshot:
        return Result.fail('快照不存在').to_response()
    return Result.ok(data={
        'snapshot': snapshot.to_dict(),
        'skus':     [s.to_dict() for s in snapshot.skus],
    }).to_response()


# ─────────────────────────────────────────────────────────────
# SKU BOM 树
# ─────────────────────────────────────────────────────────────

@cost_bp.get('/sku/<int:sku_id>/bom')
@require_auth
def get_sku_bom(sku_id):
    sku = CostSnapshotSku.query.get(sku_id)
    if not sku:
        return Result.fail('SKU 不存在').to_response()

    lines = CostBomLine.query.filter_by(sku_id=sku_id).all()
    rules = _load_code_rules()

    # 批量查 child_spec 和首选供应商
    child_node_ids = list({line.child_node_id for line in lines})
    node_spec_map     = {}
    node_supplier_map = {}
    if child_node_ids:
        nodes = CostBomNode.query.filter(CostBomNode.id.in_(child_node_ids)).with_entities(
            CostBomNode.id, CostBomNode.spec
        ).all()
        node_spec_map = {n.id: n.spec or '' for n in nodes}

        suppliers = CostMaterialSupplier.query.filter(
            CostMaterialSupplier.node_id.in_(child_node_ids),
            CostMaterialSupplier.is_preferred == True,
        ).with_entities(CostMaterialSupplier.node_id, CostMaterialSupplier.supplier_name).all()
        # 每个 node 取第一条首选
        for s in suppliers:
            if s.node_id not in node_supplier_map:
                node_supplier_map[s.node_id] = s.supplier_name

    # 构建 {parent_node_id -> [line_dict, ...]} 映射
    children_map = {}
    for line in lines:
        d = line.to_dict()
        d['child_spec']        = node_spec_map.get(line.child_node_id, '')
        d['material_category'] = _match_category(d['child_code'], rules)
        d['supplier_name']     = node_supplier_map.get(line.child_node_id, '')
        children_map.setdefault(line.parent_node_id, []).append(d)

    # 根节点：成品 node（parent_code == finished_code）
    finished_base_code = _strip_version_py(sku.finished_code)
    root_node = CostBomNode.query.filter_by(code=finished_base_code).first()

    def build_tree(node_id):
        kids = children_map.get(node_id, [])
        result = []
        for kid in sorted(kids, key=lambda x: x['child_code'] or ''):
            child_id = kid['child_node_id']
            kid['children'] = build_tree(child_id)
            # 半成品：total_price = 子件合计（外购半成品保留自身价格）
            if kid['child_node_type'] == 'semi' and not kid['child_is_purchased_semi']:
                kid['total_price'] = sum(c['total_price'] or 0 for c in kid['children'])
                kid['unit_price']  = kid['total_price'] / (kid['quantity'] or 1) if kid['quantity'] else None
            result.append(kid)
        return result

    tree = build_tree(root_node.id) if root_node else []

    return Result.ok(data={
        'sku':  sku.to_dict(),
        'tree': tree,
    }).to_response()


def _strip_version_py(code: str) -> str:
    import re
    if not code:
        return code
    return re.sub(r'-[A-Z]\d+$', '', code.strip())


# ─────────────────────────────────────────────────────────────
# 物料节点管理
# ─────────────────────────────────────────────────────────────

def _load_code_rules():
    """加载 erp_code_rules，按前缀长度降序（最长前缀优先匹配）。"""
    from sqlalchemy import text as sql_text
    rows = db.session.execute(
        sql_text("SELECT prefix, description FROM erp_code_rules WHERE is_disabled=0 ORDER BY LENGTH(prefix) DESC")
    ).all()
    return [(r.prefix, r.description) for r in rows]


def _match_category(code: str, rules: list) -> str | None:
    """用最长前缀匹配返回 erp_code_rules.description。"""
    if not code:
        return None
    for prefix, desc in rules:
        if code.startswith(prefix):
            return desc
    return None


@cost_bp.get('/nodes')
@require_auth
def search_nodes():
    q         = request.args.get('q', '').strip()
    page      = int(request.args.get('page', 1))
    per_page  = int(request.args.get('per_page', 30))
    node_type = request.args.get('node_type', '')  # material/semi/finished

    query = CostBomNode.query
    if q:
        like = f'%{q}%'
        query = query.filter(
            db.or_(CostBomNode.code.like(like), CostBomNode.name.like(like))
        )
    if node_type:
        query = query.filter(CostBomNode.node_type == node_type)

    # 加载编码规则，在 Python 端完成分类匹配与排序
    rules = _load_code_rules()
    all_nodes = query.order_by(CostBomNode.code).all()

    # 附加 material_category 并排序
    def enrich(node):
        d = node.to_dict()
        d['material_category'] = _match_category(node.code, rules)
        return d

    enriched = [enrich(n) for n in all_nodes]
    enriched.sort(key=lambda x: (x['material_category'] or '\uffff', x['code']))

    total = len(enriched)
    page_items = enriched[(page-1)*per_page : page*per_page]

    # 附加最新单价
    node_ids = [n['id'] for n in page_items]
    if node_ids:
        latest_rows = (
            db.session.query(
                CostBomLine.child_node_id,
                CostBomLine.unit_price,
            )
            .join(CostSnapshotSku, CostBomLine.sku_id == CostSnapshotSku.id)
            .join(CostSnapshot, CostSnapshotSku.snapshot_id == CostSnapshot.id)
            .filter(CostBomLine.child_node_id.in_(node_ids))
            .order_by(CostSnapshot.snapshot_date.desc(), CostSnapshot.created_at.desc())
            .all()
        )
        # 取每个 node_id 第一条（已按日期降序）
        price_map = {}
        for nid, price in latest_rows:
            if nid not in price_map and price is not None:
                price_map[nid] = float(price)
        for item in page_items:
            item['latest_price'] = price_map.get(item['id'])

    return Result.ok(data={
        'total': total,
        'items': page_items,
    }).to_response()


@cost_bp.get('/nodes/<int:node_id>')
@require_auth
def get_node(node_id):
    node = CostBomNode.query.get(node_id)
    if not node:
        return Result.fail('节点不存在').to_response()
    rules = _load_code_rules()
    d = node.to_dict(include_suppliers=True)
    d['material_category'] = _match_category(node.code, rules)
    return Result.ok(data=d).to_response()


@cost_bp.patch('/nodes/<int:node_id>')
@require_auth
def update_node(node_id):
    err = _require_edit()
    if err:
        return err

    node = CostBomNode.query.get(node_id)
    if not node:
        return Result.fail('节点不存在').to_response()

    data = request.get_json() or {}
    allowed = ('is_purchased_semi', 'material_type', 'weight_kg', 'area_m2', 'notes', 'node_type')
    for key in allowed:
        if key in data:
            setattr(node, key, data[key])

    db.session.commit()
    return Result.ok(data=node.to_dict(), message='已更新').to_response()


@cost_bp.get('/nodes/<int:node_id>/price-history')
@require_auth
def node_price_history(node_id):
    node = CostBomNode.query.get(node_id)
    if not node:
        return Result.fail('节点不存在').to_response()

    rows = (
        db.session.query(
            CostBomLine.unit_price,
            CostSnapshot.snapshot_date,
            CostSnapshot.order_no,
            CostSnapshot.id.label('snapshot_id'),
        )
        .join(CostSnapshotSku, CostBomLine.sku_id == CostSnapshotSku.id)
        .join(CostSnapshot,    CostSnapshotSku.snapshot_id == CostSnapshot.id)
        .filter(CostBomLine.child_node_id == node_id)
        .order_by(CostSnapshot.snapshot_date.asc(), CostSnapshot.created_at.asc())
        .all()
    )

    history = [
        {
            'snapshot_id':   r.snapshot_id,
            'order_no':      r.order_no or '',
            'snapshot_date': r.snapshot_date.strftime('%Y-%m-%d') if r.snapshot_date else '',
            'unit_price':    float(r.unit_price) if r.unit_price is not None else None,
        }
        for r in rows
    ]
    return Result.ok(data=history).to_response()


@cost_bp.get('/nodes/<int:node_id>/usages')
@require_auth
def node_usages(node_id):
    """该物料出现在哪些快照/SKU 里。"""
    rows = (
        db.session.query(
            CostBomLine.unit_price,
            CostBomLine.quantity,
            CostSnapshotSku.finished_code,
            CostSnapshotSku.finished_name,
            CostSnapshotSku.id.label('sku_id'),
            CostSnapshot.order_no,
            CostSnapshot.snapshot_date,
            CostSnapshot.id.label('snapshot_id'),
        )
        .join(CostSnapshotSku, CostBomLine.sku_id == CostSnapshotSku.id)
        .join(CostSnapshot,    CostSnapshotSku.snapshot_id == CostSnapshot.id)
        .filter(CostBomLine.child_node_id == node_id)
        .order_by(CostSnapshot.snapshot_date.desc())
        .all()
    )
    usages = [
        {
            'snapshot_id':   r.snapshot_id,
            'order_no':      r.order_no or '',
            'snapshot_date': r.snapshot_date.strftime('%Y-%m-%d') if r.snapshot_date else '',
            'sku_id':        r.sku_id,
            'finished_code': r.finished_code,
            'finished_name': r.finished_name or '',
            'unit_price':    float(r.unit_price) if r.unit_price is not None else None,
            'quantity':      float(r.quantity) if r.quantity is not None else None,
        }
        for r in rows
    ]
    return Result.ok(data=usages).to_response()


# ─────────────────────────────────────────────────────────────
# 供应商报价
# ─────────────────────────────────────────────────────────────

@cost_bp.get('/suppliers')
@require_auth
def list_suppliers():
    node_id = request.args.get('node_id', type=int)
    query = CostMaterialSupplier.query
    if node_id:
        query = query.filter_by(node_id=node_id)
    suppliers = query.order_by(
        CostMaterialSupplier.is_preferred.desc(),
        CostMaterialSupplier.price_date.desc()
    ).all()
    return Result.ok(data=[s.to_dict() for s in suppliers]).to_response()


@cost_bp.post('/suppliers')
@require_auth
def add_supplier():
    err = _require_edit()
    if err:
        return err

    data = request.get_json() or {}
    node_id = data.get('node_id')
    if not node_id:
        return Result.fail('缺少 node_id').to_response()

    node = CostBomNode.query.get(node_id)
    if not node:
        return Result.fail('节点不存在').to_response()

    price_date = None
    if data.get('price_date'):
        try:
            price_date = date.fromisoformat(data['price_date'])
        except ValueError:
            pass

    # 若设为首选，取消其他首选
    if data.get('is_preferred'):
        CostMaterialSupplier.query.filter_by(node_id=node_id, is_preferred=True).update({'is_preferred': False})

    supplier = CostMaterialSupplier(
        node_id=node_id,
        supplier_name=data.get('supplier_name', ''),
        unit_price=data.get('unit_price'),
        price_date=price_date,
        is_preferred=bool(data.get('is_preferred', False)),
        notes=data.get('notes', '') or None,
        created_by=g.current_user.get('username', ''),
    )
    db.session.add(supplier)
    db.session.commit()
    return Result.ok(data=supplier.to_dict(), message='已添加').to_response()


@cost_bp.delete('/suppliers/<int:supplier_id>')
@require_auth
def delete_supplier(supplier_id):
    err = _require_edit()
    if err:
        return err

    supplier = CostMaterialSupplier.query.get(supplier_id)
    if not supplier:
        return Result.fail('不存在').to_response()

    db.session.delete(supplier)
    db.session.commit()
    return Result.ok(message='已删除').to_response()


@cost_bp.patch('/suppliers/<int:supplier_id>')
@require_auth
def update_supplier(supplier_id):
    err = _require_edit()
    if err:
        return err

    supplier = CostMaterialSupplier.query.get(supplier_id)
    if not supplier:
        return Result.fail('不存在').to_response()

    data = request.get_json() or {}

    if data.get('is_preferred') and not supplier.is_preferred:
        CostMaterialSupplier.query.filter(
            CostMaterialSupplier.node_id == supplier.node_id,
            CostMaterialSupplier.id != supplier_id,
        ).update({'is_preferred': False})

    for key in ('supplier_name', 'unit_price', 'notes', 'is_preferred'):
        if key in data:
            setattr(supplier, key, data[key])
    if 'price_date' in data and data['price_date']:
        try:
            supplier.price_date = date.fromisoformat(data['price_date'])
        except ValueError:
            pass

    db.session.commit()
    return Result.ok(data=supplier.to_dict(), message='已更新').to_response()


# ─────────────────────────────────────────────────────────────
# 材料估算规则
# ─────────────────────────────────────────────────────────────

@cost_bp.get('/material-rules')
@require_auth
def list_material_rules():
    mtype = request.args.get('material_type', '')
    query = CostMaterialRule.query
    if mtype:
        query = query.filter_by(material_type=mtype)
    rules = query.order_by(
        CostMaterialRule.material_type,
        CostMaterialRule.effective_date.desc()
    ).all()
    return Result.ok(data=[r.to_dict() for r in rules]).to_response()


@cost_bp.post('/material-rules')
@require_auth
def add_material_rule():
    err = _require_edit()
    if err:
        return err

    data = request.get_json() or {}
    effective_date = None
    if data.get('effective_date'):
        try:
            effective_date = date.fromisoformat(data['effective_date'])
        except ValueError:
            pass

    rule = CostMaterialRule(
        material_type=data.get('material_type'),
        rule_name=data.get('rule_name', ''),
        unit=data.get('unit', 'kg'),
        price_per_unit=data.get('price_per_unit'),
        effective_date=effective_date,
        notes=data.get('notes', '') or None,
    )
    db.session.add(rule)
    db.session.commit()
    return Result.ok(data=rule.to_dict(), message='已添加').to_response()


@cost_bp.delete('/material-rules/<int:rule_id>')
@require_auth
def delete_material_rule(rule_id):
    err = _require_edit()
    if err:
        return err

    rule = CostMaterialRule.query.get(rule_id)
    if not rule:
        return Result.fail('不存在').to_response()

    db.session.delete(rule)
    db.session.commit()
    return Result.ok(message='已删除').to_response()


# ─────────────────────────────────────────────────────────────
# 物料价格历史
# ─────────────────────────────────────────────────────────────

@cost_bp.get('/nodes/<int:node_id>/prices')
@require_auth
def list_material_prices(node_id):
    node = CostBomNode.query.get(node_id)
    if not node:
        return Result.fail('节点不存在').to_response()
    prices = (
        CostMaterialPrice.query
        .filter_by(node_id=node_id)
        .order_by(CostMaterialPrice.price_date.desc(),
                  CostMaterialPrice.created_at.desc())
        .all()
    )
    # 批量取关联快照的订单号
    snapshot_ids = list({p.snapshot_id for p in prices if p.snapshot_id})
    order_map = {}
    if snapshot_ids:
        snaps = CostSnapshot.query.filter(CostSnapshot.id.in_(snapshot_ids)).with_entities(
            CostSnapshot.id, CostSnapshot.order_no
        ).all()
        order_map = {s.id: s.order_no or '' for s in snaps}

    result = []
    for p in prices:
        d = p.to_dict()
        d['order_no'] = order_map.get(p.snapshot_id, '') if p.snapshot_id else ''
        result.append(d)
    return Result.ok(data=result).to_response()


@cost_bp.post('/nodes/<int:node_id>/prices')
@require_auth
def add_material_price(node_id):
    err = _require_edit()
    if err:
        return err

    node = CostBomNode.query.get(node_id)
    if not node:
        return Result.fail('节点不存在').to_response()

    data = request.get_json() or {}
    if not data.get('unit_price'):
        return Result.fail('单价不能为空').to_response()

    price_date = None
    if data.get('price_date'):
        try:
            price_date = date.fromisoformat(data['price_date'])
        except ValueError:
            return Result.fail('日期格式错误').to_response()

    price = CostMaterialPrice(
        node_id=node_id,
        unit_price=data['unit_price'],
        price_date=price_date,
        supplier_name=data.get('supplier_name') or None,
        source='manual',
        notes=data.get('notes') or None,
        created_by=g.current_user.get('username', ''),
    )
    db.session.add(price)
    db.session.commit()
    return Result.ok(data=price.to_dict(), message='已添加').to_response()


@cost_bp.patch('/prices/<int:price_id>')
@require_auth
def update_material_price(price_id):
    err = _require_edit()
    if err:
        return err

    price = CostMaterialPrice.query.get(price_id)
    if not price:
        return Result.fail('不存在').to_response()

    data = request.get_json() or {}
    for key in ('unit_price', 'supplier_name', 'notes'):
        if key in data:
            setattr(price, key, data[key] or None if key != 'unit_price' else data[key])
    if 'price_date' in data and data['price_date']:
        try:
            price.price_date = date.fromisoformat(data['price_date'])
        except ValueError:
            return Result.fail('日期格式错误').to_response()

    db.session.commit()
    return Result.ok(data=price.to_dict(), message='已更新').to_response()


@cost_bp.delete('/prices/<int:price_id>')
@require_auth
def delete_material_price(price_id):
    err = _require_edit()
    if err:
        return err

    price = CostMaterialPrice.query.get(price_id)
    if not price:
        return Result.fail('不存在').to_response()

    db.session.delete(price)
    db.session.commit()
    return Result.ok(message='已删除').to_response()


# ─────────────────────────────────────────────────────────────
# 列名别名配置
# ─────────────────────────────────────────────────────────────

_COL_ALIASES_KEY = 'cost_col_aliases'


@cost_bp.get('/col-aliases')
@require_auth
def get_col_aliases():
    import json
    from database.models.account import SiteConfig
    from services.rd.cost_import import DEFAULT_COL_ALIASES
    row = SiteConfig.query.get(_COL_ALIASES_KEY)
    if row and row.value:
        try:
            aliases = json.loads(row.value)
        except Exception:
            aliases = DEFAULT_COL_ALIASES
    else:
        aliases = DEFAULT_COL_ALIASES
    return Result.ok(data=aliases).to_response()


@cost_bp.put('/col-aliases')
@require_auth
def set_col_aliases():
    err = _require_edit()
    if err:
        return err
    import json
    from database.models.account import SiteConfig
    data = request.get_json() or {}
    # 过滤空值
    cleaned = {k: [v for v in vs if v.strip()] for k, vs in data.items() if isinstance(vs, list)}
    row = SiteConfig.query.get(_COL_ALIASES_KEY)
    if row:
        row.value = json.dumps(cleaned, ensure_ascii=False)
    else:
        db.session.add(SiteConfig(key=_COL_ALIASES_KEY, value=json.dumps(cleaned, ensure_ascii=False)))
    db.session.commit()
    return Result.ok(message='已保存').to_response()


# ─────────────────────────────────────────────────────────────
# 成本预估（纯计算，不存库）
# ─────────────────────────────────────────────────────────────

@cost_bp.post('/estimate/calc')
@require_auth
def estimate_calc():
    """
    前端传入物料行列表，服务端返回汇总：
      items: [{ child_node_id?, name, quantity, unit_price, purchase_type }]
    返回：{ total, purchase_total, self_made_total }
    """
    data  = request.get_json() or {}
    items = data.get('items', [])

    total         = 0.0
    purchase_total   = 0.0
    self_made_total  = 0.0

    for item in items:
        qty   = float(item.get('quantity') or 0)
        price = float(item.get('unit_price') or 0)
        sub   = qty * price
        total += sub
        pt = item.get('purchase_type', '')
        if '自制' in pt:
            self_made_total += sub
        else:
            purchase_total += sub

    return Result.ok(data={
        'total':            round(total, 4),
        'purchase_total':   round(purchase_total, 4),
        'self_made_total':  round(self_made_total, 4),
    }).to_response()
