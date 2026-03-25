<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, computed, watch, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/api/http'

// ── 响应式状态 ────────────────────────────────────
const lastShippedDate = ref('')   // 数据库中最新的发货日期

const existingDatesArr = ref([])           // 已有数据的日期列表
const calendarDate     = ref(new Date())  // el-calendar 当前显示月份

// 2024-01-01 到 lastShippedDate 之间缺失日期，普通 ref 数组
const missingDates = ref([])
const missingCount = computed(() => missingDates.value.length)

watch(
  [lastShippedDate, existingDatesArr],
  ([last, existing]) => {
    if (!last) { missingDates.value = []; return }
    const existingSet = new Set(existing)
    const result = []
    const cur = new Date(2024, 0, 1)   // 本地时间，避免 UTC 解析偏移
    const [ey, em, ed] = last.split('-').map(Number)
    const end = new Date(ey, em - 1, ed)
    while (cur <= end) {
      const s = `${cur.getFullYear()}-${String(cur.getMonth()+1).padStart(2,'0')}-${String(cur.getDate()).padStart(2,'0')}`
      if (!existingSet.has(s)) result.push(s)
      cur.setDate(cur.getDate() + 1)
    }
    missingDates.value = result
  },
  { immediate: true },
)

// 加载完成后将日历跳到最新数据所在月份
watch(lastShippedDate, (val) => {
  if (val) calendarDate.value = new Date(val + 'T00:00:00')
})

// ── 日历导航 ──────────────────────────────────────

// 年份列表（2024 ~ 今年+1）
const years = computed(() => {
  const cur = new Date().getFullYear()
  const arr = []
  for (let y = 2024; y <= cur + 1; y++) arr.push(y)
  return arr
})

// 当前显示年份（双向）
const calYear = computed({
  get: () => calendarDate.value.getFullYear(),
  set: (y) => { calendarDate.value = new Date(y, calendarDate.value.getMonth(), 1) },
})

// 当前显示月份（双向，1-12）
const calMonth = computed({
  get: () => calendarDate.value.getMonth() + 1,
  set: (m) => { calendarDate.value = new Date(calendarDate.value.getFullYear(), m - 1, 1) },
})

function prevMonth() {
  calendarDate.value = new Date(calYear.value, calMonth.value - 2, 1)
}
function nextMonth() {
  calendarDate.value = new Date(calYear.value, calMonth.value, 1)
}

