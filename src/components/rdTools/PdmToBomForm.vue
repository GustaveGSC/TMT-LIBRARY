<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled, RefreshRight, Download } from '@element-plus/icons-vue'
import { PhArrowsLeftRight } from '@phosphor-icons/vue'
import http from '@/api/http'

// ── 响应式状态 ────────────────────────────────────
// 'idle' | 'processing' | 'error' | 'ready'
const state = ref('idle')
const selectedFilePath = ref('')
const selectedFileName = ref('')

// 来自后端 process 响应
const columns = ref([])               // PDM 文件所有列名
const tableData = ref([])             // 2D 字符串数组，可编辑
const errorMap = ref({})              // { "rowIndex": [colIndex, ...] }
const requiredColIndices = ref([])    // 必填列索引
const totalLevel = ref(0)             // 最大层级深度

// ── 计算属性 ──────────────────────────────────────
// 第一行的品号，用于生成默认文件名
const firstCode = computed(() => {
  const ci = columns.value.indexOf('品号')
  return ci >= 0 && tableData.value[0] ? tableData.value[0][ci] : ''
})

// ── 方法 ──────────────────────────────────────────

// 打开 Electron 文件选择对话框
async function selectFile() {
  const result = await window.electronAPI?.showOpenDialog({
    title: '选择 PDM 导出文件',
    filters: [{ name: 'Excel 文件', extensions: ['xlsx'] }],
    properties: ['openFile'],
  })
  const path = result?.filePaths?.[0]
  if (!path) return
  selectedFilePath.value = path
  selectedFileName.value = path.split(/[\\/]/).pop()
  // 重置状态
  state.value = 'idle'
  columns.value = []
  tableData.value = []
  errorMap.value = {}
}

// 发送文件路径到后端处理
async function processFile() {
  if (!selectedFilePath.value) {
    ElMessage.warning('请先选择 PDM 导出文件')
    return
  }
  state.value = 'processing'
  try {
    const res = await http.post('/api/rd/pdm2bom/process', {
      file_path: selectedFilePath.value,
    })
    if (!res.success) {
      ElMessage.error(res.message || '处理失败')
      state.value = 'idle'
      return
    }
    const data = res.data
    columns.value = data.columns
    // 深拷贝，使 tableData 可在前端独立编辑
    tableData.value = data.table_data.map(row => [...row])
    errorMap.value = data.error_map
    requiredColIndices.value = data.required_col_indices
    totalLevel.value = data.total_level
    const errCount = Object.keys(data.error_map).length
    state.value = errCount ? 'error' : 'ready'
    if (!errCount) {
      ElMessage.success(`处理完成，共 ${tableData.value.length} 行`)
    }
  } catch {
    ElMessage.error('请求失败，请检查后端服务')
    state.value = 'idle'
  }
}

// 在前端本地重新校验（不往返后端）
function revalidate() {
  const newErrorMap = {}
  tableData.value.forEach((row, ri) => {
    const missing = requiredColIndices.value.filter(ci => !row[ci])
    if (missing.length) newErrorMap[String(ri)] = missing
  })
  // 重新计算层级深度（如果层次列被编辑）
  const levelIdx = columns.value.indexOf('层次')
  if (levelIdx >= 0) {
    totalLevel.value = tableData.value.reduce((max, row) => {
      const depth = (row[levelIdx] || '').split('.').length
      return Math.max(max, depth)
    }, 0)
  }
  errorMap.value = newErrorMap
  const errCount = Object.keys(newErrorMap).length
  if (errCount > 0) {
    state.value = 'error'
    ElMessage.warning(`仍有 ${errCount} 行存在缺失项，请补充后重新校验`)
  } else {
    state.value = 'ready'
    ElMessage.success('校验通过，可以导出')
  }
}

// 导出 ERP 物料 xlsx
async function exportErp() {
  try {
    const res = await http.post('/api/rd/pdm2bom/export-erp', {
      columns: columns.value,
      table_data: tableData.value,
    }, { responseType: 'arraybuffer' })
    const saveResult = await window.electronAPI?.showSaveDialog({
      defaultPath: `ERP-${firstCode.value}.xlsx`,
      filters: [{ name: 'Excel', extensions: ['xlsx'] }],
    })
    if (!saveResult?.canceled && saveResult?.filePath) {
      await window.electronAPI.saveFile(saveResult.filePath, res)
      ElMessage.success(`ERP 物料文件已导出`)
    }
  } catch {
    ElMessage.error('ERP 物料导出失败')
  }
}

