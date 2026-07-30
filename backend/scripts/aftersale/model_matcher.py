"""售后工单型号匹配器（确定性规则实现）。

复现人工处理工单时的型号选择规则，样本外验证：2026-03 系列层 88.4% / 型号层 67.6%
（调参月 2026-02 为 85.4% / 70.1%，说明未过拟合）。

规则来源（用户口述）+ 三条经实测确定的解读：
1. 剔除纯外贸型号（market == 'foreign'），保留 domestic / both / 空值
   —— 内外销共有产品确实参与售后（全历史 11 条）。
2. 从备注抽取显式参数（系列/版本/尺寸/材料/颜色/升降方式）逐级收窄候选；
   某参数收窄为空则忽略该参数，避免过滤到 0。
3. 生命周期比对用【备注里的购买日期】而非工单发货日期
   —— 用发货日期反而比不过滤更差（客户当年购买、现已退市的型号会被错误排除）。
4. "缺项取第一个" = 取【历史频次最高】的变体（频次须来自不含持出月的参考集）。

注意：型号层人工标注本身含噪声（如备注写"理想105"却标成 090），
因此评估应以系列层为主指标。
"""
import re
from collections import Counter

# 括号全半角混用是字典里的既有脏数据（如 '蜻蜓 (V1.2）'），四种组合都要认，
# 否则系列名剥不干净 → 与备注抽出的系列名对不上 → 收窄失败 → 掉回全局最高频
VER_RE = re.compile(r'[（(]\s*V(\d+(?:\.\d+)?)\s*[）)]')
SIZE_RE = re.compile(r'(\d+(?:\.\d+)?)米')
DATE_RE = re.compile(r'(20\d{2})[.\-/年](\d{1,2})[.\-/月]?(\d{1,2})?')
LIFT_WORDS = {'手摇', '电动', '落地', '夹式', '夹子', '底座', '固定'}
PARAM_ORDER = ('series', 'version', 'size', 'color', 'material', 'lift')

# 备注里的写法 → 系统系列名。录入人员的简称、销售名与系统录入名不统一造成的
# 大量未匹配，必须显式对齐（长的写法放前面，匹配时优先）。
SERIES_ALIASES = [
    ('领航员Z', '领航员Z'), ('领航Z', '领航员Z'),
    ('领航员S阳光版', '领航员S阳光版'),
    ('领航员S', '领航员S'), ('领航S', '领航员S'),
    ('领航员A', '领航员A'), ('领航A', '领航员A'),
    ('领航员', '领航员'), ('领航', '领航员'),
]


class ModelMatcher:
    def __init__(self, models, reference_rows):
        """models: models-with-lifecycle.json；reference_rows: 不含持出月的已确认原因行"""
        self.pool = [m for m in models if (m.get('market') or '') != 'foreign']
        self.freq = Counter(r['model_code'] for r in reference_rows if r.get('model_code'))
        self.params = {m['model_code']: self._model_params(m) for m in self.pool}
        self.vocab = self._build_vocab(models)

    @staticmethod
    def _build_vocab(models):
        v = {'series': set(), 'size': set(), 'color': set(), 'material': set()}
        for m in models:
            segs = (m.get('model_name') or '').split('_')
            if segs:
                v['series'].add(VER_RE.sub('', segs[0]).strip())
            for s in segs:
                if SIZE_RE.fullmatch(s):
                    v['size'].add(SIZE_RE.fullmatch(s).group(1))
                elif s.endswith('色'):
                    v['color'].add(s)
                elif '木' in s or s == '微麻白':
                    v['material'].add(s)
        return v

    @staticmethod
    def _model_params(m):
        segs = (m.get('model_name') or '').split('_')
        s0 = segs[0] if segs else ''
        mv = VER_RE.search(s0)
        p = {'series': VER_RE.sub('', s0).strip(), 'version': mv.group(1) if mv else None}
        for s in segs:
            if SIZE_RE.fullmatch(s):
                p['size'] = SIZE_RE.fullmatch(s).group(1)
            elif s in LIFT_WORDS:
                p['lift'] = s
            elif s.endswith('色'):
                p['color'] = s
            elif '木' in s or s == '微麻白':
                p['material'] = s
        tail = (m.get('model_code') or '').rsplit('-', 1)[-1]
        p['suffix'] = tail if re.fullmatch(r'[A-Z]', tail) else 'Z'
        return p

    @staticmethod
    def purchase_ym(text):
        """备注开头的购买日期 → 'YYYY-MM'"""
        m = DATE_RE.search(text or '')
        return f'{m.group(1)}-{int(m.group(2)):02d}' if m else None

    def parse_remark(self, text):
        """抽取备注里显式出现的参数。只认字面，不做语义猜测。"""
        t = text or ''
        got = {}
        # 先按别名表匹配（覆盖录入简称/销售名），命中即用其规范系列名
        for alias, canon in SERIES_ALIASES:
            if alias in t and canon in self.vocab['series']:
                got['series'] = canon
                break
        else:
            hits = sorted([s for s in self.vocab['series'] if s and s in t],
                          key=len, reverse=True)
            if hits:
                got['series'] = hits[0]
        # 先抠掉购买日期，否则 '2023.11' 会被当成版本号 3.1
        cleaned = DATE_RE.sub(' ', t)
        mv = (re.search(r'V\s*(\d+\.\d+)', t)
              # 裸数字当版本号时，必须排除紧跟 米/m 的（那是尺寸，如 '领航员PRO1.2米'）
              or re.search(r'(?<![\d.])(\d\.\d)(?![\d])(?!\s*[米mM])', cleaned))
        if mv:
            got['version'] = mv.group(1)
        ms = SIZE_RE.search(t)
        if ms:
            got['size'] = ms.group(1)
        else:
            mc = re.search(r'(?<!\d)(\d{3})(?!\d)', cleaned)
            if mc and 60 <= int(mc.group(1)) <= 200:
                got['size'] = str(int(mc.group(1)) / 100)
        for c in sorted(self.vocab['color'], key=len, reverse=True):
            if c in t:
                got['color'] = c
                break
        else:
            for ch, full in (('蓝', '蓝色'), ('绿', '绿色'), ('粉', '粉色'),
                             ('黄', '黄色'), ('灰', '灰色')):
                if ch in t:
                    got['color'] = full
                    break
        for mt in sorted(self.vocab['material'], key=len, reverse=True):
            if mt in t:
                got['material'] = mt
                break
        for lf in LIFT_WORDS:
            if lf in t:
                got['lift'] = lf
                break
        return got

    @staticmethod
    def _alive(m, ym):
        if not ym:
            return True
        lo, hi = m.get('listed_yymm'), m.get('delisted_yymm')
        return not ((lo and ym < lo) or (hi and ym > hi))

    def match(self, remark_text):
        """→ (model_code 或 None, 抽到的参数dict, 候选数)"""
        got = self.parse_remark(remark_text)
        cands = self.pool
        for key in PARAM_ORDER:
            if key not in got:
                continue
            nxt = [m for m in cands if self.params[m['model_code']].get(key) == got[key]]
            if nxt:
                cands = nxt
        alive = [m for m in cands if self._alive(m, self.purchase_ym(remark_text))]
        if alive:
            cands = alive
        if not cands:
            return None, got, 0
        pick = sorted(cands, key=lambda m: (
            -self.freq.get(m['model_code'], 0),
            self.params[m['model_code']]['suffix'],
            m['model_id'],
        ))[0]
        return pick['model_code'], got, len(cands)