// 自定义日历网格：直接从 missingDates ref 数组生成，绕开 el-calendar slot 响应性问题
const calCells = computed(() => {
  const year  = calYear.value
  const month = calMonth.value - 1                         // 0-based
  const firstWeekDay = new Date(year, month, 1).getDay()   // 0=周日
  const daysInMonth  = new Date(year, month + 1, 0).getDate()
  const missingSet   = new Set(missingDates.value)

  const cells = []
  // 月初前补空格
  for (let i = 0; i < firstWeekDay; i++) cells.push({ d: null, missing: false })
  // 当月每一天
  for (let d = 1; d <= daysInMonth; d++) {
    const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`
    cells.push({ d, missing: missingSet.has(dateStr) })
  }
  // 末尾补齐到 7 的倍数
  while (cells.length % 7 !== 0) cells.push({ d: null, missing: false })
  return cells
})


const file      = ref(null)
const fileName  = ref('')
const loading   = ref(false)
const result    = ref(null)   // { total, inserted, skipped, skipped_rows }
const fileInput = ref(null)

// 进度状态
const progress      = ref(0)    // 0-100
const phaseLabel    = ref('')
const phaseDetail   = ref('')

// 取消导入
const currentTaskId    = ref('')
const isCancelling     = ref(false)

// 跳过记录弹窗
const showSkippedDialog = ref(false)
const skippedRows       = ref([])

// 文件内合并弹窗
const showMergedDialog = ref(false)
const mergedRows       = ref([])

// 错误弹窗
const showErrorDialog = ref(false)
const errorMessage    = ref('')

// ── 生命周期 ──────────────────────────────────────
onMounted(async () => {
  await refreshDateInfo()
})

// ── 方法 ──────────────────────────────────────────

// 刷新最新发货日期与已有日期列表
async function refreshDateInfo() {
  try {
    const [statsRes, datesRes] = await Promise.all([
      http.get('/api/shipping/stats'),
      http.get('/api/shipping/shipped-dates'),
    ])
    if (statsRes.success) lastShippedDate.value = statsRes.data.last_shipped_date || ''
    if (datesRes.success) existingDatesArr.value = datesRes.data
  } catch {}
}

// 错误用 dialog 展示，不自动消失
function showError(msg) {
  errorMessage.value    = msg || '未知错误'
  showErrorDialog.value = true
  progress.value        = 0   // 隐藏进度条
}

async function cancelImport() {
  if (!currentTaskId.value || isCancelling.value) return
  isCancelling.value = true
  try {
    await http.post(`/api/shipping/import/cancel/${currentTaskId.value}`)
  } catch {}
  // 后台线程收到信号后会推送 cancelled 事件，SSE 回调里处理后续重置
}

function onFileChange(e) {
  const f = e.target.files?.[0]
  if (!f) return
  const name = f.name.toLowerCase()
  if (!['.xlsx', '.xls', '.csv'].some(ext => name.endsWith(ext))) {
    ElMessage.warning('仅支持 .xlsx / .xls / .csv 格式')
    return
  }
  file.value        = f
  fileName.value    = f.name
  result.value      = null
  progress.value    = 0
  phaseLabel.value  = ''
  phaseDetail.value = ''
  // 重置 input，允许重复选同一文件
  e.target.value = ''
}

// 根据进度事件更新进度条与阶段文字
function handleEvent(data) {
  switch (data.step) {
    case 'parsing':
      phaseLabel.value  = '正在解析文件...'
      phaseDetail.value = ''
      progress.value    = 8
      break
    case 'parsed':
      phaseLabel.value  = '文件解析完成'
      phaseDetail.value = `共 ${data.total} 行数据`
      progress.value    = 25
      break
    case 'inserting':
      phaseLabel.value  = '正在写入数据库...'
      phaseDetail.value = data.total ? `${data.current} / ${data.total} 条` : ''
      progress.value    = data.total
        ? 35 + Math.round((data.current / data.total) * 20)
        : 35
      break
    case 'inserted':
      phaseLabel.value  = '数据写入完成'
      phaseDetail.value = `新增 ${data.inserted} 条，跳过 ${data.skipped} 条`
      progress.value    = 55
      break
    case 'resolving': {
      const pct = data.total > 0 ? Math.round((data.current / data.total) * 100) : 0
      phaseLabel.value  = '正在匹配成品组合...'
      phaseDetail.value = `${data.current} / ${data.total} 个订单`
      progress.value    = 55 + Math.round(pct * 0.42)
      break
    }
    case 'done':
      phaseLabel.value  = '导入完成'
      phaseDetail.value = ''
      progress.value    = 100
      break
  }
}

async function doImport() {
  if (!file.value) { ElMessage.warning('请先选择文件'); return }
  loading.value      = true
  isCancelling.value = false
  currentTaskId.value = ''
  result.value       = null
  progress.value     = 0
  phaseLabel.value   = '上传文件...'
  phaseDetail.value  = ''

  let wasCancelled = false
  try {
    // Step 1：上传文件，获取 task_id
    const form = new FormData()
    form.append('file', file.value)
    const res = await http.post('/api/shipping/import/shipping', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    if (!res.success) { showError(res.message || '上传失败'); return }

    currentTaskId.value = res.data.task_id
    progress.value = 5

    // Step 2：订阅 SSE 进度流
    await new Promise((resolve, reject) => {
      const es = new EventSource(`http://127.0.0.1:8765/api/shipping/import/progress/${currentTaskId.value}`)

      es.onmessage = (event) => {
        const data = JSON.parse(event.data)
        handleEvent(data)
        if (data.step === 'done') {
          result.value = data.data
          es.close()
          resolve()
        } else if (data.step === 'cancelled') {
          wasCancelled = true
          es.close()
          resolve()
        } else if (data.step === 'error') {
          es.close()
          reject(new Error(data.message || '导入失败'))
        }
      }

      es.onerror = () => { es.close(); reject(new Error('SSE 连接中断，请重试')) }
    })

    if (wasCancelled) {
      ElMessage.info('导入已中止，已回滚')
    } else if (result.value) {
      ElMessage.success('导入成功')
      // 有跳过记录则弹出明细
      if (result.value.skipped_rows?.length) {
        skippedRows.value       = result.value.skipped_rows
        showSkippedDialog.value = true
      }
      mergedRows.value = result.value.merged_away_rows || []
      await refreshDateInfo()
    }
  } catch (e) {
    showError(e.message || '导入失败')
  } finally {
    loading.value       = false
    isCancelling.value  = false
    currentTaskId.value = ''
  }
}
</script>

