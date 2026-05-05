<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, reactive, computed, onMounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { Close, Plus, Setting } from '@element-plus/icons-vue'
import http from '@/api/http.js'
import logoUrl from '@/assets/logo-banner.png'
import { usePermission } from '@/composables/usePermission'

// ── 当前用户 & 权限 ────────────────────────────────
const _user     = JSON.parse(localStorage.getItem('user') || '{}')
const submitter = _user.display_name || _user.username || ''
const { canAdminRd } = usePermission()

// 构建请求头（权限透传到后端）
function _authHeaders() {
  return {
    'X-User-Roles':       (_user.roles       || []).join(','),
    'X-User-Permissions': (_user.permissions || []).join(','),
  }
}

// ── 滚动容器引用（重置时归顶）──────────────────────
const formLeftRef  = ref(null)
const formRightRef = ref(null)

// ── 常量选项 ──────────────────────────────────────
const CHANGE_TYPE_OPTS  = ['设计变更', '制程变更', '其他']
const DISTRIBUTION_OPTS = ['研发', '业务', '采购', '生产', '生管', '品牌', '服务', '品管']
const REASON_OPTS       = ['品质不良', '价格变动', '设计优化', '结构优化', '成本优化', '工艺优化', '其他']

// ── 响应式状态 ────────────────────────────────────
const form = reactive({
  issuing_unit:         '研发部',
  date:                 todayStr(),
  ecr_code:             '',
  project:              '',
  change_type:          '设计变更',
  change_type_custom:   '',
  distribution:         ['采购', '生产', '生管', '品管'],
  change_reason:        '',
  change_reason_custom: '',
  change_subject:       '',
  change_desc:          '',
})

const exportLoading = ref(false)
const showPreview   = ref(false)

// 变更提醒（从后端加载，在架条目）
const reminders        = ref([])         // 当前在架提醒列表（db 数据）
const reminderChecked  = reactive({})    // { id: boolean } 本次会话的勾选状态
const remindersLoading = ref(false)

async function fetchReminders() {
  remindersLoading.value = true
  try {
    const res = await http.get('/api/rd/reminders')
    if (res.success) {
      reminders.value = res.data
      // 清理已失效的 checked 状态，保留本次已勾选
      const idSet = new Set(res.data.map(r => r.id))
      Object.keys(reminderChecked).forEach(k => { if (!idSet.has(Number(k))) delete reminderChecked[k] })
    }
  } finally {
    remindersLoading.value = false
  }
}

// ── 管理对话框 ────────────────────────────────────
const showMgmtDialog   = ref(false)
const mgmtReminders    = ref([])         // 全部提醒（含下架历史）
const mgmtLoading      = ref(false)
const newReminder      = reactive({ content: '', notes: '' })
const createLoading    = ref(false)

async function openMgmtDialog() {
  showMgmtDialog.value = true
  mgmtLoading.value = true
  try {
    const res = await http.get('/api/rd/reminders/all', { headers: _authHeaders() })
    if (res.success) mgmtReminders.value = res.data
    else ElMessage.error(res.message || '加载失败')
  } finally {
    mgmtLoading.value = false
  }
}

async function handleCreateReminder() {
  if (!newReminder.content.trim()) { ElMessage.warning('请填写提醒内容'); return }
  createLoading.value = true
  try {
    const res = await http.post('/api/rd/reminders', {
      content:    newReminder.content.trim(),
      notes:      newReminder.notes.trim(),
      created_by: submitter,
    }, { headers: _authHeaders() })
    if (res.success) {
      ElMessage.success('已创建')
      newReminder.content = ''
      newReminder.notes   = ''
      mgmtReminders.value.unshift(res.data)
      await fetchReminders()   // 同步主列表
    } else {
      ElMessage.error(res.message || '创建失败')
    }
  } finally {
    createLoading.value = false
  }
}

async function handleDeactivate(id) {
  const res = await http.put(`/api/rd/reminders/${id}/deactivate`, {}, { headers: _authHeaders() })
  if (res.success) {
    const item = mgmtReminders.value.find(r => r.id === id)
    if (item) item.is_active = false
    await fetchReminders()
    ElMessage.success('已下架')
  } else {
    ElMessage.error(res.message || '操作失败')
  }
}

async function handleActivate(id) {
  const res = await http.put(`/api/rd/reminders/${id}/activate`, {}, { headers: _authHeaders() })
  if (res.success) {
    const item = mgmtReminders.value.find(r => r.id === id)
    if (item) item.is_active = true
    await fetchReminders()
    ElMessage.success('已重新上架')
  } else {
    ElMessage.error(res.message || '操作失败')
  }
}

// 多个 BOM 变更组，每组独立的文件选择和比对结果
function newGroup() {
  return { before_path: '', before_name: '', after_path: '', after_name: '', compareResult: null, compareLoading: false, confirmed: false }
}
const bomGroups = ref([newGroup()])

// ── 计算属性 ──────────────────────────────────────
// 汇总所有已确认组的变更行（供预览和导出使用）
const allChanges = computed(() => {
  const list = []
  bomGroups.value.forEach(g => {
    if (g.confirmed && g.compareResult?.changes?.length) list.push(...g.compareResult.changes)
  })
  list.forEach((ch, i) => { ch.seq = i + 1 })
  return list
})

