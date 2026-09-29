<script setup>
// ── 导入 ──────────────────────────────────────────
// 有研发 BOM 的物料的成本视图（仅 material:price）：成本 + 开始计价 + 完整度，
// 页签：成本变化（按采购订单逐单重算）/ 成本构成（第一层前 5）/ 缺价清单。
// 数据来自 GET /api/material/items/:code/calc-price，由调用方加载后传入。
// 物料卡片和产品库成品卡片共用（2026-09-29 从 MaterialCard 抽出）。
import { ref, computed, watch } from 'vue'
import { TrendCharts } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/api/http'
import { usePermission } from '@/composables/usePermission'

const { canEditMaterial } = usePermission()

// ── Props / Emits ─────────────────────────────────
const props = defineProps({
  data:          { type: Object,  required: true },   // calc-price 返回的 data
  trendDisabled: { type: Boolean, default: false },
})
// open-code：点了某个物料的 ERP 编码；changed：标记了不计价，需要重新加载；trend：打开成本趋势
const emit = defineEmits(['open-code', 'changed', 'trend'])

// ── 响应式状态 ────────────────────────────────────
// 页签：history 成本变化 | composition 成本构成 | missing 缺价清单 | '' 收起
// 开始计价后默认展开成本变化；没开始时全部收起（缺价清单可能很长，点开再看）
const tab = ref('')
watch(() => props.data, d => { tab.value = d?.started ? 'history' : '' }, { immediate: true })

// ── 计算属性 ──────────────────────────────────────
// 已计价比例（按原材料种类去重）
const coverage = computed(() => {
  const c = props.data.current
  return c && c.total ? Math.round(c.priced / c.total * 100) : 0
})

// ── 方法 ──────────────────────────────────────────
// 点页签展开；再点当前页签收起
function toggleTab(key) {
  tab.value = tab.value === key ? '' : key
}

// 缺价清单里直接把物料标记为「不计价」（客供件、赠送件等），然后让调用方重算
async function markNoPrice(m) {
  if (!m.erp_code) return
  try {
    await ElMessageBox.confirm(
      `把 ${m.erp_code} ${m.name || ''} 标记为「不计价」？计价时按 0 元、算作已有价格。适用于客供件、赠送件等不会有采购价的物料。`,
      '标记不计价', { type: 'warning', confirmButtonText: '标记', cancelButtonText: '取消' })
  } catch { return }
  const res = await http.put(`/api/material/items/${encodeURIComponent(m.erp_code)}`, { no_price: true })
  if (res.success) {
    ElMessage.success('已标记不计价')
    emit('changed')
  } else {
    ElMessage.error(res.message || '标记失败')
  }
}

function money(v) {
  return v == null ? '—' : '¥' + String(+Number(v).toFixed(4))
}

function signed(v) {
  if (v == null) return '—'
  const n = +Number(v).toFixed(4)
  return (n > 0 ? '+' : n < 0 ? '−' : '') + '¥' + Math.abs(n)
}
</script>