<template>
  <div class="data-import">

    <div class="import-header">
      <div class="import-title">导入发货清单</div>
      <div class="import-sub">支持 .xlsx / .xls / .csv 格式，重复记录自动跳过</div>
    </div>

    <!-- 文件选择区 -->
    <div
      class="file-zone"
      :class="{ selected: fileName, disabled: loading }"
      @click="!loading && fileInput.click()"
    >
      <input
        ref="fileInput"
        type="file"
        accept=".xlsx,.xls,.csv"
        style="display:none"
        @change="onFileChange"
      />
      <div v-if="!fileName" class="file-zone-hint">
        <div class="file-zone-icon">📂</div>
        <div>点击选择文件</div>
        <div class="file-zone-ext">.xlsx / .xls / .csv</div>
      </div>
      <div v-else class="file-zone-name">
        <!-- Excel SVG 图标 -->
        <svg class="file-icon-excel" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <rect width="24" height="24" rx="4" fill="#1D6F42"/>
          <path d="M13 3H7a1 1 0 00-1 1v16a1 1 0 001 1h10a1 1 0 001-1V9l-5-6z" fill="#fff" fill-opacity=".15"/>
          <path d="M13 3v6h5" stroke="#fff" stroke-opacity=".5" stroke-width="1" fill="none"/>
          <text x="4" y="19" font-size="7.5" font-weight="700" fill="#fff" font-family="Arial,sans-serif">XLS</text>
        </svg>
        <span class="file-name-text">{{ fileName }}</span>
        <span class="file-change">点击更换</span>
      </div>
    </div>

    <!-- 导入 / 取消 按钮 -->
    <div class="btn-row">
      <button class="import-btn" :disabled="!file || loading" @click="doImport">
        {{ loading ? '导入中…' : '开始导入' }}
      </button>
      <button v-if="loading" class="cancel-btn" :disabled="isCancelling" @click="cancelImport">
        {{ isCancelling ? '中止中…' : '中止导入' }}
      </button>
    </div>

    <!-- 当前数据截至日期 -->
    <div v-if="lastShippedDate && !loading" class="last-date-badge">
      <span class="last-date-label">当前数据截至</span>
      <span class="last-date-value">{{ lastShippedDate }}</span>
    </div>

    <!-- 缺失日期日历 -->
    <div v-if="lastShippedDate && !loading" class="missing-wrap">
      <div class="missing-header">
        <span class="missing-title">缺失日期</span>
        <span v-if="missingCount > 0" class="missing-count-badge">{{ missingCount }} 天</span>
        <span v-else class="missing-none">数据完整 ✓</span>
      </div>
      <!-- 导航 -->
      <div class="cal-nav">
        <button class="cal-nav-btn" @click="prevMonth">‹</button>
        <div class="cal-nav-selects">
          <el-select v-model="calYear" size="small" style="width:80px">
            <el-option v-for="y in years" :key="y" :value="y" :label="y + '年'" />
          </el-select>
          <el-select v-model="calMonth" size="small" style="width:66px">
            <el-option v-for="m in 12" :key="m" :value="m" :label="m + '月'" />
          </el-select>
        </div>
        <button class="cal-nav-btn" @click="nextMonth">›</button>
      </div>
      <!-- 星期标题 -->
      <div class="cal-weekdays">
        <span v-for="wd in ['日','一','二','三','四','五','六']" :key="wd">{{ wd }}</span>
      </div>
      <!-- 日期网格：直接用 calCells computed，避免 el-calendar slot 响应性问题 -->
      <div class="cal-days">
        <span
          v-for="(cell, i) in calCells"
          :key="i"
          :class="['cal-cell', { 'cal-cell--empty': !cell.d }]"
        >
          <span :class="['cal-inner', { 'cal-inner--missing': cell.missing }]">
            {{ cell.d ?? '' }}
          </span>
        </span>
      </div>
    </div>

    <!-- 进度条 -->
    <div v-if="loading || (progress > 0 && progress < 100 && !result)" class="progress-wrap">
      <div class="progress-bar-bg">
        <div class="progress-bar-fill" :style="{ width: progress + '%' }"></div>
      </div>
      <div class="progress-info">
        <span class="progress-phase">{{ phaseLabel }}</span>
        <span v-if="phaseDetail" class="progress-detail">{{ phaseDetail }}</span>
        <span class="progress-pct">{{ progress }}%</span>
      </div>
    </div>

    <!-- 结果卡片 -->
    <div v-if="result" class="result-wrap">
      <div class="result-title">导入完成</div>
      <div class="result-cards">
        <div class="result-card">
          <div class="rc-val">{{ result.total }}</div>
          <div class="rc-lbl">文件行数</div>
        </div>
        <div class="result-card accent">
          <div class="rc-val">{{ result.inserted }}</div>
          <div class="rc-lbl">新增记录</div>
        </div>
        <div class="result-card">
          <div class="rc-val">{{ result.skipped }}</div>
          <div class="rc-lbl">跳过重复</div>
        </div>
        <div v-if="result.merged_away > 0" class="result-card clickable" @click="showMergedDialog = true">
          <div class="rc-val">{{ result.merged_away }}</div>
          <div class="rc-lbl">文件内合并 ›</div>
        </div>
      </div>
      <div v-if="result.inserted > 0" class="result-hint">
        已自动对新订单执行成品组合匹配
      </div>
    </div>

    <!-- 错误弹窗 -->
    <el-dialog
      v-model="showErrorDialog"
      title="导入失败"
      width="480px"
      :close-on-click-modal="false"
    >
      <div class="error-dialog-body">{{ errorMessage }}</div>
      <template #footer>
        <el-button type="primary" @click="showErrorDialog = false">确定</el-button>
      </template>
    </el-dialog>

    <!-- 文件内合并弹窗 -->
    <el-dialog
      v-model="showMergedDialog"
      title="文件内合并消除的行（数量已累加到对应行）"
      width="1100px"
      :close-on-click-modal="false"
    >
      <el-table :data="mergedRows" size="small" border max-height="460">
        <el-table-column prop="ecommerce_order_no" label="电商订单号"   min-width="150" show-overflow-tooltip />
        <el-table-column prop="line_no"            label="项次"         width="55"  align="center" />
        <el-table-column prop="shipped_date"       label="发货日期"     width="96"  align="center" />
        <el-table-column prop="channel_name"       label="渠道名称"     min-width="90"  show-overflow-tooltip />
        <el-table-column prop="channel_code"       label="渠道商"       min-width="80"  show-overflow-tooltip />
        <el-table-column prop="channel_org_name"   label="渠道商名称"   min-width="110" show-overflow-tooltip />
        <el-table-column prop="operator"           label="最近操作人"   width="90"  show-overflow-tooltip />
        <el-table-column prop="product_code"       label="商品型号"     min-width="120" show-overflow-tooltip />
        <el-table-column prop="product_name"       label="商品名称"     min-width="150" show-overflow-tooltip />
        <el-table-column prop="spec"               label="规格"         min-width="90"  show-overflow-tooltip />
        <el-table-column prop="quantity"           label="数量"         width="65"  align="right" />
        <el-table-column prop="country"            label="国家"         width="65"  show-overflow-tooltip />
        <el-table-column prop="province"           label="省份"         width="75"  show-overflow-tooltip />
        <el-table-column prop="city"               label="市区"         width="75"  show-overflow-tooltip />
        <el-table-column prop="district"           label="县区"         width="75"  show-overflow-tooltip />
        <el-table-column prop="street"             label="街道"         min-width="90"  show-overflow-tooltip />
        <el-table-column prop="address"            label="详细地址"     min-width="150" show-overflow-tooltip />
        <el-table-column prop="buyer_remark"       label="买家留言"     min-width="120" show-overflow-tooltip />
        <el-table-column prop="seller_remark"      label="商家备注"     min-width="120" show-overflow-tooltip />
      </el-table>
      <template #footer>
        <span style="font-size:12px; color:var(--text-muted); margin-right:auto;">
          共 {{ mergedRows.length }} 条
        </span>
        <el-button @click="showMergedDialog = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 跳过记录弹窗 -->
    <el-dialog
      v-model="showSkippedDialog"
      title="以下记录已存在于数据库，已跳过"
      width="820px"
      :close-on-click-modal="false"
    >
      <el-table :data="skippedRows" size="small" border max-height="420">
        <el-table-column prop="ecommerce_order_no" label="电商订单号"  min-width="160" show-overflow-tooltip />
        <el-table-column prop="line_no"            label="项次"        width="60"  align="center" />
        <el-table-column prop="product_code"       label="商品型号"    min-width="130" show-overflow-tooltip />
        <el-table-column prop="product_name"       label="商品名称"    min-width="160" show-overflow-tooltip />
        <el-table-column prop="quantity"           label="数量"        width="70"  align="right" />
        <el-table-column prop="shipped_date"       label="发货日期"    width="100" align="center" />
        <el-table-column prop="channel_name"       label="渠道"        min-width="100" show-overflow-tooltip />
        <el-table-column prop="operator"           label="最近操作人"  width="100" show-overflow-tooltip />
        <el-table-column prop="province"           label="省份"        width="80"  show-overflow-tooltip />
      </el-table>
      <template #footer>
        <span style="font-size:12px; color:var(--text-muted); margin-right:auto;">
          共 {{ skippedRows.length }} 条
        </span>
        <el-button @click="showSkippedDialog = false">关闭</el-button>
      </template>
    </el-dialog>

  </div>