// ── 生命周期 ──────────────────────────────────────
onMounted(() => {
  form.ecr_code = generateEcrCode(false)
  fetchReminders()
})

// ── 工具函数 ──────────────────────────────────────
function todayStr() {
  return new Date().toISOString().slice(0, 10)
}

function generateEcrCode(consume = true) {
  const today = new Date().toISOString().slice(0, 10).replace(/-/g, '')
  const key = `ecr_seq_${today}`
  const cur = parseInt(sessionStorage.getItem(key) || '0')
  const seq = cur + 1
  if (consume) sessionStorage.setItem(key, String(seq))
  return `ECR.${today}-${String(seq).padStart(2, '0')}`
}

function markText(opts, selected, custom = '') {
  return opts.map(o => {
    const checked = Array.isArray(selected) ? selected.includes(o) : selected === o
    if (checked && o === '其他' && custom) return `☑ 其他：${custom}`
    return checked ? `☑ ${o}` : `☐ ${o}`
  }).join('    ')
}

// 将 cancel/add 对合并为单行，计算 change_content 描述
function diffRowsFor(group) {
  if (!group.compareResult) return []
  const list = group.compareResult.changes
  const rows = []
  let i = 0
  while (i < list.length) {
    const ch = list[i]
    if (ch.row_type === 'cancel' && i + 1 < list.length && list[i + 1].row_type === 'add') {
      const nxt = list[i + 1]
      const kind = ch.change_kind || '变更'
      const qtyChanged = ch.qty != null && nxt.qty != null && Math.abs(ch.qty - nxt.qty) > 1e-9
      let change_content = kind === '数量变更'
        ? `数量变更 ${ch.qty}→${nxt.qty}`
        : (qtyChanged ? `${kind}，数量 ${ch.qty}→${nxt.qty}` : kind)
      rows.push({
        seq: rows.length + 1, level: ch.level, name: ch.name,
        drawing_before: ch.drawing,  drawing_after: nxt.drawing,
        spec_before:    ch.spec,     spec_after:    nxt.spec,
        change_content,
        row_type: 'changed',
      })
      i += 2
    } else {
      const kind = ch.change_kind || (ch.row_type === 'added' ? '新增' : ch.row_type === 'deleted' ? '删除' : '')
      rows.push({
        seq: rows.length + 1, level: ch.level, name: ch.name,
        drawing_before: ch.row_type === 'deleted' ? ch.drawing : '',
        drawing_after:  ch.row_type === 'added'   ? ch.drawing : '',
        spec_before:    ch.row_type === 'deleted' ? ch.spec : '',
        spec_after:     ch.row_type === 'added'   ? ch.spec : '',
        change_content: kind,
        row_type:       ch.row_type,
      })
      i++
    }
  }
  return rows
}

// ── 表单校验 ──────────────────────────────────────
function validate() {
  if (!form.issuing_unit.trim())  { ElMessage.warning('请填写发出单位'); return false }
  if (!form.ecr_code.trim())      { ElMessage.warning('请填写变更编码'); return false }
  if (!form.project.trim())       { ElMessage.warning('请填写变更项目'); return false }
  if (!form.change_type)          { ElMessage.warning('请选择变更类型'); return false }
  if (form.change_type === '其他' && !form.change_type_custom.trim())
                                  { ElMessage.warning('请填写变更类型说明'); return false }
  if (!form.distribution.length)  { ElMessage.warning('请选择分发单位'); return false }
  if (!form.change_reason)        { ElMessage.warning('请选择变更原因'); return false }
  if (form.change_reason === '其他' && !form.change_reason_custom.trim())
                                  { ElMessage.warning('请填写变更原因说明'); return false }
  if (!form.change_subject.trim()){ ElMessage.warning('请填写变更主题'); return false }
  if (!form.change_desc.trim())   { ElMessage.warning('请填写变更内容说明'); return false }
  // 在架提醒项必须全部勾选
  const unchecked = reminders.value.filter(r => !reminderChecked[r.id])
  if (unchecked.length) {
    ElMessage.warning(`还有 ${unchecked.length} 条变更提醒未确认，请逐项核对并勾选后再导出`)
    return false
  }
  return true
}

// ── BOM 组管理 ────────────────────────────────────
function addBomGroup() {
  bomGroups.value.push(newGroup())
}

function removeBomGroup(idx) {
  bomGroups.value.splice(idx, 1)
}

async function selectBomFile(type, idx) {
  const result = await window.electronAPI?.showOpenDialog({
    filters: [{ name: 'Excel 文件', extensions: ['xlsx'] }],
    properties: ['openFile'],
  })
  if (result?.canceled || !result?.filePaths?.length) return
  const filePath = result.filePaths[0]
  const fileName = filePath.replace(/.*[/\\]/, '')
  const g = bomGroups.value[idx]
  if (type === 'before') { g.before_path = filePath; g.before_name = fileName }
  else                   { g.after_path  = filePath; g.after_name  = fileName }
  g.compareResult = null
  g.confirmed = false
}

