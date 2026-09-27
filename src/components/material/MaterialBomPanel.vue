<script setup>
// ── 导入 ──────────────────────────────────────────
// 物料BOM：研发 BOM 的导入与浏览。
// 左侧是已导入的单层 BOM 列表（每个有下级的成品/产成品/半成品一条，按研发编码+版本），
// 右侧是选中 BOM 展开后的完整多层结构。采购 BOM 不在这里导入（只作价格来源）。
import { ref, computed, watch, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Upload, Delete, WarningFilled } from '@element-plus/icons-vue'
import http from '@/api/http'
import MaterialBomTree from './MaterialBomTree.vue'
import MaterialCard from './MaterialCard.vue'
import { usePermission } from '@/composables/usePermission'

const { canEditMaterial } = usePermission()

// ── 响应式状态 ────────────────────────────────────
const keyword   = ref('')
const category  = ref('')
const items     = ref([])
const total     = ref(0)
const categories = ref([])
const page      = ref(1)
const pageSize  = 50
const listLoading = ref(false)
const errorMsg  = ref('')

const selectedId  = ref(null)
const treeData    = ref(null)    // { bom, children }
const treeLoading = ref(false)

const fileInput  = ref(null)
const importing  = ref(false)
const importResult = ref(null)   // 导入结果弹窗
const resultOpen   = ref(false)
const importErrors    = ref([])  // 导入校验失败：逐条错误（含 Excel 行号）
const importErrorOpen = ref(false)

const cardCode    = ref('')
const cardVisible = ref(false)

// ── 计算属性 ──────────────────────────────────────
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))

// ── 方法 ──────────────────────────────────────────
async function loadList() {
  listLoading.value = true
  errorMsg.value = ''
  try {
    const params = { page: page.value, page_size: pageSize }
    if (keyword.value.trim()) params.keyword = keyword.value.trim()
    if (category.value) params.category = category.value
    const res = await http.get('/api/material/boms', { params })
    if (res.success) {
      items.value = res.data.items || []
      total.value = res.data.total || 0
      categories.value = res.data.categories || []
      // 当前选中的不在列表里时默认选第一条
      if (!items.value.some(i => i.id === selectedId.value)) {
        selectBom(items.value[0]?.id ?? null)
      }
    } else {
      errorMsg.value = res.message || '加载失败'
    }
  } catch (e) {
    errorMsg.value = e.message || '网络错误'
  } finally {
    listLoading.value = false
  }
}

async function selectBom(id) {
  selectedId.value = id
  treeData.value = null
  if (!id) return
  treeLoading.value = true
  try {
    const res = await http.get(`/api/material/boms/${id}/tree`)
    // 快速连点时只认最后一次
    if (selectedId.value !== id) return
    if (res.success) treeData.value = res.data
    else ElMessage.error(res.message || '加载 BOM 失败')
  } catch (e) {
    ElMessage.error(e.message || '网络错误')
  } finally {
    if (selectedId.value === id) treeLoading.value = false
  }
}

// 搜索框输入防抖，避免每个字符都打一次请求
let searchTimer = null
watch(keyword, () => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => { page.value = 1; loadList() }, 300)
})
watch(category, () => { page.value = 1; loadList() })
watch(page, loadList)

function pickFile() { fileInput.value?.click() }

