"""研发 BOM 的实时计价（用户 2026-09-27 定：部件价格不存储，按「计价日期」现算）。

- 原材料：取计价日期当天或之前最近的一条价格（cost_material_price，按去版本号的基础码绑定）；
  不给计价日期时取最新一条。
- 部件（有下级）：Σ(下级数量 × 下级单价)，逐层往上；
  特例：下级全部没有价格、而部件自己有采购价（采购导入的「下级全为 0 的半成品」）→ 用自己的价格。
- 每个节点带 missing：其下没有价格的原材料数量，避免把漏算的合计当成完整价格。

价格历史（物料卡片用）：取下级所有原材料出现过的价格日期，在每个日期上重算一次，不存库。
"""
from datetime import date as _date

from database.base import db
from database.models.rd.cost import CostBomNode, CostMaterialPrice


def price_histories(codes):
    """{基础码: [(price_date, 单价), ...]}，按日期从新到旧；一条查询。

    旧的 bom_calc（部件推算价）不参与：部件价格一律由下级现算。
    无日期的价格排在最后（视为最早）。
    """
    codes = [c for c in set(codes) if c]
    if not codes:
        return {}
    rows = db.session.query(
        CostBomNode.code, CostMaterialPrice.price_date, CostMaterialPrice.unit_price,
    ).join(CostMaterialPrice, CostMaterialPrice.node_id == CostBomNode.id).filter(
        CostBomNode.code.in_(codes), CostMaterialPrice.source != 'bom_calc',
    ).order_by(
        CostBomNode.code, CostMaterialPrice.price_date.desc(),
        CostMaterialPrice.created_at.desc(), CostMaterialPrice.id.desc(),
    ).all()
    result = {}
    for code, day, price in rows:
        result.setdefault(code, []).append((day, float(price)))
    # MySQL 的 DESC 会把 NULL 排在最后，SQLite 相反；统一在内存里排一次
    for code, items in result.items():
        items.sort(key=lambda x: (x[0] is not None, x[0] or _date.min), reverse=True)
    return result


def price_as_of(history, as_of=None):
    """历史里取计价日期当天或之前最近的一条：(单价, 日期)；没有返回 None。"""
    for day, price in history or []:
        if as_of is None or day is None or day <= as_of:
            if price and price > 0:
                return price, day
    return None


def collect_codes(nodes, acc=None):
    acc = set() if acc is None else acc
    for n in nodes:
        acc.add(n['code'])
        if n.get('children'):
            collect_codes(n['children'], acc)
    return acc


def evaluate(nodes, histories, as_of=None, annotate=True):
    """给树上每个节点算单价/金额；返回这一层的 (合计, missing)。

    annotate=False 时只算合计不写字段（价格历史要在多个日期上反复算）。
    """
    total, missing = 0.0, 0
    for n in nodes:
        own = price_as_of(histories.get(n['code']), as_of)
        if n.get('children'):
            sub_total, sub_missing = evaluate(n['children'], histories, as_of, annotate)
            if sub_total <= 0 and own:
                unit, day, source, miss = own[0], own[1], 'own', 0
            elif sub_total <= 0:
                unit, day, source, miss = None, None, None, sub_missing
            else:
                unit, day, source, miss = round(sub_total, 4), None, 'calc', sub_missing
        elif own:
            unit, day, source, miss = own[0], own[1], 'material', 0
        else:
            unit, day, source, miss = None, None, None, 1
        qty = float(n.get('qty') or 0)
        if annotate:
            n['unit_price'] = unit
            n['amount'] = round(unit * qty, 4) if unit is not None else None
            n['price_date'] = day.isoformat() if day else None
            n['price_source'] = source
            n['missing'] = miss
        if unit is not None:
            total += unit * qty
        missing += miss
    return round(total, 4), missing


def root_price(children, root_code, histories, as_of=None, annotate=True):
    """整份 BOM（根部件）的单价：同样遵守「下级全无价格时用自己的采购价」。"""
    total, missing = evaluate(children, histories, as_of, annotate)
    own = price_as_of(histories.get(root_code), as_of)
    if total <= 0 and own:
        return {'unit_price': own[0], 'missing': 0, 'price_source': 'own',
                'price_date': own[1].isoformat() if own[1] else None}
    if total <= 0:
        return {'unit_price': None, 'missing': missing, 'price_source': None, 'price_date': None}
    return {'unit_price': total, 'missing': missing, 'price_source': 'calc', 'price_date': None}


def history_points(children, root_code, histories):
    """在每个出现过价格的日期上重算根单价，返回价格变化点（新→旧），相邻相同的合并。"""
    days = sorted({d for items in histories.values() for d, _ in items if d is not None})
    points = []
    for day in days:
        r = root_price(children, root_code, histories, day, annotate=False)
        if r['unit_price'] is None:
            continue
        if points and points[-1]['unit_price'] == r['unit_price'] and points[-1]['missing'] == r['missing']:
            continue
        points.append({'date': day.isoformat(), 'unit_price': r['unit_price'], 'missing': r['missing']})
    return list(reversed(points))