async function handleCompare(idx) {
  const g = bomGroups.value[idx]
  if (!g.before_path || !g.after_path) { ElMessage.warning('请先选择两个 BOM 文件'); return }
  g.compareLoading = true
  g.compareResult  = null
  try {
    const res = await http.post('/api/rd/ecr/compare-bom', {
      bom_before_path: g.before_path,
      bom_after_path:  g.after_path,
    })
    if (res.success) {
      g.compareResult = res.data
      g.confirmed = false   // 重新比对后需要重新确认
      if (res.data.stats.total === 0) ElMessage.info('两份 BOM 无差异')
    } else {
      ElMessage.error(res.message || '比对失败')
    }
  } catch {
    ElMessage.error('比对失败，请重试')
  } finally {
    g.compareLoading = false
  }
}

// ── 预览 / 导出 ───────────────────────────────────
function handlePreview() {
  if (!validate()) return
  showPreview.value = true
}

async function handleExport() {
  if (!validate()) return
  exportLoading.value = true
  try {
    const code = generateEcrCode(true)
    form.ecr_code = code

    const res = await http.post('/api/rd/ecr/export', {
      ...form,
      submitter,
      changes: allChanges.value.length ? allChanges.value : null,
    }, { responseType: 'arraybuffer' })

    const saveResult = await window.electronAPI?.showSaveDialog({
      defaultPath: `${code} ${form.project} 变更申请单.xlsx`,
      filters: [{ name: 'Excel', extensions: ['xlsx'] }],
    })
    if (saveResult?.canceled || !saveResult?.filePath) return

    await window.electronAPI.saveFile(saveResult.filePath, res)
    ElMessage.success('导出成功')
  } catch {
    ElMessage.error('导出失败，请重试')
  } finally {
    exportLoading.value = false
  }
}

// ── 重置 ──────────────────────────────────────────
function resetForm() {
  form.issuing_unit         = '研发部'
  form.date                 = todayStr()
  form.project              = ''
  form.change_type          = '设计变更'
  form.change_type_custom   = ''
  form.distribution         = ['采购', '生产', '生管', '品管']
  form.change_reason        = ''
  form.change_reason_custom = ''
  form.change_subject       = ''
  form.change_desc          = ''
  bomGroups.value           = [newGroup()]
  Object.keys(reminderChecked).forEach(k => delete reminderChecked[k])
  form.ecr_code             = generateEcrCode(false)
  // 滚动归顶，避免视觉上看不出已重置
  nextTick(() => {
    if (formLeftRef.value)  formLeftRef.value.scrollTop  = 0
    if (formRightRef.value) formRightRef.value.scrollTop = 0
  })
}
</script>