async function onFileChange(e) {
  const file = e.target.files?.[0]
  e.target.value = ''
  if (!file) return
  const form = new FormData()
  form.append('file', file)
  importing.value = true
  try {
    const res = await http.post('/api/material/boms/import', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    if (res.success) {
      importResult.value = { ...res.data, filename: file.name }
      resultOpen.value = true
      page.value = 1
      await loadList()
    } else {
      // 校验错误可能一次列出多行（后端用「；」分隔），弹窗逐条显示，便于对照 Excel 修改
      importErrors.value = (res.message || '导入失败').split('；').filter(Boolean)
      importErrorOpen.value = true
    }
  } catch (err) {
    ElMessage.error(err.message || '网络错误')
  } finally {
    importing.value = false
  }
}

async function deleteBom() {
  const bom = treeData.value?.bom
  if (!bom) return
  try {
    await ElMessageBox.confirm(
      `确认删除 ${bom.drawing} 的 BOM？只删除这一层的子件清单，下级半成品自己的 BOM 不受影响。`,
      '删除 BOM', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })
  } catch { return }
  let res = await http.delete(`/api/material/boms/${bom.id}`)
  // 被其他 BOM 引用：列出引用它的上级，再确认一次才强制删除
  if (!res.success && res.data?.needs_force) {
    const refs = res.data.references || []
    const list = refs.slice(0, 10).map(r => `${r.drawing}${r.name ? ' ' + r.name : ''}`).join('\n')
    const more = refs.length > 10 ? `\n……等 ${refs.length} 个` : ''
    try {
      await ElMessageBox.confirm(
        `${bom.drawing} 正被以下上级 BOM 使用，删除后它在这些上级里将无法再展开下级：\n\n${list}${more}\n\n仍要删除吗？`,
        '仍被引用', {
          type: 'warning', confirmButtonText: '仍然删除', cancelButtonText: '取消',
          customStyle: { whiteSpace: 'pre-line' },
        })
    } catch { return }
    res = await http.delete(`/api/material/boms/${bom.id}`, { params: { force: 1 } })
  }
  if (res.success) {
    ElMessage.success('已删除')
    selectedId.value = null
    loadList()
  } else {
    ElMessage.error(res.message || '删除失败')
  }
}

function openCard(code) {
  cardCode.value = code
  cardVisible.value = true
}

// ── 生命周期 ──────────────────────────────────────
onMounted(loadList)
</script>

