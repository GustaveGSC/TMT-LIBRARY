<script setup>
// ── 材料清单校验（独立工具） ────────────────────────
// 上传任意一份带"物料编码"或"品号"列的 Excel，单独跑一遍门禁校验，不生成任何单据。
// 和 PDM转BOM / 变更申请单填写 里的自动校验共用同一份门禁数据，但这里是主动触发、
// 面向"临时想核对一份清单"的场景（比如采购/仓库同事），不依赖那两个流程。
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled, Setting } from '@element-plus/icons-vue'
import { usePermission } from '@/composables/usePermission'
import http from '@/api/http'
import { pickFile } from '@/utils/download.js'
import MaterialGateBanner from './MaterialGateBanner.vue'
import MaterialGateManageDialog from './MaterialGateManageDialog.vue'

const { canAdminRd } = usePermission()

const selectedFilePath = ref('')
const selectedFileName = ref('')
const selectedFileObj  = ref(null)
const checking  = ref(false)
const scannedCount = ref(0)
const hits = ref({ warn: [], block: [] })
const hitsOk = ref(true)
const hasResult = ref(false)

const showMgmtDialog = ref(false)

async function selectFile() {
  if (window.electronAPI) {
    const result = await window.electronAPI.showOpenDialog({
      title: '选择材料清单文件',
      filters: [{ name: 'Excel 文件', extensions: ['xlsx'] }],
      properties: ['openFile'],
    })
    const path = result?.filePaths?.[0]
    if (!path) return
    selectedFilePath.value = path
    selectedFileName.value = path.split(/[\\/]/).pop()
    selectedFileObj.value = null
  } else {
    const file = await pickFile('.xlsx')
    if (!file) return
    selectedFilePath.value = ''
    selectedFileName.value = file.name
    selectedFileObj.value = file
  }
  hasResult.value = false
  hits.value = { warn: [], block: [] }
}

async function handleCheck() {
  if (!selectedFilePath.value && !selectedFileObj.value) {
    ElMessage.warning('请先选择要校验的文件')
    return
  }
  checking.value = true
  try {
    let res
    if (window.electronAPI) {
      res = await http.post('/api/rd/material-gates/check-file', {
        file_path: selectedFilePath.value,
      })
    } else {
      const fd = new FormData()
      fd.append('file', selectedFileObj.value)
      res = await http.post('/api/rd/material-gates/check-file', fd)
    }
    if (!res.success) {
      ElMessage.error(res.message || '校验失败')
      hitsOk.value = false
      return
    }
    scannedCount.value = res.data.scanned_count || 0
    hits.value = { warn: res.data.warn || [], block: res.data.block || [] }
    hitsOk.value = true
    hasResult.value = true
    if (!hits.value.warn.length && !hits.value.block.length) {
      ElMessage.success(`共扫描 ${scannedCount.value} 个物料编码，未命中门禁`)
    }
  } catch {
    ElMessage.error('请求失败，请检查后端服务')
    hitsOk.value = false
  } finally {
    checking.value = false
  }
}
</script>

<template>
  <div class="gate-check-page">
    <div class="gate-check-toolbar">
      <el-button size="small" @click="selectFile">选择文件</el-button>
      <span class="file-name" :class="{ 'file-name--set': selectedFileName }">
        {{ selectedFileName || '未选择（需包含"物料编码"或"品号"列）' }}
      </span>
      <el-button size="small" type="primary" :loading="checking" @click="handleCheck">开始校验</el-button>
      <button v-if="canAdminRd" class="btn-mgmt-gate" @click="showMgmtDialog = true">
        <el-icon><Setting /></el-icon> 管理物料门禁
      </button>
    </div>

    <div v-if="hasResult" class="gate-check-result">
      <div class="gate-check-summary">共扫描 {{ scannedCount }} 个物料编码</div>
      <MaterialGateBanner :hits="hits" :ok="hitsOk" />
      <div v-if="!hits.warn.length && !hits.block.length" class="gate-check-empty">
        未命中任何门禁物料
      </div>
    </div>

    <div v-else class="gate-check-empty-state">
      <el-icon :size="40" color="var(--text-muted)"><UploadFilled /></el-icon>
      <div>选择一份带"物料编码"或"品号"列的 Excel，点击"开始校验"</div>
    </div>

    <MaterialGateManageDialog v-model="showMgmtDialog" />
  </div>
</template>

<style scoped>
.gate-check-page {
  padding: 20px;
  height: 100%;
  overflow-y: auto;
}
.gate-check-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.file-name {
  font-size: 12px;
  color: var(--text-muted);
}
.file-name--set { color: var(--text-primary); }

.btn-mgmt-gate {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 4px;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 3px 10px;
  font-size: 12px;
  font-family: var(--font-family);
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.15s;
}
.btn-mgmt-gate:hover { color: var(--accent); border-color: var(--accent); }

.gate-check-result { margin-top: 16px; max-width: 640px; }
.gate-check-summary { font-size: 13px; color: var(--text-muted); margin-bottom: 4px; }
.gate-check-empty {
  font-size: 12px;
  color: #267840;
  background: rgba(38,120,64,0.06);
  border: 1px solid rgba(38,120,64,0.25);
  border-radius: 8px;
  padding: 8px 12px;
}

.gate-check-empty-state {
  margin-top: 60px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  color: var(--text-muted);
  font-size: 13px;
}
</style>