<template>
  <div class="cost-view">
    <div class="cv-head">
      <!-- 齐全才计价：下级价格第一次齐全的那一刻才开始计价，之前不给成本数字 -->
      <template v-if="data.current.unit_price != null">
        <b class="mono cv-val">{{ money(data.current.unit_price) }}</b>
        <span v-if="data.current.price_source === 'own'" class="calc-own"
              title="下级价格不齐全，使用该部件自己的外购价">外购价</span>
        <span v-if="data.started" class="cv-start" title="下级价格第一次齐全的时间">
          开始计价：
          <span v-if="data.started.order_no" class="order-tag mono">{{ data.started.order_no }}</span>
          {{ data.started.date || '' }}
        </span>
      </template>
      <span v-else class="cv-unpriced" title="下级价格齐全后才开始计价">未开始计价</span>
      <span class="cv-bom mono" title="计算依据的研发 BOM 版本">{{ data.bom.drawing }}</span>
      <span class="cv-cover" :title="`已计价 ${data.current.priced} 种 / 共 ${data.current.total} 种原材料（按编码去重）`">
        已计价 <b>{{ data.current.priced }}</b> / {{ data.current.total }} 种原材料
        <span class="cv-bar"><span :style="{ width: coverage + '%' }"></span></span>
        <span class="cv-pct" :class="{ full: coverage === 100 }">{{ coverage }}%</span>
      </span>
      <button class="cost-trend" type="button" :disabled="trendDisabled"
              title="按订单显示成本走势" @click="emit('trend')">
        <el-icon><TrendCharts /></el-icon>成本趋势
      </button>
    </div>

    <div class="cv-tabs">
      <template v-if="data.started">
        <button :class="{ active: tab === 'history' }" @click="toggleTab('history')">
          成本变化（{{ data.history.length }}）</button>
        <button :class="{ active: tab === 'composition' }" @click="toggleTab('composition')">成本构成</button>
      </template>
      <button :class="{ active: tab === 'missing' }" @click="toggleTab('missing')">
        缺价清单（{{ data.missing_items.length }}）</button>
    </div>

    <!-- 成本变化：按采购订单逐单重算 -->
    <template v-if="tab === 'history'">
      <table v-if="data.history.length" class="cost-table cv-table">
        <thead>
          <tr>
            <th>订单</th>
            <th style="width:100px">日期</th>
            <th style="width:110px" class="ta-r">计算成本</th>
            <th style="width:110px" class="ta-r" title="开始计价后下级价格都齐全，这里的变化就是真实的价格涨跌">较上一单</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="h in data.history" :key="h.batch_id">
            <td>
              <span class="order-tag mono" :title="h.order_no">{{ h.order_no || '（无订单号）' }}</span>
              <span v-if="h.related === true" class="rel-tag rel-own" title="这个订单里包含本产品">本产品订单</span>
              <span v-else-if="h.related === false" class="rel-tag rel-shared"
                    title="这个订单里没有本产品，是共用物料的价格更新了">共用物料变价</span>
            </td>
            <td>{{ h.date }}</td>
            <td class="ta-r price-val">{{ money(h.unit_price) }}</td>
            <td class="ta-r mono" :class="{ up: h.delta > 0, down: h.delta < 0 }">
              {{ h.delta == null ? '开始计价' : signed(h.delta) }}
            </td>
          </tr>
        </tbody>
      </table>
      <div v-else class="cost-empty">开始计价后还没有采购订单记录（价格来自手动录入或不计价标记）</div>
    </template>

    <!-- 成本构成：第一层下级按金额排前 5 -->
    <template v-else-if="tab === 'composition'">
      <table v-if="data.composition.length" class="cost-table cv-table">
        <thead>
          <tr><th style="width:150px">图纸编码</th><th>名称</th><th style="width:60px" class="ta-r">用量</th>
              <th style="width:96px" class="ta-r">金额</th><th style="width:150px">占比</th></tr>
        </thead>
        <tbody>
          <tr v-for="c in data.composition" :key="c.drawing">
            <td class="mono">
              <span v-if="c.erp_code" class="bom-link" @click="emit('open-code', c.erp_code)">{{ c.drawing }}</span>
              <span v-else>{{ c.drawing }}</span>
            </td>
            <td class="ellip" :title="c.name">{{ c.name || '—' }}</td>
            <td class="ta-r">{{ c.qty }}</td>
            <td class="ta-r price-val">{{ money(c.amount) }}</td>
            <td>
              <span class="cv-share"><span :style="{ width: ((c.share || 0) * 100) + '%' }"></span></span>
              {{ c.share != null ? (c.share * 100).toFixed(1) + '%' : '—' }}
              <span v-if="c.missing" class="calc-miss" :title="`其中 ${c.missing} 项原材料无价格`">缺{{ c.missing }}</span>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-else class="cost-empty">还没有可计算的金额</div>
    </template>

    <!-- 缺价清单：点 ERP 编码到该物料卡片补价格 -->
    <template v-else-if="tab === 'missing'">
      <table v-if="data.missing_items.length" class="cost-table cv-table">
        <thead>
          <tr><th style="width:150px">图纸编码</th><th style="width:140px">ERP 编码</th><th>名称</th>
              <th style="width:70px" class="ta-r">总用量</th><th style="width:180px">所在部件</th>
              <th v-if="canEditMaterial" style="width:84px"></th></tr>
        </thead>
        <tbody>
          <tr v-for="m in data.missing_items" :key="m.drawing">
            <td class="mono">{{ m.drawing }}</td>
            <td class="mono">
              <span v-if="m.erp_code" class="bom-link" title="到该物料卡片补价格" @click="emit('open-code', m.erp_code)">{{ m.erp_code }}</span>
              <span v-else class="cell-muted">未匹配</span>
            </td>
            <td class="ellip" :title="m.name">{{ m.name || '—' }}</td>
            <td class="ta-r">{{ m.qty }}</td>
            <td class="ellip mono" :title="m.parents.join('、')">{{ m.parents.join('、') }}</td>
            <td v-if="canEditMaterial">
              <button v-if="m.erp_code" class="np-btn" type="button"
                      title="客供件、赠送件等不会有采购价的物料：标记后按 0 元计" @click="markNoPrice(m)">标记不计价</button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-else class="cost-empty">原材料价格已齐全</div>
      <div v-if="data.missing_items.length" class="cv-tip">
        下级价格全部齐全时才开始计价。价格不全时，现有价格大多来自别的产品的订单，合计没有参考意义。
      </div>
    </template>
  </div>