<template>
  <div class="ecr-form-wrap">
    <div class="ecr-scroll-area">
    <div class="ecr-form">

      <!-- ── 左侧：表单主体 ─────────────────────── -->
      <div class="form-left" ref="formLeftRef">

        <div class="section-label">基本信息</div>

        <div class="form-row form-row--3">
          <div class="form-item">
            <label class="form-label">发出单位 <span class="req">*</span></label>
            <el-input v-model="form.issuing_unit" placeholder="请输入发出单位" />
          </div>
          <div class="form-item">
            <label class="form-label">日期</label>
            <el-input v-model="form.date" disabled />
          </div>
          <div class="form-item">
            <label class="form-label">变更编码 <span class="req">*</span></label>
            <el-input v-model="form.ecr_code" placeholder="自动生成，可修改" />
          </div>
        </div>

        <div class="form-row form-row--full">
          <div class="form-item">
            <label class="form-label">变更项目 <span class="req">*</span></label>
            <el-input v-model="form.project" placeholder="请输入变更项目名称" />
          </div>
        </div>

        <div class="section-label">变更分类</div>

        <div class="form-row form-row--full">
          <div class="form-item">
            <label class="form-label">变更类型 <span class="req">*</span></label>
            <el-radio-group v-model="form.change_type" class="radio-group">
              <el-radio v-for="opt in CHANGE_TYPE_OPTS" :key="opt" :value="opt">{{ opt }}</el-radio>
            </el-radio-group>
            <el-input
              v-if="form.change_type === '其他'"
              v-model="form.change_type_custom"
              placeholder="请说明变更类型"
              style="margin-top:6px"
            />
          </div>
        </div>

        <div class="form-row form-row--full">
          <div class="form-item">
            <label class="form-label">变更原因 <span class="req">*</span></label>
            <el-radio-group v-model="form.change_reason" class="radio-group">
              <el-radio v-for="opt in REASON_OPTS" :key="opt" :value="opt">{{ opt }}</el-radio>
            </el-radio-group>
            <el-input v-show="form.change_reason === '其他'" v-model="form.change_reason_custom"
              placeholder="请说明变更原因" style="margin-top:6px" />
          </div>
        </div>

        <div class="form-row form-row--full">
          <div class="form-item">
            <label class="form-label">分发单位 <span class="req">*</span></label>
            <el-checkbox-group v-model="form.distribution" class="check-group">
              <el-checkbox v-for="opt in DISTRIBUTION_OPTS" :key="opt" :value="opt">{{ opt }}</el-checkbox>
            </el-checkbox-group>
          </div>
        </div>

        <div class="section-label">变更内容</div>

        <div class="form-row form-row--full">
          <div class="form-item">
            <label class="form-label">变更主题 <span class="req">*</span></label>
            <el-input v-model="form.change_subject" type="textarea" :rows="2" placeholder="简要描述变更主题" />
          </div>
        </div>

        <div class="form-row form-row--full">
          <div class="form-item">
            <label class="form-label">变更内容说明 <span class="req">*</span></label>
            <el-input v-model="form.change_desc" type="textarea" :rows="4" placeholder="详细说明更改哪些内容" />
          </div>
        </div>

        <div class="form-actions">
          <el-button @click="resetForm">重置</el-button>
          <el-button @click="handlePreview">预览</el-button>
          <el-button type="primary" :loading="exportLoading" @click="handleExport">导出 XLSX</el-button>
        </div>

      </div>

      <!-- ── 右侧：材料明细 ────────────────────── -->
      <div class="form-right" ref="formRightRef">

        <div class="section-label">
          材料明细表
          <button class="btn-add-group" @click="addBomGroup">
            <el-icon><Plus /></el-icon> 添加变更
          </button>
        </div>

        <!-- 每个 BOM 变更组 -->
        <div
          v-for="(group, idx) in bomGroups"
          :key="idx"
          class="bom-group"
          :class="{ 'bom-group--has-result': diffRowsFor(group).length }"
        >
          <!-- 组头 -->
          <div class="bom-group-header">
            <span class="bom-group-title">变更 {{ idx + 1 }}</span>
            <button v-if="bomGroups.length > 1" class="btn-remove-group" @click="removeBomGroup(idx)">移除</button>
          </div>

          <!-- 文件选择（左右排列） -->
          <div class="bom-files">
            <div class="form-item">
              <label class="form-label">变更前</label>
              <div class="file-picker">
                <el-button size="small" @click="selectBomFile('before', idx)">选择文件</el-button>
                <span class="file-name" :class="{ 'file-name--set': group.before_name }">
                  {{ group.before_name || '未选择' }}
                </span>
                <el-icon v-if="group.before_name" class="file-clear"
                  @click="group.before_path = ''; group.before_name = ''; group.compareResult = null"><Close /></el-icon>
              </div>
            </div>
            <div class="form-item">
              <label class="form-label">变更审核中</label>
              <div class="file-picker">
                <el-button size="small" @click="selectBomFile('after', idx)">选择文件</el-button>
                <span class="file-name" :class="{ 'file-name--set': group.after_name }">
                  {{ group.after_name || '未选择' }}
                </span>
                <el-icon v-if="group.after_name" class="file-clear"
                  @click="group.after_path = ''; group.after_name = ''; group.compareResult = null"><Close /></el-icon>
              </div>
            </div>
          </div>

          <!-- 比对操作栏 -->
          <div v-if="group.before_path && group.after_path" class="compare-bar">
            <el-button size="small" :loading="group.compareLoading" @click="handleCompare(idx)">开始比对</el-button>
            <span v-if="group.compareResult" class="compare-stat">
              <template v-if="group.compareResult.stats.total === 0">无差异</template>
              <template v-else>
                共 {{ group.compareResult.stats.total }} 条变动<template v-if="group.compareResult.stats.version">，{{ group.compareResult.stats.version }} 项版本变更</template><template v-if="group.compareResult.stats.added">，{{ group.compareResult.stats.added }} 项新增</template><template v-if="group.compareResult.stats.deleted">，{{ group.compareResult.stats.deleted }} 项删除</template>
              </template>
            </span>
          </div>

          <!-- 确认栏：比对完成后显示，确认后才纳入预览/导出 -->
          <div v-if="group.compareResult" class="confirm-bar">
            <template v-if="!group.confirmed">
              <el-button size="small" type="primary" @click="group.confirmed = true">确认此变更</el-button>
              <span class="confirm-hint">确认后将纳入预览和导出</span>
            </template>
            <template v-else>
              <span class="confirmed-mark">✓ 已确认</span>
              <button class="btn-unconfirm" @click="group.confirmed = false">取消确认</button>
            </template>
          </div>

          <!-- 比对结果表格 -->
          <div v-if="diffRowsFor(group).length" class="compare-result">
            <table class="diff-table">
              <thead>
                <tr>
                  <th class="col-seq">序号</th>
                  <th class="col-level">层次</th>
                  <th>图号（前）</th>
                  <th class="col-arrow">→</th>
                  <th>图号（后）</th>
                  <th>品名</th>
                  <th>规格</th>
                  <th class="col-content">变更内容</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in diffRowsFor(group)" :key="row.seq" :class="`diff-row--${row.row_type}`">
                  <td class="tc">{{ row.seq }}</td>
                  <td class="tc">{{ row.level }}</td>
                  <td class="mono">{{ row.drawing_before || '—' }}</td>
                  <td class="tc">→</td>
                  <td class="mono">{{ row.drawing_after || '—' }}</td>
                  <td>{{ row.name }}</td>
                  <td>
                    <template v-if="row.spec_before !== row.spec_after">
                      <span class="val-old">{{ row.spec_before || '—' }}</span>
                      <span class="val-arrow"> → </span>
                      <span class="val-new">{{ row.spec_after || '—' }}</span>
                    </template>
                    <template v-else>{{ row.spec_after || '' }}</template>
                  </td>
                  <td class="content-cell">{{ row.change_content }}</td>
                </tr>
              </tbody>
            </table>
          </div>

        </div>
      </div>

    </div>
    </div><!-- /ecr-scroll-area -->

    <!-- ── 底部：变更提醒项 ────────────────────── -->
    <div class="ecr-reminder">
      <div class="section-label">
        变更提醒
        <span class="section-tip">在架提醒需全部勾选确认后方可导出</span>
        <button v-if="canAdminRd" class="btn-mgmt-reminder" @click="openMgmtDialog">
          <el-icon><Setting /></el-icon> 管理变更提醒
        </button>
      </div>

      <div v-if="remindersLoading" class="reminder-empty">加载中…</div>

      <div v-else-if="!reminders.length" class="reminder-empty">
        当前暂无在架变更提醒
      </div>

      <div v-else class="reminder-list">
        <div
          v-for="item in reminders"
          :key="item.id"
          class="reminder-card"
          :class="{ 'reminder-card--checked': reminderChecked[item.id] }"
        >
          <el-checkbox
            v-model="reminderChecked[item.id]"
            class="reminder-check"
          />
          <div class="reminder-body">
            <div class="reminder-content">{{ item.content }}</div>
            <div v-if="item.notes" class="reminder-notes">{{ item.notes }}</div>
            <div class="reminder-meta">发布于 {{ item.created_at }}{{ item.created_by ? '  ·  ' + item.created_by : '' }}</div>
          </div>
        </div>
      </div>
    </div>

  </div>

  <!-- ── 管理变更提醒弹窗 ───────────────────────── -->
  <el-dialog v-model="showMgmtDialog" title="管理变更提醒" width="min(720px, 94vw)" draggable :close-on-click-modal="false">
    <!-- 新建表单 -->
    <div class="mgmt-create-form">
      <div class="mgmt-create-title">新建提醒</div>
      <el-input
        v-model="newReminder.content"
        placeholder="提醒内容（必填）"
        maxlength="200"
        show-word-limit
      />
      <el-input
        v-model="newReminder.notes"
        type="textarea"
        :rows="2"
        placeholder="备注说明（选填，可补充背景或操作要求）"
        style="margin-top:8px"
      />
      <div style="text-align:right;margin-top:8px">
        <el-button type="primary" size="small" :loading="createLoading" @click="handleCreateReminder">
          发布提醒
        </el-button>
      </div>
    </div>

    <el-divider />

    <!-- 全部提醒列表 -->
    <div v-if="mgmtLoading" style="text-align:center;padding:20px;color:var(--text-muted)">加载中…</div>
    <div v-else-if="!mgmtReminders.length" style="text-align:center;padding:20px;color:var(--text-muted)">暂无记录</div>
    <div v-else class="mgmt-list">
      <div
        v-for="item in mgmtReminders"
        :key="item.id"
        class="mgmt-item"
        :class="{ 'mgmt-item--inactive': !item.is_active }"
      >
        <div class="mgmt-item-main">
          <div class="mgmt-item-content">{{ item.content }}</div>
          <div v-if="item.notes" class="mgmt-item-notes">{{ item.notes }}</div>
          <div class="mgmt-item-meta">
            {{ item.created_at }}
            <template v-if="item.created_by"> · {{ item.created_by }}</template>
            <el-tag v-if="!item.is_active" size="small" type="info" style="margin-left:8px">已下架</el-tag>
          </div>
        </div>
        <div class="mgmt-item-actions">
          <el-button v-if="item.is_active" size="small" type="danger" plain @click="handleDeactivate(item.id)">下架</el-button>
          <el-button v-else size="small" @click="handleActivate(item.id)">重新上架</el-button>
        </div>
      </div>
    </div>
  </el-dialog>

  <!-- ── 预览弹窗 ──────────────────────────────── -->
  <el-dialog v-model="showPreview" title="变更申请单预览" width="min(1200px, 96vw)" :close-on-click-modal="true" draggable style="--el-dialog-margin-top:3vh">
    <div class="preview-sheet">

      <div class="preview-top">
        <img :src="logoUrl" class="preview-logo" alt="" />
        <div class="preview-title">变 更 申 请 单</div>
        <div class="preview-docno">2M2-QM-25-01-A1</div>
      </div>

      <table class="preview-table">
        <tbody>
          <tr>
            <td class="pt-label">发出单位</td>
            <td class="pt-value" colspan="2">{{ form.issuing_unit }}</td>
            <td class="pt-label">日期</td>
            <td class="pt-value">{{ form.date }}</td>
            <td class="pt-label">变更编码</td>
            <td class="pt-value">{{ form.ecr_code }}</td>
            <td class="pt-label">变更项目</td>
            <td class="pt-value">{{ form.project }}</td>
          </tr>
          <tr>
            <td class="pt-label">变更类型</td>
            <td class="pt-value pt-check" colspan="8">{{ markText(CHANGE_TYPE_OPTS, form.change_type, form.change_type_custom) }}</td>
          </tr>
          <tr>
            <td class="pt-label">变更原因</td>
            <td class="pt-value pt-check" colspan="8">{{ markText(REASON_OPTS, form.change_reason, form.change_reason_custom) }}</td>
          </tr>
          <tr>
            <td class="pt-label">分发单位</td>
            <td class="pt-value pt-check" colspan="8">{{ markText(DISTRIBUTION_OPTS, form.distribution) }}</td>
          </tr>
          <tr><td class="pt-section" colspan="9">变更主题：</td></tr>
          <tr><td class="pt-value pt-multiline" colspan="9">{{ form.change_subject }}</td></tr>
          <tr><td class="pt-section" colspan="9">变更内容说明（详细说明更改哪些内容）：</td></tr>
          <tr><td class="pt-value pt-multiline pt-desc" colspan="9">{{ form.change_desc }}</td></tr>
          <tr><td class="pt-section" colspan="9">变更明细：</td></tr>
        </tbody>
      </table>

      <table class="preview-table preview-detail">
        <colgroup>
          <col class="c-seq" />
          <col class="c-main" />
          <col class="c-draw" />
          <col class="c-name" span="2" />
          <col class="c-spec" span="2" />
          <col class="c-meth" />
          <col class="c-rep" />
          <col class="c-dept" span="6" />
          <col class="c-disp" />
          <col class="c-resp" />
        </colgroup>
        <thead>
          <tr>
            <th rowspan="2">序号</th>
            <th rowspan="2">主件图号</th>
            <th rowspan="2">图号</th>
            <th rowspan="2" colspan="2">品名</th>
            <th rowspan="2" colspan="2">规格</th>
            <th rowspan="2">变更方式</th>
            <th rowspan="2">取替代关系<br>（原材料、半成品）</th>
            <th colspan="6">各部门问题反馈</th>
            <th rowspan="2">处置方式</th>
            <th rowspan="2">责任人</th>
          </tr>
          <tr>
            <th>研发</th><th>采购</th><th>品管</th><th>生管</th><th>生产</th><th>服务</th>
          </tr>
        </thead>
        <tbody>
          <template v-if="allChanges.length">
            <tr v-for="ch in allChanges" :key="ch.seq" :class="`detail-row--${ch.row_type}`">
              <td class="tc">{{ ch.seq }}</td>
              <td>{{ ch.main_drawing || '' }}</td>
              <td>{{ ch.drawing      || '' }}</td>
              <td colspan="2" class="tl">{{ ch.name }}</td>
              <td colspan="2" class="tl">{{ ch.spec }}</td>
              <td class="tl">{{ ch.change_method }}</td>
              <td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td>
            </tr>
          </template>
          <template v-else>
            <tr v-for="n in 6" :key="n">
              <td class="tc">{{ n }}</td>
              <td></td><td></td><td colspan="2"></td><td colspan="2"></td>
              <td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td>
            </tr>
          </template>
        </tbody>
      </table>

      <div class="preview-submitter">填写人员：{{ submitter }}</div>
    </div>

    <template #footer>
      <el-button @click="showPreview = false">关闭</el-button>
      <el-button type="primary" :loading="exportLoading" @click="showPreview = false; handleExport()">导出 XLSX</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