// 导出 BOM xlsx
async function exportBom() {
  try {
    const res = await http.post('/api/rd/pdm2bom/export-bom', {
      columns: columns.value,
      table_data: tableData.value,
      total_level: totalLevel.value,
    }, { responseType: 'arraybuffer' })
    const saveResult = await window.electronAPI?.showSaveDialog({
      defaultPath: `BOM-${firstCode.value}.xlsx`,
      filters: [{ name: 'Excel', extensions: ['xlsx'] }],
    })
    if (!saveResult?.canceled && saveResult?.filePath) {
      await window.electronAPI.saveFile(saveResult.filePath, res)
      ElMessage.success(`BOM 文件已导出`)
    }
  } catch {
    ElMessage.error('BOM 导出失败')
  }
}

// 获取单元格 class（错误行高亮）
function cellClass(ri, ci) {
  const key = String(ri)
  if (!(key in errorMap.value)) return ''
  return errorMap.value[key].includes(ci) ? 'cell-error' : 'cell-warn'
}

// 判断行是否有错误
function isErrorRow(ri) {
  return String(ri) in errorMap.value
}
</script>

<template>
  <div class="ptb-form">

    <!-- ── 顶部操作栏 ────────────────────────────── -->
    <div class="ptb-toolbar">
      <button class="btn-select" @click="selectFile">
        <el-icon><UploadFilled /></el-icon>
        选择文件
      </button>
      <span class="file-name" :class="{ 'has-file': selectedFileName }">
        {{ selectedFileName || '未选择文件' }}
      </span>
      <button
        class="btn-process"
        :disabled="!selectedFilePath || state === 'processing'"
        @click="processFile"
      >
        {{ state === 'processing' ? '处理中…' : '处理' }}
      </button>
    </div>

    <!-- ── 内容区 ──────────────────────────────── -->
    <div class="ptb-content">

      <!-- 空闲：占位 -->
      <div v-if="state === 'idle'" class="ptb-placeholder">
        <component :is="PhArrowsLeftRight" :size="48" weight="duotone" color="#c4883a" style="opacity:0.35" />
        <div class="ph-title">PDM 转 BOM</div>
        <div class="ph-desc">选择 PDM 导出的 .xlsx 文件，点击「处理」开始转换</div>
      </div>

      <!-- 处理中 -->
      <div v-else-if="state === 'processing'" class="ptb-placeholder">
        <div class="ph-title" style="color: var(--text-muted)">正在处理文件…</div>
      </div>

      <!-- 错误：可编辑表格 -->
      <div v-else-if="state === 'error'" class="ptb-error-panel">
        <div class="error-bar">
          <span class="error-summary">
            发现 <b>{{ Object.keys(errorMap).length }}</b> 行存在缺失项 ──
            <span class="leg-red">■ 缺失格</span>
            <span class="leg-yellow">■ 有问题行其他格</span>
          </span>
          <button class="btn-revalidate" @click="revalidate">
            <el-icon><RefreshRight /></el-icon>
            重新校验
          </button>
        </div>
        <div class="table-scroll">
          <table class="ptb-table">
            <thead>
              <tr>
                <th class="col-seq">#</th>
                <th v-for="(col, ci) in columns" :key="ci">{{ col }}</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(row, ri) in tableData"
                :key="ri"
                :class="{ 'row-has-error': isErrorRow(ri) }"
              >
                <td class="col-seq">{{ ri + 1 }}</td>
                <td
                  v-for="(cell, ci) in row"
                  :key="ci"
                  :class="cellClass(ri, ci)"
                >
                  <input
                    v-if="isErrorRow(ri)"
                    v-model="tableData[ri][ci]"
                    class="cell-input"
                  />
                  <span v-else>{{ cell }}</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- 就绪：导出按钮 -->
      <div v-else-if="state === 'ready'" class="ptb-ready">
        <div class="ready-icon">
          <component :is="PhArrowsLeftRight" :size="36" weight="duotone" color="#c4883a" />
        </div>
        <div class="ready-title">处理完成</div>
        <div class="ready-desc">
          共 {{ tableData.length }} 行数据，品号：{{ firstCode }}
        </div>
        <div class="export-buttons">
          <button class="btn-export erp" @click="exportErp">
            <el-icon><Download /></el-icon>
            导出 ERP 物料 xlsx
          </button>
          <button class="btn-export bom" @click="exportBom">
            <el-icon><Download /></el-icon>
            导出 BOM xlsx
          </button>
        </div>
      </div>

    </div>
  </div>
</template>

<style scoped>
.ptb-form {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

/* ── 顶部操作栏 ── */
.ptb-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.6);
  flex-shrink: 0;
}