</template>

<style scoped>
.mono { font-family: monospace; font-size: 12px; }
.cost-view {
  margin-bottom: 10px; padding: 10px 12px; border-radius: 8px;
  background: rgba(74,143,192,0.05); border: 1px solid rgba(74,143,192,0.25);
}
.cv-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.cv-val { font-size: 18px; color: #4a8fc0; }
.cv-bom { font-size: 12px; color: #6b5e4e; }
.cv-cover { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: #6b5e4e; }
.cv-cover b { color: #2c2420; }
.cv-bar, .cv-share {
  display: inline-block; width: 90px; height: 6px; border-radius: 3px; overflow: hidden;
  background: rgba(138,122,106,0.2); vertical-align: middle;
}
.cv-bar > span, .cv-share > span { display: block; height: 100%; background: #4a8fc0; border-radius: 3px; }
.cv-share { width: 60px; margin-right: 4px; }
.cv-pct { font-weight: 600; color: #c0782a; }
.cv-pct.full { color: #4a8f6a; }
.cv-head .cost-trend { margin-left: auto; }
.cv-tabs { display: flex; gap: 6px; margin: 10px 0 6px; }
.cv-tabs button {
  padding: 3px 12px; border-radius: 7px; border: 1px solid var(--border);
  background: #fff; color: #6b5e4e; font-size: 12px; font-family: inherit; cursor: pointer;
}
.cv-tabs button.active { background: var(--accent-bg); border-color: var(--accent); color: var(--accent); font-weight: 600; }
.cv-table td.up { color: #d05a3c; }
.cv-table td.down { color: #4a8f6a; }
.rel-tag { margin-left: 4px; padding: 0 5px; border-radius: 4px; font-size: 10px; line-height: 16px; display: inline-block; }
.rel-own { color: #4a8f6a; background: rgba(74,143,106,0.12); }
.rel-shared { color: #8a7a6a; background: rgba(138,122,106,0.12); }
.calc-own { padding: 0 6px; border-radius: 4px; font-size: 11px; color: #9c6fba; background: rgba(156,111,186,0.12); }
.calc-miss { padding: 0 6px; border-radius: 4px; font-size: 11px; color: #c0782a; background: rgba(224,144,80,0.15); }
.cv-unpriced { font-size: 15px; font-weight: 600; color: #8a7a6a; }
.cv-start { display: inline-flex; align-items: center; gap: 4px; font-size: 12px; color: #6b5e4e; }
.cv-tip { margin-top: 6px; font-size: 12px; color: #8a7a6a; }
.np-btn {
  padding: 1px 8px; border-radius: 10px; cursor: pointer; white-space: nowrap;
  border: 1px solid var(--border); background: #fff; color: #6b5e4e; font-size: 11px; font-family: inherit;
}
.np-btn:hover { border-color: var(--accent); color: var(--accent); }
/* 订单号 tag：浅蓝底，超长省略（悬停看全文） */
.order-tag {
  display: inline-block; max-width: 160px; vertical-align: middle;
  padding: 0 7px; border-radius: 4px; font-size: 11px; line-height: 18px;
  color: #3d6f94; background: rgba(74,143,192,0.1); border: 1px solid rgba(74,143,192,0.35);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.cost-trend {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 3px 12px; border-radius: 12px; cursor: pointer;
  border: 1px solid var(--accent); background: transparent; color: var(--accent);
  font-size: 12px; font-family: inherit; transition: all 0.15s;
}
.cost-trend:hover:not(:disabled) { background: var(--accent); color: #fff; }
.cost-trend:disabled { opacity: 0.45; cursor: not-allowed; }
.cost-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.cost-table th {
  text-align: left; font-weight: 600; color: var(--text-secondary);
  padding: 6px 8px; border-bottom: 1px solid var(--border); white-space: nowrap;
}
.cost-table td {
  padding: 5px 8px; border-bottom: 1px solid var(--border);
  color: var(--text-primary); vertical-align: middle;
}
.cost-table tr:last-child td { border-bottom: none; }
.ta-r, .cost-table th.ta-r { text-align: right; }
.ellip { max-width: 150px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.price-val { font-family: 'SF Mono', Consolas, monospace; font-weight: 600; }
.cost-empty { padding: 16px 0; text-align: center; font-size: 12px; color: var(--text-secondary); }
.bom-link { cursor: pointer; }
.bom-link:hover { color: var(--accent); text-decoration: underline; }
.cell-muted { color: var(--text-muted); }
</style>
