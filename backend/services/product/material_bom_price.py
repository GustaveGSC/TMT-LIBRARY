"""研发 BOM 的实时计价（用户 2026-09-27 定：部件价格不存储，按「计价日期」现算）。

2026-09-28 起改为「齐全才计价」（用户定）：
- 原材料：取计价日期当天或之前最近的一条价格（cost_material_price，按去版本号的基础码绑定）；
  被标记为「不计价」的物料（客供件、赠送件等）按 0 元、算作已有价格。
- 部件（有下级）：**下级全部有价格**时才计价 = Σ(下级数量 × 下级单价)；
  下级不齐全但部件自己有外购价（采购导入的「下级全为 0 的半成品」）→ 用外购价；
  都不满足 → 未计价（unit_price=None），不给残缺合计，只给 missing（缺价原材料数）。
  理由：产品总有几个独有物料，下级价格不全基本说明现有价格来自别的产品的订单，残缺合计会误导。
- 「开始计价」= 这个物料下级价格第一次齐全的那个价格日期；之后的变化都是真实的价格涨跌。

成本视图（物料卡片用）按采购订单逐单重算，不存库（见 cost_snapshot）。

计价截止点 as_of（Codex 审计 #1/#3，2026-09-28）：
- None：最新价格；
- date：价格日期 ≤ 该日期；
- (date, max_price_id)：按采购订单计价——价格日期早于该日，或同日且价格记录 id ≤ 该订单最后一条价格的 id。
  同一天导入多个订单时，选前一个订单不会用到后一个订单的价格（之前只传日期，同日订单分不开）。
- 没有日期的价格只在「最新价格」时参与，不回溯到任何历史日期（避免今天补录的价格改写过去的开始计价时间）。
"""
from datetime import date as _date

from database.base import db
from database.models.rd.cost import CostBomNode, CostMaterialPrice


def price_histories(codes):
    """{基础码: [(price_date, 单价, 价格id, 批次id), ...]}，按 (日期, id) 从新到旧；一条查询。

    旧的 bom_calc（部件推算价）不参与：部件价格一律由下级现算。
    同一天多条价格按记录 id（导入先后）排序，后导入的在前。
    """
    codes = [c for c in set(codes) if c]
    if not codes:
        return {}
    rows = db.session.query(
        CostBomNode.code, CostMaterialPrice.price_date, CostMaterialPrice.unit_price,
        CostMaterialPrice.id, CostMaterialPrice.snapshot_id,
    ).join(CostMaterialPrice, CostMaterialPrice.node_id == CostBomNode.id).filter(
        CostBomNode.code.in_(codes), CostMaterialPrice.source != 'bom_calc',
    ).all()
    result = {}
    for code, day, price, pid, sid in rows:
        result.setdefault(code, []).append((day, float(price), pid, sid))
    # 新→旧：先按日期（无日期视为最早），同日按记录 id；在内存里排，避免 MySQL/SQLite 的 NULL 排序差异
    for items in result.values():
        items.sort(key=lambda x: (x[0] is not None, x[0] or _date.min, x[2]), reverse=True)
    return result


def _visible(day, pid, as_of):
    """价格记录在计价截止点 as_of 下是否可用（规则见模块说明）。"""
    if as_of is None:
        return True
    if day is None:
        return False          # 无日期价格不回溯到任何历史时点
    if isinstance(as_of, tuple):
        cut_day, cut_id = as_of
        return day < cut_day or (day == cut_day and pid <= cut_id)
    return day <= as_of


def price_as_of(history, as_of=None):
    """历史里取截止点 as_of 之前最近的一条：(单价, 日期)；没有返回 None。"""
    for day, price, pid, _sid in history or []:
        if _visible(day, pid, as_of) and price and price > 0:
            return price, day
    return None


def price_cursors(histories):
    """所有可能的「开始计价」时点（升序）：每个 (日期, 批次) 一组，取组内最大价格 id 作为截止点。

    返回 [((日期, 最大价格id), 批次id 或 None), ...]；手动价格（无批次）各自成组。
    """
    groups = {}
    for items in histories.values():
        for day, _price, pid, sid in items:
            if day is None:
                continue
            key = (day, sid if sid is not None else ('manual', pid))
            if key not in groups or pid > groups[key]:
                groups[key] = pid
    points = sorted(((day, pid), key[1] if not isinstance(key[1], tuple) else None)
                    for key, pid in groups.items() for day in [key[0]])
    return points


def collect_codes(nodes, acc=None):
    acc = set() if acc is None else acc
    for n in nodes:
        acc.add(n['code'])
        if n.get('children'):
            collect_codes(n['children'], acc)
    return acc


def collect_pairs(nodes, acc=None):
    """树上所有 (基础码, ERP 编码)，用于把「不计价」标记（按 ERP 编码存）换成基础码。"""
    acc = set() if acc is None else acc
    for n in nodes:
        acc.add((n['code'], n.get('erp_code')))
        if n.get('children'):
            collect_pairs(n['children'], acc)
    return acc


