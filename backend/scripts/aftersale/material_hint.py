"""从发货物料（products）解析材质大类，作为一级分类的硬信号。

来源：用户在 2026-05 标注中两次指出「这一点可以从发货物料里得出」——
备注只写"书架搁板掉漆""灯支架层板有磕碰"，文字上分不出实木还是钣金，
但物料名里写得很清楚。

products 的 name 是规范化命名：`原材料_{材质大类}_{材质}_{部位}`
  原材料_木器_桦木_书架层板     → 木器
  原材料_金属件_铁件_顶部层板   → 金属件
  原材料_塑胶件_塑料件_塑料挂钩 → 塑胶件

实测判别力（2026-05，461 单，覆盖率 40.6%）：
  木器   → 实木问题  92.5%   ← 硬信号
  金属件 → 钣金问题  66.7%   ← 硬信号（人工判钣金问题且有材质信息的 8 单全是金属件）
  塑胶件 → 物料破损  47.8%   ← 仅参考
  定制件 → 主功能失效 58.8%  ← 仅参考
  标准件 → 次功能失效/错漏件 28.6%/25.7% ← 仅参考

用途：修掉「实木问题 vs 钣金问题」的边界误判（第四轮钣金召回一度跌到 40%）。
"""

# 只有这两类判别力足够强，可作硬信号
STRONG = {'木器': '实木问题', '金属件': '钣金问题'}
# 以下仅作参考，不要当硬规则用
WEAK = {'塑胶件': '物料破损', '定制件': '主功能失效', '标准件': '次功能失效'}


def parse(products):
    """→ (材质大类列表, 部位列表)。products 为 blind 数据里的 products 字段。"""
    cats, parts = [], []
    for x in (products or []):
        name = (x.get('name') if isinstance(x, dict) else str(x)) or ''
        seg = name.split('_')
        if len(seg) >= 2 and seg[0] == '原材料':
            cats.append(seg[1])
            if len(seg) >= 4:
                parts.append(seg[-1])
    return cats, parts


def hint(products):
    """→ dict：材质大类、部位、硬信号推荐分类（无则 None）、强度。"""
    cats, parts = parse(products)
    strong = [STRONG[c] for c in cats if c in STRONG]
    weak = [WEAK[c] for c in cats if c in WEAK]
    return {
        'material_categories': cats,
        'material_parts': parts,
        # 硬信号：命中即应优先采用，优先级高于从备注文字猜材质
        'category_hint': strong[0] if strong else None,
        'category_hint_strength': 'strong' if strong else ('weak' if weak else None),
        'weak_hints': weak or None,
    }