<template>
  <div class="bom-panel">
    <!-- ── 左：BOM 列表 ── -->
    <aside class="bp-list">
      <div class="bp-toolbar">
        <el-input v-model="keyword" size="small" clearable placeholder="编码 / 名称"
                  :prefix-icon="Search" class="bp-search" />
        <el-select v-model="category" size="small" clearable placeholder="类别" class="bp-cat">
          <el-option v-for="c in categories" :key="c" :label="c" :value="c" />
        </el-select>
        <el-button v-if="canEditMaterial" size="small" type="primary" :icon="Upload"
                   :loading="importing" @click="pickFile">导入BOM</el-button>
        <input ref="fileInput" type="file" accept=".xlsx" hidden @change="onFileChange" />
      </div>

      <div v-if="errorMsg" class="bp-error">
        <el-icon><WarningFilled /></el-icon><span>{{ errorMsg }}</span>
      </div>

      <div v-loading="listLoading" class="bp-items">
        <div v-if="!items.length && !listLoading" class="bp-empty">
          <template v-if="keyword || category">没有符合条件的 BOM</template>
          <template v-else>还没有导入 BOM<br /><span>点击「导入BOM」上传研发 BOM 表格（PDM / ERP 层次格式）</span></template>
        </div>
        <button
          v-for="b in items"
          :key="b.id"
          class="bp-item"
          :class="{ active: b.id === selectedId }"
          @click="selectBom(b.id)"
        >
          <div class="bp-item-top">
            <span class="bp-drawing mono">{{ b.drawing }}</span>
            <span v-if="b.category" class="bp-cat-tag">{{ b.category }}</span>
            <span class="bp-count">{{ b.line_count }} 项</span>
          </div>
          <div class="bp-item-name">{{ b.name || '—' }}</div>
        </button>
      </div>

      <div class="bp-footer">
        <span>共 <b>{{ total }}</b> 条</span>
        <div class="bp-pager">
          <button class="pg-btn" :disabled="page <= 1" @click="page--">上一页</button>
          <span>{{ page }} / {{ totalPages }}</span>
          <button class="pg-btn" :disabled="page >= totalPages" @click="page++">下一页</button>
        </div>
      </div>
    </aside>

    <!-- ── 右：选中 BOM 的完整结构 ── -->
    <section v-loading="treeLoading" class="bp-detail">
      <template v-if="treeData">
        <header class="bd-head">
          <!-- 编码：显示完整研发编码（含 -A01 这类完整版本）；能对应到 ERP 物料时可点开物料卡片 -->
          <span v-if="treeData.bom.erp_code" class="bd-drawing mono link"
                :title="`点击查看物料卡片（ERP：${treeData.bom.erp_code}）`"
                @click="openCard(treeData.bom.erp_code)">{{ treeData.bom.drawing }}</span>
          <span v-else class="bd-drawing mono" title="ERP 物料表里没有对应编码">{{ treeData.bom.drawing }}</span>
          <span class="bd-name">{{ treeData.bom.name }}</span>
          <span class="bd-meta">{{ treeData.bom.imported_by || '—' }} · {{ treeData.bom.imported_at }}</span>
          <el-button v-if="canEditMaterial" size="small" :icon="Delete" class="bd-del" @click="deleteBom">删除</el-button>
        </header>
        <div class="bd-tree">
          <MaterialBomTree :rows="treeData.children" height="100%" @open-code="openCard" />
        </div>
      </template>
      <div v-else-if="!treeLoading" class="bp-empty">选择左侧的 BOM 查看结构</div>
    </section>

    <!-- 导入结果 -->
    <el-dialog v-model="resultOpen" title="BOM 导入结果" width="520" align-center append-to-body>
      <div v-if="importResult" class="ir">
        <div class="ir-file">{{ importResult.filename }}</div>
        <div class="ir-stats">
          <div><b>{{ importResult.created }}</b><span>新增 BOM</span></div>
          <div><b>{{ importResult.updated }}</b><span>覆盖更新</span></div>
          <div><b>{{ importResult.lines }}</b><span>子件行</span></div>
        </div>
        <div v-if="importResult.skipped" class="ir-row ir-muted">
          已按规则跳过 {{ importResult.skipped }} 行（带「.」的 PDM 子零件、14ST10 标准件及其下级）
        </div>
        <div v-if="importResult.roots?.length" class="ir-row">
          顶层：<span class="mono">{{ importResult.roots.join('、') }}</span>
        </div>
        <div v-if="importResult.unmatched?.length" class="ir-unmatched">
          <div class="ir-warn">
            <el-icon><WarningFilled /></el-icon>
            {{ importResult.unmatched.length }} 个编码在 ERP 物料表中找不到对应物料（BOM 已保存，只是无法关联到物料表）：
          </div>
          <div class="ir-codes mono">{{ importResult.unmatched.join('、') }}</div>
        </div>
      </div>
      <template #footer>
        <el-button type="primary" @click="resultOpen = false">知道了</el-button>
      </template>
    </el-dialog>

    <!-- 导入校验失败：整份文件未写入，逐条列出问题 -->
    <el-dialog v-model="importErrorOpen" title="BOM 导入失败" width="560" align-center append-to-body>
      <div class="ie-tip">文件未导入，请按下列问题修改 Excel 后重新导入：</div>
      <ul class="ie-list">
        <li v-for="(e, i) in importErrors" :key="i">{{ e }}</li>
      </ul>
      <template #footer>
        <el-button type="primary" @click="importErrorOpen = false">知道了</el-button>
      </template>
    </el-dialog>

    <MaterialCard v-model:visible="cardVisible" :code="cardCode" />
  </div>
</template>

<style scoped>
.bom-panel { flex: 1; min-height: 0; display: flex; gap: 12px; }
.mono { font-family: 'SF Mono', Consolas, 'Microsoft YaHei UI', monospace; }

