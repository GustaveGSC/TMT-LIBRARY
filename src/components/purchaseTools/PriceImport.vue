<script setup>
// ── 导入 ──────────────────────────────────────────
// 采购工具 · 导入价格：上传采购带价格的 BOM → 预览（确认价格日期）→ 导入。
// 只提取原材料单价绑定到物料库（特例：下级全为 0 的半成品导入它自己的价格）；
// 同一日期且同一价格的跳过。半成品/成品价格不导入，由研发 BOM 按计价日期实时计算。
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Upload, WarningFilled, Refresh } from '@element-plus/icons-vue'
import http from '@/api/http'
import { pickFile } from '@/utils/download'
import { usePermission } from '@/composables/usePermission'

// 导入价格要求 material:price（查看入口只要 purchase:view）
const { canMaterialPrice } = usePermission()

// ── 响应式状态 ────────────────────────────────────
const file       = ref(null)      // 当前选中的采购 BOM 文件（改日期时要带着它重新预览）
const preview    = ref(null)      // 后端预览结果
const priceDate  = ref('')        // 确认的价格日期（YYYY-MM-DD）
const previewing = ref(false)
const importing  = ref(false)
const result     = ref(null)      // 最近一次导入结果
const history    = ref([])
const tab        = ref('items')   // items | zero | conflicts

// ── 计算属性 ──────────────────────────────────────
// 同一物料多个不同单价时禁止导入（用户 2026-09-28 定），必须先改 Excel
const hasConflicts = computed(() => !!preview.value?.conflicts?.length)
const canImport = computed(() =>
  canMaterialPrice && !!preview.value && !!priceDate.value && preview.value.new_count > 0
  && !hasConflicts.value && !importing.value)

// ── 方法 ──────────────────────────────────────────
async function chooseFile() {
  const f = await pickFile('.xlsx')
  if (!f) return
  file.value = f
  result.value = null
  priceDate.value = ''
  await runPreview()
}