/* ── 外层容器：不滚动，flex 列布局 ── */
.ecr-form-wrap {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 24px 32px 0;
  box-sizing: border-box;
}

/* ── 上方可滚动区域（表单 + 材料明细） ── */
.ecr-scroll-area {
  flex: 1 1 0;
  min-height: 0;
  overflow: hidden;   /* 自身不滚动，由左右列各自滚动 */
}

/* ── 双列布局：左侧固定宽度，右侧占满剩余 ── */
.ecr-form {
  width: 100%;
  height: 100%;              /* 填满滚动区高度 */
  display: grid;
  grid-template-columns: minmax(480px, 560px) 1fr;
  gap: 0;
  align-items: stretch;      /* 两列等高 */
}

.form-left {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 0 28px 24px 0;
  border-right: 1px solid var(--border);
  overflow-y: auto;          /* 左列独立滚动 */
  height: 100%;
}
.form-left::-webkit-scrollbar       { width: 4px; }
.form-left::-webkit-scrollbar-thumb { background: rgba(0,0,0,0.18); border-radius: 2px; }
.form-left::-webkit-scrollbar-track { background: transparent; }

.form-right {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 0 0 24px 28px;
  overflow-y: auto;          /* 右列独立滚动 */
  height: 100%;
}
.form-right::-webkit-scrollbar       { width: 4px; }
.form-right::-webkit-scrollbar-thumb { background: rgba(0,0,0,0.18); border-radius: 2px; }
.form-right::-webkit-scrollbar-track { background: transparent; }