</template>

<style scoped>
.data-import {
  max-width: 560px;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.import-header {}
.import-title { font-size: 16px; font-weight: 600; color: var(--text-primary); margin-bottom: 4px; }
.import-sub   { font-size: 12px; color: var(--text-muted); }

.last-date-badge {
  display: flex;
  align-items: baseline;
  justify-content: center;
  gap: 12px;
}
.last-date-label {
  font-size: 14px;
  color: var(--text-muted);
  white-space: nowrap;
}
.last-date-value {
  font-size: 36px;
  font-weight: 800;
  color: var(--accent);
  font-family: monospace;
  letter-spacing: 0.04em;
}

/* 文件选择区 */
.file-zone {
  border: 1.5px dashed var(--border);
  border-radius: 12px;
  padding: 0 24px;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer;
  transition: all 0.18s;
  background: var(--bg);
  height: 100px;   /* 固定高度，选文件后不撑开 */
  flex-shrink: 0;
}
.file-zone:hover:not(.disabled) { border-color: var(--accent); background: rgba(196,136,58,0.03); }
.file-zone.selected { border-style: solid; border-color: var(--accent); }
.file-zone.disabled { opacity: 0.5; cursor: not-allowed; }

.file-zone-hint {
  display: flex; flex-direction: column; align-items: center; gap: 6px;
  color: var(--text-muted); font-size: 13px;
}
.file-zone-icon { font-size: 32px; }
.file-zone-ext  { font-size: 11px; opacity: 0.6; }

.file-zone-name {
  display: flex; align-items: center; gap: 10px;
  width: 100%;
}
.file-icon-excel { width: 32px; height: 32px; flex-shrink: 0; }
.file-name-text  { flex: 1; font-size: 13px; color: var(--text-primary); word-break: break-all; }
.file-change     { font-size: 11px; color: var(--text-muted); flex-shrink: 0; white-space: nowrap; }

/* 错误 */
.import-error {
  font-size: 12px; color: #d05a3c;
  padding: 8px 12px;
  background: rgba(208,90,60,0.06);
  border-radius: 8px;
  border: 1px solid rgba(208,90,60,0.2);
}

/* 按钮行 */
.btn-row {
  display: flex; gap: 10px;
}

/* 导入按钮 */
.import-btn {
  flex: 1;
  padding: 11px 0;
  background: var(--accent); color: #fff;
  border: none; border-radius: 8px;
  font-size: 13px; font-weight: 500; font-family: inherit;
  cursor: pointer; transition: background 0.18s;
}
.import-btn:hover:not(:disabled) { background: var(--accent-hover); }
.import-btn:disabled { opacity: 0.45; cursor: not-allowed; }

/* 中止按钮 */
.cancel-btn {
  padding: 11px 18px;
  background: transparent;
  color: #c06030; border: 1px solid #c06030;
  border-radius: 8px;
  font-size: 13px; font-weight: 500; font-family: inherit;
  cursor: pointer; transition: all 0.18s; white-space: nowrap;
}
.cancel-btn:hover:not(:disabled) { background: rgba(192,96,48,0.06); }
.cancel-btn:disabled { opacity: 0.45; cursor: not-allowed; }

/* 进度条 */
.progress-wrap {
  display: flex; flex-direction: column; gap: 8px;
}
.progress-bar-bg {
  height: 6px;
  background: var(--border);
  border-radius: 3px;
  overflow: hidden;
}
.progress-bar-fill {
  height: 100%;
  background: var(--accent);
  border-radius: 3px;
  transition: width 0.4s cubic-bezier(0.16, 1, 0.3, 1);
}
.progress-info {
  display: flex; align-items: center; gap: 8px;
  font-size: 12px;
}
.progress-phase  { color: var(--text-primary); font-weight: 500; }
.progress-detail { color: var(--text-muted); flex: 1; }
.progress-pct    { color: var(--text-muted); margin-left: auto; font-family: monospace; }

/* 结果 */
.result-wrap {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 20px;
}
.result-title { font-size: 13px; font-weight: 600; color: var(--text-primary); margin-bottom: 14px; }
.result-cards {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px;
  margin-bottom: 12px;
}
.result-card {
  background: var(--bg); border: 1px solid var(--border);
  border-radius: 10px; padding: 14px 10px; text-align: center;
}
.result-card.accent   { border-color: rgba(196,136,58,0.3); }
.result-card.clickable { cursor: pointer; transition: border-color 0.15s, box-shadow 0.15s; }
.result-card.clickable:hover { border-color: var(--accent); box-shadow: 0 0 0 2px rgba(196,136,58,0.12); }
.rc-val { font-size: 28px; font-weight: 700; color: var(--text-primary); }
.result-card.accent .rc-val { color: var(--accent); }
.rc-lbl { font-size: 11px; color: var(--text-muted); margin-top: 4px; }

.result-hint { font-size: 12px; color: var(--text-muted); }

.error-dialog-body {
  font-size: 13px; color: var(--text-primary);
  line-height: 1.7; word-break: break-all;
  max-height: 300px; overflow-y: auto;
}

/* 缺失日期日历 */
.missing-wrap {
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
}
.missing-header {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 14px;
  background: var(--bg-card);
  border-bottom: 1px solid var(--border);
}
.missing-title {
  font-size: 13px; font-weight: 600; color: var(--text-primary);
}
.missing-count-badge {
  display: inline-flex; align-items: center; justify-content: center;
  height: 18px; padding: 0 7px;
  background: rgba(192,96,48,0.1); border-radius: 9px;
  font-size: 11px; font-weight: 600; color: #c06030;
}
.missing-none {
  font-size: 12px; color: #4a9a5a;
}

/* 自定义导航栏 */
.cal-nav {
  display: flex; align-items: center; justify-content: space-between;
  padding: 8px 14px;
  width: 100%;
}
.cal-nav-selects { display: flex; align-items: center; gap: 6px; }
.cal-nav-btn {
  width: 28px; height: 28px; border-radius: 7px;
  border: 1px solid var(--border); background: transparent;
  color: var(--text-muted); font-size: 16px; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: all 0.15s;
}
.cal-nav-btn:hover { border-color: var(--accent); color: var(--accent); }

/* 自定义日历网格 */
.cal-weekdays {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  padding: 4px 14px 6px;
  font-size: 13px;
  font-weight: 700;
  color: var(--text-secondary, #6b5e4e);
  text-align: center;
  border-bottom: 1px solid var(--border);
  margin-bottom: 4px;
}
.cal-weekdays span {
  padding: 6px 0;
}
.cal-days {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  padding: 4px 14px 14px;
}
.cal-cell {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 44px;
  cursor: default;
}
.cal-cell--empty { pointer-events: none; }

.cal-inner {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  font-size: 14px;
  color: var(--text-primary);
  transition: background 0.15s;
}
.cal-cell:not(.cal-cell--empty):hover .cal-inner:not(.cal-inner--missing) {
  background: var(--border);
}
.cal-inner--missing {
  background: #e53935;
  color: #fff;
  font-weight: 700;
}

</style>