// 预览：带上已确认的日期（没有则后端用订单号里的日期），据此标出「新增 / 同日同价跳过」
async function runPreview() {
  if (!file.value) return
  const form = new FormData()
  form.append('file', file.value)
  if (priceDate.value) form.append('price_date', priceDate.value)
  previewing.value = true
  try {
    const res = await http.post('/api/purchase/price-import/preview', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    if (res.success) {
      preview.value = res.data
      if (!priceDate.value && res.data.price_date) priceDate.value = res.data.price_date
      tab.value = res.data.conflicts?.length ? 'conflicts' : 'items'
    } else {
      preview.value = null
      ElMessage.error(res.message || '解析失败')
    }
  } catch (e) {
    ElMessage.error(e.message || '网络错误')
  } finally {
    previewing.value = false
  }
}

async function doImport() {
  if (!canImport.value) return
  try {
    await ElMessageBox.confirm(
      `将以价格日期 ${priceDate.value} 导入 ${preview.value.new_count} 条价格` +
      (preview.value.skip_count ? `（同日同价跳过 ${preview.value.skip_count} 条）` : '') + '，确认导入？',
      '确认导入', { type: 'warning', confirmButtonText: '导入', cancelButtonText: '取消' })
  } catch { return }
  const form = new FormData()
  form.append('file', file.value)
  form.append('price_date', priceDate.value)
  importing.value = true
  try {
    const res = await http.post('/api/purchase/price-import', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    if (res.success) {
      result.value = res.data
      preview.value = null
      file.value = null
      ElMessage.success(res.data.created ? `已导入 ${res.data.created} 条价格` : (res.message || "没有新增价格"))
      loadHistory()
    } else {
      ElMessage.error(res.message || '导入失败')
    }
  } catch (e) {
    ElMessage.error(e.message || '网络错误')
  } finally {
    importing.value = false
  }
}

async function loadHistory() {
  try {
    const res = await http.get('/api/purchase/price-import/history')
    if (res.success) history.value = res.data || []
  } catch { /* 历史拿不到不影响导入 */ }
}

function fmtPrice(v) {
  return v == null ? '—' : '¥' + String(+Number(v).toFixed(4))
}

// ── 生命周期 ──────────────────────────────────────
onMounted(() => { if (canMaterialPrice) loadHistory() })
</script>

<template>
  <div class="prc">
    <h1 class="prc-title">导入价格</h1>
    <p class="prc-lead">
      上传采购带价格的 BOM（汇总页 + 每个成品一个 Sheet），提取<b>原材料</b>的单价绑定到物料库；
      下级价格全为 0 的半成品，导入它自己的价格。<b>同一日期且同一价格</b>的会跳过。
      半成品、产成品、成品的价格不导入，在物料BOM 里按计价日期由下级实时计算。
    </p>

    <div v-if="!canMaterialPrice" class="prc-warn">
      <el-icon><WarningFilled /></el-icon>导入价格需要「物料价格」权限（material:price），请联系管理员开通。
    </div>

    <template v-else>
      <!-- 选择文件 -->
      <section class="prc-card">
        <div class="prc-row">
          <el-button type="primary" :icon="Upload" :loading="previewing" @click="chooseFile">选择采购 BOM</el-button>
          <span v-if="file" class="prc-file">{{ file.name }}</span>
          <span v-else class="prc-muted">仅支持 .xlsx</span>
        </div>
      </section>

      <!-- 预览 -->
      <section v-if="preview" v-loading="previewing" class="prc-card">
        <div class="prc-head">
          <div class="prc-field">
            <label>订单号</label><span class="mono">{{ preview.order_no || '（未识别）' }}</span>
          </div>
          <div class="prc-field">
            <label>价格日期 <b>*</b></label>
            <el-date-picker
              v-model="priceDate" type="date" value-format="YYYY-MM-DD" size="small"
              placeholder="请确认价格日期" :clearable="false" class="prc-date" @change="runPreview"
            />
            <span v-if="preview.suggested_date" class="prc-muted">订单号日期：{{ preview.suggested_date }}</span>
            <span v-else class="prc-muted">订单号里没有日期，请手动选择</span>
          </div>
        </div>

        <div class="prc-stats">
          <div><b>{{ preview.new_count }}</b><span>将新增</span></div>
          <div><b>{{ preview.skip_count }}</b><span>同日同价跳过</span></div>
          <div><b>{{ preview.special_semis.length }}</b><span>特例半成品</span></div>
          <div :class="{ warn: preview.zero_items.length }"><b>{{ preview.zero_items.length }}</b><span>原材料无价格</span></div>
          <div :class="{ warn: preview.conflicts.length }"><b>{{ preview.conflicts.length }}</b><span>同物料多单价</span></div>
        </div>
        <div v-if="hasConflicts" class="prc-warn">
          <el-icon><WarningFilled /></el-icon>
          有 {{ preview.conflicts.length }} 个物料在文件里出现了多个不同单价，不能导入。请先在 Excel 里把这些物料的单价改成一致，再重新选择文件。
        </div>
        <div v-for="w in preview.warnings" :key="w" class="prc-warn small">
          <el-icon><WarningFilled /></el-icon>{{ w }}
        </div>

        <div class="prc-tabs">
          <button :class="{ active: tab === 'items' }" @click="tab = 'items'">价格清单（{{ preview.items.length }}）</button>
          <button :class="{ active: tab === 'zero' }" @click="tab = 'zero'">无价格（{{ preview.zero_items.length }}）</button>
          <button :class="{ active: tab === 'conflicts' }" @click="tab = 'conflicts'">多单价（{{ preview.conflicts.length }}）</button>
        </div>

        <el-table v-if="tab === 'items'" :data="preview.items" size="small" border max-height="420" class="prc-table">
          <el-table-column prop="code" label="编码（去版本）" width="150">
            <template #default="{ row }"><span class="mono">{{ row.code }}</span></template>
          </el-table-column>
          <el-table-column prop="name" label="名称" min-width="220" show-overflow-tooltip />
          <el-table-column label="单价" width="100" align="right">
            <template #default="{ row }"><span class="mono">{{ fmtPrice(row.price) }}</span></template>
          </el-table-column>
          <el-table-column label="类型" width="100">
            <template #default="{ row }">
              <span v-if="row.kind === 'semi'" class="tag tag-semi" title="下级价格全为 0，导入半成品自己的价格">特例半成品</span>
              <span v-else class="tag">原材料</span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="110">
            <template #default="{ row }">
              <span v-if="row.status === 'new'" class="tag tag-new">新增</span>
              <span v-else class="tag tag-skip" title="该日期已有相同价格">同日同价跳过</span>
            </template>
          </el-table-column>
          <el-table-column label="物料表" width="80" align="center">
            <template #default="{ row }">
              <span v-if="row.in_erp">有</span>
              <span v-else class="prc-muted" title="物料表里没有这个编码，价格仍会记录">无</span>
            </template>
          </el-table-column>
        </el-table>

        <el-table v-else-if="tab === 'zero'" :data="preview.zero_items" size="small" border max-height="420"
                  class="prc-table" empty-text="所有原材料都有价格">
          <el-table-column prop="code" label="编码（去版本）" width="150">
            <template #default="{ row }"><span class="mono">{{ row.code }}</span></template>
          </el-table-column>
          <el-table-column prop="name" label="名称" min-width="260" show-overflow-tooltip />
          <el-table-column label="说明" min-width="200">
            <template #default>单价为 0 或为空，不导入</template>
          </el-table-column>
        </el-table>

        <el-table v-else :data="preview.conflicts" size="small" border max-height="420"
                  class="prc-table" empty-text="没有同一物料多个单价的情况">
          <el-table-column prop="code" label="编码（去版本）" width="150">
            <template #default="{ row }"><span class="mono">{{ row.code }}</span></template>
          </el-table-column>
          <el-table-column label="文件里出现的单价" min-width="260">
            <template #default="{ row }">{{ row.prices.map(fmtPrice).join('、') }}</template>
          </el-table-column>
        </el-table>

        <div class="prc-actions">
          <span v-if="hasConflicts" class="prc-warn-text">存在同物料多单价，需先修改 Excel</span>
          <span v-else-if="!priceDate" class="prc-warn-text">请先确认价格日期</span>
          <span v-else-if="preview.new_count === 0" class="prc-muted">没有需要新增的价格</span>
          <el-button type="primary" :disabled="!canImport" :loading="importing" @click="doImport">确认导入</el-button>
        </div>
      </section>

      <!-- 导入结果 -->
      <section v-if="result" class="prc-card prc-result">
        已导入：订单 <b class="mono">{{ result.order_no || '—' }}</b>，价格日期 <b>{{ result.price_date }}</b>，
        新增 <b>{{ result.created }}</b> 条，同日同价跳过 <b>{{ result.skipped }}</b> 条
        <template v-if="result.special_semis">，其中特例半成品 {{ result.special_semis }} 个</template>。
      </section>

      <!-- 导入记录 -->
      <section class="prc-card">
        <div class="prc-sub">
          最近导入记录
          <el-button size="small" text :icon="Refresh" @click="loadHistory">刷新</el-button>
        </div>
        <el-table :data="history" size="small" border class="prc-table" empty-text="还没有导入记录">
          <el-table-column label="订单号" min-width="200">
            <template #default="{ row }"><span class="mono">{{ row.order_no || '—' }}</span></template>
          </el-table-column>
          <el-table-column prop="price_date" label="价格日期" width="120" />
          <el-table-column prop="price_count" label="写入价格" width="100" align="right" />
          <el-table-column prop="created_by" label="导入人" width="120" />
          <el-table-column prop="created_at" label="导入时间" width="160" />
        </el-table>
      </section>
    </template>
  </div>
</template>

<style scoped>
.prc { max-width: 1100px; margin: 0 auto; padding: 24px 24px 48px; color: #3a3028; font-size: 14px; }
.prc-title { font-size: 22px; font-weight: 700; color: #2c2420; margin: 0 0 6px; }
.prc-lead { margin: 0 0 14px; line-height: 1.75; color: #3a3028; }
.prc-lead b { color: #2c2420; }
.mono { font-family: 'SF Mono', Consolas, 'Microsoft YaHei UI', monospace; }
.prc-muted { font-size: 12px; color: #8a7a6a; }

.prc-card {
  margin-top: 14px; padding: 16px 18px;
  background: #fff; border: 1px solid #e0d4c0; border-radius: 12px;
}
.prc-row { display: flex; align-items: center; gap: 12px; }
.prc-file { font-weight: 600; color: #2c2420; }

.prc-head { display: flex; flex-wrap: wrap; gap: 12px 32px; margin-bottom: 14px; }
.prc-field { display: flex; align-items: center; gap: 8px; }
.prc-field label { font-size: 13px; color: #6b5e4e; }
.prc-field label b { color: #d05a3c; }
.prc-date { width: 150px; }

.prc-stats { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 12px; }
.prc-stats > div {
  flex: 1; min-width: 110px; text-align: center; padding: 10px 0; border-radius: 10px;
  background: #faf7f2; border: 1px solid #e0d4c0;
}
.prc-stats > div.warn { background: #fff8e6; border-color: #f0d48a; }
.prc-stats b { display: block; font-size: 20px; color: #2c2420; }
.prc-stats span { font-size: 12px; color: #6b5e4e; }

.prc-warn {
  display: flex; align-items: center; gap: 6px; margin-top: 12px; padding: 10px 12px;
  border-radius: 8px; background: #fff8e6; border: 1px solid #f0d48a; color: #8a5a00; font-size: 13px;
}
.prc-warn.small { margin: 0 0 8px; padding: 6px 10px; font-size: 12px; }
.prc-warn-text { font-size: 13px; color: #d05a3c; }

.prc-tabs { display: flex; gap: 6px; margin-bottom: 8px; }
.prc-tabs button {
  padding: 4px 14px; border-radius: 7px; border: 1px solid #e0d4c0;
  background: #fff; color: #6b5e4e; font-size: 13px; font-family: inherit; cursor: pointer;
}
.prc-tabs button.active { background: var(--accent-bg); border-color: var(--accent); color: var(--accent); font-weight: 600; }

.tag {
  display: inline-block; padding: 0 7px; border-radius: 4px; font-size: 11px; line-height: 18px;
  color: #6b5e4e; background: #f5f0e8; border: 1px solid #e0d4c0;
}
.tag-semi { color: #9c6fba; background: rgba(156,111,186,0.1); border-color: rgba(156,111,186,0.4); }
.tag-new { color: #4a8f6a; background: rgba(74,143,106,0.1); border-color: rgba(74,143,106,0.4); }
.tag-skip { color: #8a7a6a; }

.prc-actions { display: flex; align-items: center; justify-content: flex-end; gap: 12px; margin-top: 12px; }
.prc-result { background: #f2f9f4; border-color: rgba(74,143,106,0.4); color: #2c4a36; }
.prc-sub { display: flex; align-items: center; justify-content: space-between; font-weight: 700; color: #2c2420; margin-bottom: 8px; }

@media (max-width: 768px) {
  .prc { padding: 16px 16px 32px; }
}
</style>