/* ── 区块标题 ── */
.section-label {
  font-size: 11px;
  font-weight: 700;
  color: var(--accent);
  letter-spacing: 0.06em;
  text-transform: uppercase;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--border);
  margin-top: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
  /* 在各自列内冻结 */
  position: sticky;
  top: 0;
  z-index: 2;
  background: inherit;
}
.section-label:first-child { margin-top: 0; }
.section-tip {
  font-size: 10px;
  font-weight: 400;
  color: var(--text-muted);
  letter-spacing: 0;
  text-transform: none;
}

/* ── 行布局（仅用于 form-left 内部） ── */
.form-row          { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.form-row--3       { grid-template-columns: 1fr 1fr 1fr; }
.form-row--full    { grid-template-columns: 1fr; }

.form-item         { display: flex; flex-direction: column; gap: 6px; }

.form-label        { font-size: 12px; font-weight: 600; color: var(--text-muted); letter-spacing: 0.03em; }
.req               { color: #c0402a; margin-left: 2px; }

.radio-group  { display: flex; flex-wrap: wrap; gap: 4px 16px; padding: 6px 0; }
.check-group  { display: flex; flex-wrap: wrap; gap: 4px 14px; padding: 6px 0; }

/* ── 文件选择 ── */
.file-picker {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  min-height: 32px;
}
.file-name {
  flex: 1;
  font-size: 12px;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.file-name--set    { color: var(--text-primary); }
.file-clear        { color: var(--text-muted); cursor: pointer; flex-shrink: 0; font-size: 13px; transition: color 0.15s; }
.file-clear:hover  { color: #c0402a; }

/* ── 操作栏 ── */
.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding-top: 8px;
  margin-top: 4px;
  border-top: 1px solid var(--border);
}

/* ── 添加变更按钮 ── */
.btn-add-group {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 4px;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 2px 10px;
  font-size: 11px;
  font-family: var(--font-family);
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.15s;
  text-transform: none;
  letter-spacing: 0;
  font-weight: 400;
}
.btn-add-group:hover { color: var(--accent); border-color: var(--accent); }

/* ── BOM 变更组 ── */
.bom-group {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px 14px;
  background: rgba(255,255,255,0.5);
  border: 1px solid var(--border);
  border-radius: 10px;
}
.bom-group--has-result { border-color: rgba(196,136,58,0.25); }

.bom-group-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.bom-group-title {
  font-size: 11px;
  font-weight: 700;
  color: var(--text-muted);
  letter-spacing: 0.04em;
}
.btn-remove-group {
  background: transparent;
  border: none;
  font-size: 11px;
  font-family: var(--font-family);
  color: var(--text-muted);
  cursor: pointer;
  padding: 0 4px;
  transition: color 0.15s;
}
.btn-remove-group:hover { color: #c0402a; }

/* 文件选择左右排列 */
.bom-files {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

/* ── 确认栏 ── */
.confirm-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 0 2px;
  border-top: 1px solid var(--border);
}
.confirm-hint {
  font-size: 11px;
  color: var(--text-muted);
}
.confirmed-mark {
  font-size: 12px;
  font-weight: 600;
  color: #267840;
}
.btn-unconfirm {
  background: transparent;
  border: none;
  font-size: 11px;
  font-family: var(--font-family);
  color: var(--text-muted);
  cursor: pointer;
  padding: 0;
  transition: color 0.15s;
  text-decoration: underline;
  text-underline-offset: 2px;
}
.btn-unconfirm:hover { color: #c0402a; }

/* ── 比对结果区 ── */
.compare-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 2px 0;
  flex-wrap: wrap;
}
.compare-stat {
  font-size: 12px;
  color: var(--text-muted);
}

.compare-result {
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
}

.diff-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
}
.diff-table th {
  background: var(--bg-card);
  padding: 5px 7px;
  font-weight: 600;
  text-align: left;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
  font-size: 11px;
}
.diff-table td {
  padding: 4px 7px;
  border-bottom: 1px solid var(--border);
  vertical-align: middle;
  font-size: 11px;
}
.diff-table tr:last-child td { border-bottom: none; }
.diff-table .col-seq     { width: 32px; }
.diff-table .col-level   { width: 44px; }
.diff-table .col-arrow   { width: 18px; text-align: center; color: var(--text-muted); padding: 0 2px; }
.diff-table .col-content { width: 110px; }
.diff-table td.content-cell { font-size: 11px; white-space: nowrap; }
.diff-table td.tc      { text-align: center; color: var(--text-muted); }
.diff-table td.mono    { font-family: monospace; white-space: nowrap; }

/* 变化前后对比文字 */
.val-old   { color: #b03020; }
.val-new   { color: #267840; }
.val-arrow { color: var(--text-muted); }

/* 行底色 */
.diff-row--changed { background: rgba(196,136,58,0.05); }
.diff-row--added   { background: rgba(50,160,80,0.05);  }
.diff-row--deleted { background: rgba(192,64,42,0.05);  }

/* ── 预览样式 ── */
.preview-sheet {
  font-family: '宋体', 'SimSun', serif;
  font-size: 12px;
  color: #222;
  overflow-x: auto;
}
.preview-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}
.preview-logo   { height: 28px; width: auto; object-fit: contain; flex-shrink: 0; }
.preview-title  { flex: 1; text-align: center; font-size: 18px; font-weight: bold; letter-spacing: 0.15em; }
.preview-docno  { font-size: 10px; color: #666; flex-shrink: 0; }

.preview-table  { width: 100%; border-collapse: collapse; }
.preview-table td,
.preview-table th { border: 1px solid #999; padding: 4px 6px; font-size: 11px; vertical-align: middle; }
.pt-label       { background: #f0ede6; font-weight: 600; white-space: nowrap; text-align: center; width: 56px; }
.pt-value       { background: #fff; }
.pt-check       { letter-spacing: 0.05em; }
.pt-section     { background: #f0ede6; font-weight: 600; padding: 4px 8px; }
.pt-multiline   { white-space: pre-wrap; min-height: 28px; }
.pt-desc        { min-height: 52px; }

.preview-detail         { margin-top: 0; table-layout: fixed; min-width: 960px; }
.preview-detail th      { background: #f0ede6; font-weight: 600; text-align: center; font-size: 10px; padding: 3px 3px; }
.preview-detail td      { text-align: center; height: 20px; font-size: 10px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
/* 列宽：合计约 960px，可在 1200px 弹窗内完整显示 */
.preview-detail col.c-seq   { width: 30px; }
.preview-detail col.c-main  { width: 100px; }
.preview-detail col.c-draw  { width: 100px; }
.preview-detail col.c-name  { width: 65px; }   /* ×2 = 130px */
.preview-detail col.c-spec  { width: 85px; }   /* ×2 = 170px */
.preview-detail col.c-meth  { width: 55px; }
.preview-detail col.c-rep   { width: 70px; }
.preview-detail col.c-dept  { width: 34px; }   /* ×6 = 204px */
.preview-detail col.c-disp  { width: 60px; }
.preview-detail col.c-resp  { width: 50px; }
.preview-detail td.tl   { text-align: left; }
.preview-detail td.tc   { text-align: center; color: #666; }
.detail-row--cancel     { background: rgba(192,64,42,0.07); }
.detail-row--add        { background: rgba(50,160,80,0.07); }
.detail-row--added      { background: rgba(50,160,80,0.07); }
.detail-row--deleted    { background: rgba(192,64,42,0.07); }
.preview-submitter      { margin-top: 6px; font-size: 11px; text-align: right; color: #555; }

/* ── 变更提醒区：固定在底部，内容多时内部滚动 ── */
.ecr-reminder {
  flex: 0 0 25%;
  width: 100%;
  overflow-y: auto;
  border-top: 2px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 14px 0 20px;
}
.ecr-reminder::-webkit-scrollbar       { width: 4px; }
.ecr-reminder::-webkit-scrollbar-thumb { background: rgba(0,0,0,0.18); border-radius: 2px; }
.ecr-reminder::-webkit-scrollbar-track { background: transparent; }

/* 管理按钮 */
.btn-mgmt-reminder {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 4px;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 2px 10px;
  font-size: 11px;
  font-family: var(--font-family);
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.15s;
  text-transform: none;
  letter-spacing: 0;
  font-weight: 400;
}
.btn-mgmt-reminder:hover { color: var(--accent); border-color: var(--accent); }

/* 空态 */
.reminder-empty {
  font-size: 12px;
  color: var(--text-muted);
  padding: 12px 0;
  text-align: center;
  background: rgba(255,255,255,0.4);
  border: 1px dashed var(--border);
  border-radius: 8px;
}

/* 提醒列表横向排布 */
.reminder-list {
  display: flex;
  flex-direction: row;
  flex-wrap: wrap;
  gap: 10px;
}

/* 每张提醒卡片 */
.reminder-card {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  flex: 1 1 260px;
  min-width: 0;
  padding: 10px 14px;
  background: #fff;
  border: 2px solid #e8b96b;
  border-left: 5px solid #c4883a;
  border-radius: 8px;
  box-shadow: 0 1px 4px rgba(196,136,58,0.10);
  transition: border-color 0.15s, background 0.15s, opacity 0.15s;
}
.reminder-card--checked {
  border-color: rgba(38,120,64,0.4);
  border-left-color: #267840;
  background: rgba(38,120,64,0.03);
  opacity: 0.8;
}
.reminder-check { flex-shrink: 0; margin-top: 2px; }

.reminder-body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }

.reminder-content {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  line-height: 1.4;
  word-break: break-word;
}
.reminder-card--checked .reminder-content {
  text-decoration: line-through;
  color: var(--text-muted);
}
.reminder-notes {
  font-size: 11px;
  color: var(--text-muted);
  line-height: 1.4;
  word-break: break-word;
  white-space: pre-wrap;
}
.reminder-meta {
  font-size: 10px;
  color: #a09080;
  margin-top: 2px;
}

/* ── 管理弹窗样式 ── */
.mgmt-create-form {
  padding: 4px 0 0;
}
.mgmt-create-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-muted);
  margin-bottom: 8px;
}

.mgmt-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 360px;
  overflow-y: auto;
}
.mgmt-list::-webkit-scrollbar       { width: 4px; }
.mgmt-list::-webkit-scrollbar-thumb { background: rgba(0,0,0,0.15); border-radius: 2px; }
.mgmt-list::-webkit-scrollbar-track { background: transparent; }

.mgmt-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 10px 14px;
  background: #fff;
  border: 1px solid var(--border);
  border-left: 4px solid var(--accent);
  border-radius: 8px;
  transition: opacity 0.15s;
}
.mgmt-item--inactive {
  opacity: 0.5;
  border-left-color: #bbb;
}
.mgmt-item-main    { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
.mgmt-item-content { font-size: 13px; font-weight: 600; color: var(--text-primary); word-break: break-word; }
.mgmt-item-notes   { font-size: 12px; color: var(--text-muted); word-break: break-word; white-space: pre-wrap; }
.mgmt-item-meta    { font-size: 11px; color: #a09080; margin-top: 2px; display: flex; align-items: center; flex-wrap: wrap; gap: 4px; }
.mgmt-item-actions { flex-shrink: 0; }
</style>
