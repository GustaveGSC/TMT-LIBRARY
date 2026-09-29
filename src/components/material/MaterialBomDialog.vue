<script setup>
// ── 导入 ──────────────────────────────────────────
// 研发 BOM 完整结构弹窗：标题（图纸编码/名称/导入信息/导出）+ 筛选 + 计价行（仅 material:price）+ 多层树。
// 物料卡片和产品库成品卡片共用（2026-09-29 从 MaterialCard 抽出）。
// 用法：ref.open(版本行, 筛选词?, 计价批次?)；树里点物料编码时 emit('open-code', code, snapshot)，
// snapshot 记下当前 BOM/筛选词/计价批次，调用方返回时可以用它重新打开。
import { ref } from 'vue'
import { Search, Download, ArrowDown, ArrowUp } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import MaterialBomTree from './MaterialBomTree.vue'
import PriceBatchSelect from './PriceBatchSelect.vue'
import { exportBom } from './bomExport'
import http from '@/api/http'
import { usePermission } from '@/composables/usePermission'

const { canMaterialPrice } = usePermission()

const emit = defineEmits(['open-code'])

// ── 响应式状态 ────────────────────────────────────
const visible    = ref(false)
const head       = ref(null)    // 列表里点的那一条（先用它显示标题，树加载完再合并树接口返回的 bom）
const tree       = ref([])
const loading    = ref(false)
const keyword    = ref('')      // 弹窗内筛选：编码/名称
const priceBatch = ref(null)    // 计价依据的采购导入批次 id：null = 最新价格
const treeRef    = ref(null)    // 读取树组件暴露的匹配数 / 展开状态
const exporting  = ref(false)

// ── 方法 ──────────────────────────────────────────
// 打开某一个研发版本的完整多层结构
async function open(v, kw = '', batch = null) {
  keyword.value = kw
  priceBatch.value = batch
  head.value = v
  tree.value = []
  visible.value = true
  loading.value = true
  try {
    const res = await http.get(`/api/material/boms/${v.id}/tree`,
      { params: priceBatch.value ? { batch_id: priceBatch.value } : {} })
    if (head.value?.id !== v.id) return
    if (res.success) {
      head.value = { ...v, ...res.data.bom }
      tree.value = res.data.children || []
    } else {
      ElMessage.error(res.message || '加载 BOM 失败')
    }
  } catch (e) {
    ElMessage.error(e.message || '网络错误')
  } finally {
    if (head.value?.id === v.id) loading.value = false
  }
}

function close() { visible.value = false }

// 改计价依据：保留筛选词重新加载
function onBatchChange() {
  if (head.value) open(head.value, keyword.value, priceBatch.value)
}

// 导出当前 BOM 为 Excel（带当前计价依据）
async function exportCurrent() {
  if (exporting.value) return
  exporting.value = true
  try { await exportBom(head.value, priceBatch.value) } finally { exporting.value = false }
}

// 树里点物料编码：交给调用方决定怎么跳转（物料卡片内跳转 / 产品卡片打开物料卡片）
function onOpenCode(code) {
  emit('open-code', code, { head: head.value, keyword: keyword.value, priceBatch: priceBatch.value })
}

function money(v) {
  return v == null ? '—' : '¥' + String(+Number(v).toFixed(4))
}

defineExpose({ open, close })
</script>

<template>
  <el-dialog
    v-model="visible"
    class="material-bom-dialog"
    width="min(1400px, 92vw)"
    align-center
    append-to-body
  >
    <template #header>
      <div v-if="head" class="bom-dlg-head">
        <span class="bom-dlg-code mono">{{ head.drawing }}</span>
        <span class="bom-dlg-name">{{ head.name }}</span>
        <span class="bom-dlg-meta">{{ head.imported_by || '—' }} · {{ head.imported_at }}</span>
        <el-button size="small" :icon="Download" class="bom-dlg-export" :loading="exporting"
                   @click="exportCurrent">导出</el-button>
      </div>
    </template>
    <div class="bom-dlg-filter">
      <el-input v-model="keyword" size="small" clearable placeholder="筛选编码 / 名称"
                :prefix-icon="Search" class="bom-dlg-search" />
      <span v-if="keyword.trim()" class="bom-dlg-hit">
        匹配 {{ treeRef?.matchCount ?? 0 }} 项（保留其上级层次）
      </span>
      <el-button v-if="treeRef?.hasNested" size="small" class="bom-dlg-toggle"
                 :icon="treeRef.allExpanded ? ArrowUp : ArrowDown" @click="treeRef.toggleAll()">
        {{ treeRef.allExpanded ? '全部收起' : '全部展开' }}
      </el-button>
    </div>
    <!-- 计价行（仅物料价格权限可见）：计价依据 + 合计，单独一行 -->
    <div v-if="canMaterialPrice" class="bom-dlg-price">
      <!-- 计价依据：最新价格 或 某次采购导入（年 → 月 → 订单），不手动选日期 -->
      <PriceBatchSelect v-model="priceBatch" @change="onBatchChange" />
      <template v-if="head && 'unit_price' in head">
        <!-- 齐全才计价：下级有缺价就不给合计 -->
        <span v-if="head.unit_price != null" class="bom-dlg-total" title="由下级价格计算（下级价格齐全）">
          合计 <b class="mono">{{ money(head.unit_price) }}</b>
        </span>
        <span v-else class="bom-dlg-total" title="下级价格齐全后才开始计价">
          未开始计价 <span class="calc-miss">缺 {{ head.missing }} 项价格</span>
        </span>
      </template>
    </div>
    <div v-loading="loading" class="bom-dlg-body">
      <MaterialBomTree ref="treeRef" :rows="tree" height="100%" :keyword="keyword"
                       :show-price="canMaterialPrice"
                       @open-code="onOpenCode"
                       :empty-text="loading ? '加载中...' : (keyword.trim() ? '没有匹配的物料' : '暂无 BOM 数据')" />
    </div>
  </el-dialog>
</template>

<style scoped>
.mono { font-family: monospace; font-size: 12px; }
.bom-dlg-head { display: flex; align-items: baseline; gap: 12px; min-width: 0; }
.bom-dlg-code { font-size: 17px; font-weight: 700; color: #000; }
.bom-dlg-name { font-size: 15px; color: #3a3028; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bom-dlg-meta { font-size: 12px; color: #8a7a6a; flex-shrink: 0; }
.bom-dlg-export { margin-left: auto; margin-right: 28px; align-self: center; }
.bom-dlg-filter { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; }
.bom-dlg-search { width: 280px; }
.bom-dlg-hit { font-size: 12px; color: #6b5e4e; }
.bom-dlg-toggle { margin-left: auto; }
.bom-dlg-price {
  display: flex; align-items: center; gap: 16px; margin-bottom: 10px;
  padding: 6px 10px; border-radius: 8px; background: #faf7f2; border: 1px solid var(--border);
}
.bom-dlg-total { font-size: 13px; color: #3a3028; }
.bom-dlg-total b { color: #4a8fc0; font-size: 14px; }
.calc-miss { padding: 0 6px; border-radius: 4px; font-size: 11px; color: #c0782a; background: rgba(224,144,80,0.15); }
.bom-dlg-body { height: 72vh; }
</style>