def _evaluate(nodes, histories, as_of, annotate, free):
    """逐层计价；返回 (合计或 None, 缺价原材料基础码集合)。

    缺价按原材料**种类**计（同一物料在树里出现多次只算一种），与物料卡片「已计价 N / M 种」同一口径。
    """
    total, missing = 0.0, set()
    for n in nodes:
        own = price_as_of(histories.get(n['code']), as_of)
        if n.get('children'):
            sub_total, sub_missing = _evaluate(n['children'], histories, as_of, annotate, free)
            if not sub_missing:
                unit, day, source, miss = sub_total, None, 'calc', set()
            elif own:
                unit, day, source, miss = own[0], own[1], 'own', set()          # 外购价兜底
            else:
                unit, day, source, miss = None, None, None, sub_missing          # 未计价
        elif own:
            unit, day, source, miss = own[0], own[1], 'material', set()
        elif n['code'] in free:
            unit, day, source, miss = 0.0, None, 'free', set()
        else:
            unit, day, source, miss = None, None, None, {n['code']}
        qty = float(n.get('qty') or 0)
        if annotate:
            n['unit_price'] = unit
            n['amount'] = round(unit * qty, 4) if unit is not None else None
            n['price_date'] = day.isoformat() if day else None
            n['price_source'] = source
            n['missing'] = len(miss)
        if unit is not None:
            total += unit * qty
        missing |= miss
    return (round(total, 4) if not missing else None), missing


def evaluate(nodes, histories, as_of=None, annotate=True, free=frozenset()):
    """给树上每个节点算单价/金额；返回这一层的 (合计, 缺价原材料种类数)。

    合计只有这一层全部有价格时才有意义，否则返回 None。
    annotate=False 时只算不写字段（成本历史要在多个日期上反复算）。
    free：「不计价」物料的基础码集合，按 0 元算作已有价格。
    """
    total, missing = _evaluate(nodes, histories, as_of, annotate, free)
    return total, len(missing)


def root_price(children, root_code, histories, as_of=None, annotate=True, free=frozenset()):
    """整份 BOM（根部件）的单价：下级齐全 → 计算价；不齐全但有外购价 → 外购价；否则未计价。

    另带 missing_codes（缺价原材料基础码），供成本视图列缺价清单，保证两处数字一致。
    """
    total, missing = _evaluate(children, histories, as_of, annotate, free)
    if not missing:
        return {'unit_price': total, 'missing': 0, 'price_source': 'calc', 'price_date': None,
                'missing_codes': set()}
    own = price_as_of(histories.get(root_code), as_of)
    if own:
        return {'unit_price': own[0], 'missing': 0, 'price_source': 'own',
                'price_date': own[1].isoformat() if own[1] else None, 'missing_codes': set()}
    return {'unit_price': None, 'missing': len(missing), 'price_source': None, 'price_date': None,
            'missing_codes': missing}


def cost_snapshot(children, root_code, histories, as_of=None, root_drawing=None, free=frozenset()):
    """某个计价日期下的成本快照（物料卡片成本视图用）。

    返回 {total, complete, leaves:{code: {eq, drawing, erp_code, name, parents}}, covered:set}
    - total：齐全（或用外购价）时的单价，否则 None；
    - 有效用量 eq = 从根到该行路径上数量的乘积（同一物料出现在多处时累加）；
    - covered = 全部原材料 − 根计价时的缺价集合（与 BOM 树的「缺N」同一来源，数字一致）。
    """
    leaves = {}

    def walk(nodes, mult, parent):
        for n in nodes:
            q = mult * float(n.get('qty') or 0)
            if n.get('children'):
                walk(n['children'], q, n['drawing'])
                continue
            leaf = leaves.setdefault(n['code'], {
                'eq': 0.0, 'drawing': n['drawing'], 'erp_code': n.get('erp_code'),
                'name': n.get('name'), 'parents': [],
            })
            leaf['eq'] += q
            if parent and parent not in leaf['parents']:
                leaf['parents'].append(parent)

    walk(children, 1.0, root_drawing)   # 第一层原材料的「所在部件」就是根本身
    res = root_price(children, root_code, histories, as_of, annotate=False, free=free)
    covered = set(leaves) - res['missing_codes']
    return {'total': res['unit_price'], 'complete': res['unit_price'] is not None,
            'leaves': leaves, 'covered': covered}


def start_point(children, root_code, histories, free=frozenset()):
    """「开始计价」时点：按 (价格日期, 导入先后) 从早到晚，找第一次齐全的那个截止点。

    返回 (是否已开始, 截止点 (日期, 最大价格id) 或 None, 批次id 或 None)。
    只靠无日期价格/不计价标记才齐全时：已开始，但截止点为 None。
    """
    for cursor, sid in price_cursors(histories):
        if root_price(children, root_code, histories, cursor, annotate=False, free=free)['unit_price'] is not None:
            return True, cursor, sid
    now = root_price(children, root_code, histories, None, annotate=False, free=free)
    return now['unit_price'] is not None, None, None