/* ── 左侧列表 ── */
.bp-list {
  width: 380px; flex-shrink: 0; display: flex; flex-direction: column; min-height: 0;
  background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px;
  padding: 12px;
}
.bp-toolbar { display: flex; gap: 6px; align-items: center; margin-bottom: 10px; }
.bp-search { flex: 1; min-width: 0; }
.bp-cat { width: 96px; }
.bp-error {
  display: flex; align-items: center; gap: 6px; margin-bottom: 8px; padding: 6px 10px;
  border-radius: 7px; font-size: 12px; color: #d05a3c;
  background: rgba(208,90,60,0.06); border: 1px solid rgba(208,90,60,0.2);
}
.bp-items { flex: 1; min-height: 0; overflow-y: auto; display: flex; flex-direction: column; gap: 4px; }
.bp-items::-webkit-scrollbar { width: 4px; }
.bp-items::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }
.bp-item {
  text-align: left; padding: 8px 10px; border-radius: 8px; cursor: pointer;
  border: 1px solid transparent; background: transparent; font-family: inherit;
  transition: all 0.15s;
}
.bp-item:hover { background: #faf7f2; }
.bp-item.active { background: var(--accent-bg); border-color: var(--accent); }
.bp-item-top { display: flex; align-items: center; gap: 6px; }
.bp-drawing { font-size: 13px; font-weight: 700; color: #2c2420; }
.bp-cat-tag {
  font-size: 10px; padding: 0 6px; line-height: 16px; border-radius: 4px;
  color: #6b5e4e; background: #f5f0e8; border: 1px solid var(--border);
}
.bp-count { margin-left: auto; font-size: 11px; color: #8a7a6a; }
.bp-item-name {
  margin-top: 2px; font-size: 12px; color: #6b5e4e;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.bp-empty {
  margin: auto; padding: 24px; text-align: center; font-size: 13px; color: var(--text-muted);
  line-height: 1.8;
}
.bp-empty span { font-size: 12px; }
.bp-footer {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  padding-top: 8px; font-size: 12px; color: #6b5e4e;
}
.bp-pager { display: flex; align-items: center; gap: 6px; }
.pg-btn {
  padding: 2px 10px; border-radius: 6px; border: 1px solid var(--border);
  background: var(--bg-card); color: var(--text-primary);
  font-size: 12px; font-family: inherit; cursor: pointer;
}
.pg-btn:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); }
.pg-btn:disabled { opacity: 0.4; cursor: not-allowed; }

/* ── 右侧结构 ── */
.bp-detail {
  flex: 1; min-width: 0; min-height: 0; display: flex; flex-direction: column;
  background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px;
  padding: 12px;
}
.bd-head { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; flex-wrap: wrap; }
.bd-drawing { font-size: 16px; font-weight: 700; color: #000; }
.bd-name { font-size: 14px; color: #3a3028; }
.bd-drawing.link { cursor: pointer; }
.bd-drawing.link:hover { color: var(--accent); text-decoration: underline; }

.bd-meta { font-size: 11px; color: #8a7a6a; }
.bd-del { margin-left: auto; }
.bd-tree { flex: 1; min-height: 0; }

/* ── 导入结果 ── */
.ir-file { font-size: 12px; color: #8a7a6a; margin-bottom: 10px; }
.ir-stats { display: flex; gap: 10px; margin-bottom: 12px; }
.ir-stats > div {
  flex: 1; text-align: center; padding: 10px 0; border-radius: 10px;
  background: #faf7f2; border: 1px solid var(--border);
}
.ir-stats b { display: block; font-size: 20px; color: #2c2420; }
.ir-stats span { font-size: 12px; color: #6b5e4e; }
.ir-row { font-size: 13px; color: #3a3028; margin-bottom: 10px; }
.ir-muted { font-size: 12px; color: #6b5e4e; }
.ie-tip { font-size: 13px; color: #3a3028; margin-bottom: 8px; }
.ie-list {
  margin: 0; padding: 10px 10px 10px 28px; max-height: 320px; overflow-y: auto;
  border-radius: 8px; background: #fff4f1; border: 1px solid #f0c4b8;
  font-size: 13px; line-height: 1.8; color: #a33b1f;
}
.ir-unmatched {
  padding: 10px; border-radius: 8px;
  background: #fff8e6; border: 1px solid #f0d48a;
}
.ir-warn { display: flex; align-items: center; gap: 6px; font-size: 13px; color: #8a5a00; margin-bottom: 6px; }
.ir-codes { font-size: 12px; color: #3a3028; max-height: 120px; overflow-y: auto; word-break: break-all; }
</style>