.btn-select {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 0 14px;
  height: 32px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-card);
  color: var(--text-primary);
  font-size: 13px;
  font-family: var(--font-family);
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
  flex-shrink: 0;
}
.btn-select:hover { border-color: var(--accent); color: var(--accent); }

.file-name {
  flex: 1;
  font-size: 13px;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.file-name.has-file { color: var(--text-primary); }

.btn-process {
  padding: 0 20px;
  height: 32px;
  border: none;
  border-radius: 8px;
  background: var(--accent);
  color: #fff;
  font-size: 13px;
  font-family: var(--font-family);
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s;
  white-space: nowrap;
  flex-shrink: 0;
}
.btn-process:hover:not(:disabled) { background: #e09050; }
.btn-process:disabled { opacity: 0.45; cursor: not-allowed; }

/* ── 内容区 ── */
.ptb-content {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* 占位 */
.ptb-placeholder {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
}
.ph-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin-top: 4px;
}
.ph-desc {
  font-size: 13px;
  color: var(--text-muted);
  text-align: center;
  max-width: 300px;
  line-height: 1.6;
}

/* ── 错误表格面板 ── */
.ptb-error-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.error-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 7px 14px;
  background: #fffde7;
  border-bottom: 1px solid #ffe082;
  flex-shrink: 0;
}
.error-summary {
  font-size: 13px;
  color: var(--text-primary);
}
.leg-red    { color: #c62828; font-size: 12px; margin-left: 10px; }
.leg-yellow { color: #e65100; font-size: 12px; margin-left: 6px; }

.btn-revalidate {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 0 14px;
  height: 28px;
  border: 1px solid var(--accent);
  border-radius: 7px;
  background: transparent;
  color: var(--accent);
  font-size: 12px;
  font-family: var(--font-family);
  cursor: pointer;
  transition: all 0.15s;
  flex-shrink: 0;
}
.btn-revalidate:hover { background: var(--accent); color: #fff; }

/* 表格滚动容器 */
.table-scroll {
  flex: 1;
  overflow: auto;
}
.table-scroll::-webkit-scrollbar { width: 4px; height: 4px; }
.table-scroll::-webkit-scrollbar-track { background: transparent; }
.table-scroll::-webkit-scrollbar-thumb { background: rgba(0,0,0,0.18); border-radius: 2px; }

.ptb-table {
  border-collapse: collapse;
  white-space: nowrap;
  font-size: 12px;
  font-family: var(--font-family);
}
.ptb-table th {
  background: #f5f0e8;
  color: var(--text-primary);
  font-weight: 600;
  padding: 5px 8px;
  border: 1px solid var(--border);
  position: sticky;
  top: 0;
  z-index: 1;
}
.ptb-table td {
  padding: 2px 6px;
  border: 1px solid #e8e0d0;
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--text-primary);
  background: #fff;
}
.col-seq {
  width: 36px;
  text-align: center;
  color: var(--text-muted);
  font-size: 11px;
}

/* 高亮 */
.row-has-error td { background: #fff8e1; }
.cell-warn        { background: #fff8e1 !important; }
.cell-error       { background: #ffebee !important; }

/* 可编辑输入框 */
.cell-input {
  width: 100%;
  min-width: 60px;
  max-width: 150px;
  border: 1px solid #bbb;
  border-radius: 3px;
  padding: 1px 4px;
  font-size: 12px;
  font-family: var(--font-family);
  background: #fff;
  color: var(--text-primary);
  outline: none;
}
.cell-input:focus { border-color: var(--accent); }

/* ── 就绪 ── */
.ptb-ready {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 14px;
}
.ready-icon {
  width: 72px;
  height: 72px;
  border-radius: 20px;
  background: var(--bg-card);
  border: 1.5px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 12px var(--shadow);
}
.ready-title { font-size: 16px; font-weight: 600; color: var(--text-primary); }
.ready-desc  { font-size: 13px; color: var(--text-muted); }

.export-buttons {
  display: flex;
  gap: 12px;
  margin-top: 8px;
}
.btn-export {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 22px;
  height: 36px;
  border-radius: 10px;
  font-size: 13px;
  font-family: var(--font-family);
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}
.btn-export.erp {
  border: none;
  background: var(--accent);
  color: #fff;
}
.btn-export.erp:hover { background: #e09050; }
.btn-export.bom {
  border: 1.5px solid var(--accent);
  background: var(--bg-card);
  color: var(--accent);
}
.btn-export.bom:hover { background: var(--accent); color: #fff; }
</style>
