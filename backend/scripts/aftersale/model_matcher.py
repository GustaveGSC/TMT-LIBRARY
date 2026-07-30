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

# 两类不同的名称对齐，来源不同，都要处理：
#
# 1) 销售名 ↔ 系统名：权威来源是产品标签的「别名」分类（category「别名」），
#    由业务维护，映射到具体【系列编码】（如 领航员Pro → LH21），比按系列名
#    匹配更精确。通过 alias_links 参数传入，不在代码里硬编码。
# 2) 录入简称：录入人员的习惯写法（如把「领航员」写成「领航」），不在别名表里，
#    只能在代码里维护。长写法放前面，匹配时优先。
ENTRY_SHORTHANDS = [
    ('领航员Z', '领航员Z'), ('领航Z', '领航员Z'),
    ('领航员A', '领航员A'), ('领航A', '领航员A'),
    ('领航员S', '领航员S'), ('领航S', '领航员S'),
    ('领航员', '领航员'), ('领航', '领航员'),
    ('学习工厂', '学习工场'),        # 录入常写"厂"，系统名是"场"
    ('大白2代', '大白二代'), ('大白1代', '大白'),   # 阿拉伯数字写法
]

# 同义写法归一：「款」与「版」只是写法不同（用户确认）
def _norm_text(t):
    return (t or '').replace('款', '版')


def _is_foreign(m):
    """是否外贸型号（售后不涉外贸）。market 字段 + 系列标识双信号，缺一会漏。"""
    if (m.get('market') or '') == 'foreign':
        return True
    return ('FTP' in (m.get('series_code') or '')
            or '外贸' in (m.get('series_name') or ''))


class ModelMatcher:
    def __init__(self, models, reference_rows, alias_links=None):
        """models: models-with-lifecycle.json；reference_rows: 不含持出月的已确认原因行；
        alias_links: 别名标签关联行（alias-tags.json 的 links），销售名→系列编码的权威来源"""
        # 外贸判定必须双信号并用：market 字段有空值（8 个型号，其中 1 个
        # JQ43FD120-YL-asknoa-A 属外贸系列却是空值，只看 market 会漏掉）；
        # 反过来也有 1 个 market=foreign 但系列名无外贸标识，只看系列同样会漏。
        self.pool = [m for m in models if not _is_foreign(m)]
        # 别名 → 系列编码集合；按别名长度降序，长的优先（避免"领航员Pro"被"领航员"截断）
        self.alias_series = {}
        for r in (alias_links or []):
            if r.get('alias') and r.get('series_code'):
                self.alias_series.setdefault(r['alias'], set()).add(r['series_code'])
        self.alias_order = sorted(self.alias_series, key=len, reverse=True)
        self.series_code_of = {m['model_code']: m.get('series_code') for m in models}
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
        t = _norm_text(text)
        got = {}
        # ① 先把录入简称展开成规范名（必须在查别名之前：备注写「领航pro」，
        #    而别名表里是「领航员Pro」，不先展开就永远匹配不上）
        expanded = t
        matched_short = None
        for short, canon in ENTRY_SHORTHANDS:
            if short.lower() in expanded.lower():
                expanded = re.sub(re.escape(short), canon, expanded, flags=re.I)
                matched_short = canon
                break
        low = expanded.lower()
        # ② 销售名别名（权威）：命中即锁定到具体系列编码，精度高于按系列名匹配
        for alias in self.alias_order:
            if alias.lower() in low:
                got['series_codes'] = self.alias_series[alias]
                got['_alias'] = alias
                break
        # ③ 系列名：在展开后的文本上对词表取【最长匹配】。
        #    不能因为简称命中就直接用它——例如「领航S阳光款」展开为「领航员S阳光版」后，
        #    词表里既有「领航员S」也有更长的「领航员S阳光版」（独立系列 LY11），必须取长的。
        hits = sorted([s for s in self.vocab['series'] if s and s.lower() in low],
                      key=len, reverse=True)
        if hits:
            got['series'] = hits[0]
        elif matched_short and matched_short in self.vocab['series']:
            got['series'] = matched_short
        # 先抠掉购买日期，否则 '2023.11' 会被当成版本号 3.1
        cleaned = DATE_RE.sub(' ', expanded)
        mv = (re.search(r'V\s*(\d+\.\d+)', expanded)
              # 裸数字当版本号时，必须排除紧跟 米/m 的（那是尺寸，如 '领航员PRO1.2米'）
              or re.search(r'(?<![\d.])(\d\.\d)(?![\d])(?!\s*[米mM])', cleaned))
        if mv:
            got['version'] = mv.group(1)
        ms = SIZE_RE.search(expanded)
        if ms:
            got['size'] = ms.group(1)
        else:
            mc = re.search(r'(?<!\d)(\d{3})(?!\d)', cleaned)
            if mc and 60 <= int(mc.group(1)) <= 200:
                got['size'] = str(int(mc.group(1)) / 100)
        for c in sorted(self.vocab['color'], key=len, reverse=True):
            if c in expanded:
                got['color'] = c
                break
        else:
            for ch, full in (('蓝', '蓝色'), ('绿', '绿色'), ('粉', '粉色'),
                             ('黄', '黄色'), ('灰', '灰色')):
                if ch in expanded:
                    got['color'] = full
                    break
        for mt in sorted(self.vocab['material'], key=len, reverse=True):
            if mt in expanded:
                got['material'] = mt
                break
        for lf in LIFT_WORDS:
            if lf in expanded:
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
        # 别名锁定的系列编码优先收窄（比系列名更精确）
        if got.get('series_codes'):
            nxt = [m for m in cands if self.series_code_of.get(m['model_code']) in got['series_codes']]
            if nxt:
                cands = nxt
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
