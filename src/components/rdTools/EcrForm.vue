<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, reactive, computed, onMounted, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Close, Plus, EditPen } from '@element-plus/icons-vue'
import http from '@/api/http.js'
import logoUrl from '@/assets/logo-banner.png'
import { downloadBlob, pickFile } from '@/utils/download.js'
import { useMaterialGateCheck } from '@/composables/useMaterialGateCheck'
import MaterialGateHitDialog from './MaterialGateHitDialog.vue'

// ── 当前用户 & 权限 ────────────────────────────────
const _user     = JSON.parse(localStorage.getItem('user') || '{}')
const submitter = _user.display_name || _user.username || ''


// ── 滚动容器引用（重置时归顶）──────────────────────
const formLeftRef  = ref(null)
const formRightRef = ref(null)

// ── 常量选项 ──────────────────────────────────────
const CHANGE_TYPE_OPTS  = ['设计变更', '制程变更', '其他']
const DISTRIBUTION_OPTS = ['研发', '业务', '采购', '生产', '生管', '品牌', '服务', '品管']
const REASON_OPTS       = ['品质不良', '价格变动', '设计优化', '结构优化', '成本优化', '工艺优化', '其他']


// ── 物料门禁校验 ──────────────────────────────────
// 门禁维护入口已移到研发工具首页"设置"分组（page-rd-tools.vue），这里只做校验展示。
const { checkMaterialCodes } = useMaterialGateCheck()

// ── 响应式状态 ────────────────────────────────────
const form = reactive({
  issuing_unit:         '研发部',
  date:                 todayStr(),
  ecr_code:             '',
  project:              '',
  change_type:          '设计变更',
  change_type_custom:   '',
  distribution:         ['采购', '生产', '生管', '品管'],
  change_reason:        '结构优化',
  change_reason_custom: '',
  change_subject:       '',
  change_desc:          '',
})

const exportLoading = ref(false)
const showPreview   = ref(false)


// 多个 BOM 变更组，每组独立的文件选择、比对结果和门禁校验结果
function newGroup() {
  return { before_path: '', before_name: '', after_path: '', after_name: '',
           before_file: null, after_file: null,   // 网页端存储 File 对象
           compareResult: null, compareLoading: false, confirmed: false,
           gateHits: { warn: [], block: [] }, gateHitsOk: true, gateChecking: false, gateDialogVisible: false }
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

// 预览用：处理 cancel+add 对的研发列合并显示
const previewRows = computed(() => {
  const rows = allChanges.value
  const result = []
  let i = 0
  while (i < rows.length) {
    const ch = rows[i]
    if (ch.row_type === 'cancel' && i + 1 < rows.length && rows[i + 1].row_type === 'add') {
      result.push({ ...ch,          rdText: ch.change_kind || '', rdRowspan: 2, rdSkip: false })
      result.push({ ...rows[i + 1], rdText: '',                   rdRowspan: 1, rdSkip: true  })
      i += 2
    } else {
      result.push({ ...ch, rdText: ch.qty_desc || ch.change_kind || '', rdRowspan: 1, rdSkip: false })
      i++
    }
  }
  return result
})

// ── 生命周期 ──────────────────────────────────────
onMounted(() => {
  form.ecr_code = generateEcrCode(false)
  fetchNotes()
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
        change_content: ch.qty_desc
          ? (kind === '数量变更' ? `数量变更 ${ch.qty_desc}` : ch.qty_desc)
          : kind,
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
  // 任一组存在门禁"禁止"级命中，不允许导出（禁止项必须先处理——下架门禁或移除该变更组）
  const blocked = bomGroups.value.find(g => g.gateHits.block.length)
  if (blocked) {
    ElMessage.warning('存在被物料门禁"禁止"的物料，请先处理后再导出')
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
  const g = bomGroups.value[idx]
  if (window.electronAPI) {
    const result = await window.electronAPI.showOpenDialog({
      filters: [{ name: 'Excel 文件', extensions: ['xlsx'] }],
      properties: ['openFile'],
    })
    if (result?.canceled || !result?.filePaths?.length) return
    const filePath = result.filePaths[0]
    const fileName = filePath.replace(/.*[/\\]/, '')
    if (type === 'before') { g.before_path = filePath; g.before_name = fileName; g.before_file = null }
    else                   { g.after_path  = filePath; g.after_name  = fileName; g.after_file  = null }
  } else {
    const file = await pickFile('.xlsx')
    if (!file) return
    if (type === 'before') { g.before_path = ''; g.before_name = file.name; g.before_file = file }
    else                   { g.after_path  = ''; g.after_name  = file.name; g.after_file  = file }
  }
  g.compareResult = null
  g.confirmed = false
}

async function handleCompare(idx) {
  const g = bomGroups.value[idx]
  const hasBefore = g.before_path || g.before_file
  const hasAfter  = g.after_path  || g.after_file
  if (!hasBefore || !hasAfter) { ElMessage.warning('请先选择两个 BOM 文件'); return }
  g.compareLoading = true
  g.compareResult  = null
  try {
    let res
    if (window.electronAPI) {
      res = await http.post('/api/rd/ecr/compare-bom', {
        bom_before_path: g.before_path,
        bom_after_path:  g.after_path,
      })
    } else {
      const fd = new FormData()
      fd.append('bom_before', g.before_file)
      fd.append('bom_after',  g.after_file)
      res = await http.post('/api/rd/ecr/compare-bom', fd)
    }
    if (res.success) {
      g.compareResult = res.data
      g.confirmed = false   // 重新比对后需要重新确认
      if (res.data.stats.total === 0) ElMessage.info('两份 BOM 无差异')
      // 对变更后（after）文件里出现的全部物料编码做门禁校验，不是只查 diff 出来的变动项——
      // after_codes 是后端在 compare-bom 里顺带算好的去重列表（未变更的物料也在其中）
      g.gateChecking = true
      const hits = await checkMaterialCodes(res.data.after_codes || [])
      g.gateHits   = { warn: hits.warn, block: hits.block }
      g.gateHitsOk = hits.ok
      g.gateChecking = false
      // 检测到门禁（或校验本身失败）时用弹窗展示，不再用行内 banner
      if (!hits.ok || hits.warn.length || hits.block.length) g.gateDialogVisible = true
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

    if (window.electronAPI) {
      const saveResult = await window.electronAPI.showSaveDialog({
        defaultPath: `${code} ${form.project} 变更申请单.xlsx`,
        filters: [{ name: 'Excel', extensions: ['xlsx'] }],
      })
      if (saveResult?.canceled || !saveResult?.filePath) return
      await window.electronAPI.saveFile(saveResult.filePath, res)
    } else {
      downloadBlob(res, `${code} ${form.project} 变更申请单.xlsx`)
    }
    ElMessage.success('导出成功')
  } catch {
    ElMessage.error('导出失败，请重试')
  } finally {
    exportLoading.value = false
  }
}

// ── 笔记面板 ──────────────────────────────────────
const notesOpen    = ref(false)
const notesWidth   = ref(272)               // px，可拖拽调整
const NOTES_W_MIN  = 200
const NOTES_W_MAX  = 520
const notesList    = ref([])
const noteInput    = ref('')
const notesLoading = ref(false)
const noteAdding   = ref(false)
const editingNoteId   = ref(null)   // 当前正在编辑的笔记 id
const editingNoteText = ref('')

async function fetchNotes() {
  notesLoading.value = true
  try {
    const res = await http.get('/api/rd/notes')
    if (res.success) notesList.value = res.data
  } finally {
    notesLoading.value = false
  }
}

function startNotesResize(e) {
  e.preventDefault()
  const startX = e.clientX
  const startW = notesWidth.value
  function onMove(ev) {
    // 向左拖 → 增大宽度；向右拖 → 减小宽度
    const delta = startX - ev.clientX
    notesWidth.value = Math.min(NOTES_W_MAX, Math.max(NOTES_W_MIN, startW + delta))
  }
  function onUp() {
    window.removeEventListener('mousemove', onMove)
    window.removeEventListener('mouseup',   onUp)
  }
  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup',   onUp)
}

async function addNote() {
  const text = noteInput.value.trim()
  if (!text) return
  noteAdding.value = true
  try {
    const res = await http.post('/api/rd/notes', { content: text })
    if (res.success) {
      notesList.value.unshift(res.data)
      noteInput.value = ''
    } else {
      ElMessage.error(res.message || '添加失败')
    }
  } finally {
    noteAdding.value = false
  }
}

function startEditNote(note) {
  editingNoteId.value   = note.id
  editingNoteText.value = note.content || note.text || ''
}

function cancelEditNote() {
  editingNoteId.value   = null
  editingNoteText.value = ''
}

async function saveEditNote(id) {
  const text = editingNoteText.value.trim()
  if (!text) return
  const res = await http.put(`/api/rd/notes/${id}`, { content: text })
  if (res.success) {
    const item = notesList.value.find(n => n.id === id)
    if (item) { item.content = res.data.content; item.text = res.data.content }
    cancelEditNote()
  } else {
    ElMessage.error(res.message || '保存失败')
  }
}

async function deleteNote(id) {
  try {
    await ElMessageBox.confirm('确认删除这条笔记？', '删除确认', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
      confirmButtonClass: 'el-button--danger',
    })
  } catch {
    return  // 用户点取消
  }
  const res = await http.delete(`/api/rd/notes/${id}`)
  if (res.success) {
    notesList.value = notesList.value.filter(n => n.id !== id)
  } else {
    ElMessage.error(res.message || '删除失败')
  }
}

function handleNoteKeydown(e) {
  // Ctrl/Cmd + Enter 提交
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') addNote()
}

// ── 重置 ──────────────────────────────────────────
function resetForm() {
  form.issuing_unit         = '研发部'
  form.date                 = todayStr()
  form.project              = ''
  form.change_type          = '设计变更'
  form.change_type_custom   = ''
  form.distribution         = ['采购', '生产', '生管', '品管']
  form.change_reason        = '结构优化'
  form.change_reason_custom = ''
  form.change_subject       = ''
  form.change_desc          = ''
  bomGroups.value           = [newGroup()]
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

    <!-- ── 中部主体：表单区 + 笔记面板 + 功能侧栏 ── -->
    <div class="ecr-body">

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
          <!-- 笔记按钮：跑道圆形，靠左 -->
          <button
            class="notes-pill-btn"
            :class="{ 'notes-pill-btn--active': notesOpen }"
            @click="notesOpen = !notesOpen"
          >
            <el-icon><EditPen /></el-icon>
            <span>笔记</span>
          </button>
          <div class="form-actions-right">
            <el-button @click="resetForm">重置</el-button>
            <el-button @click="handlePreview">预览</el-button>
            <el-button type="primary" :loading="exportLoading" @click="handleExport">导出 XLSX</el-button>
          </div>
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
                  @click="group.before_path = ''; group.before_name = ''; group.before_file = null; group.compareResult = null"><Close /></el-icon>
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
                  @click="group.after_path = ''; group.after_name = ''; group.after_file = null; group.compareResult = null"><Close /></el-icon>
              </div>
            </div>
          </div>

          <!-- 比对操作栏 -->
          <div v-if="(group.before_path || group.before_file) && (group.after_path || group.after_file)" class="compare-bar">
            <el-button size="small" :loading="group.compareLoading" @click="handleCompare(idx)">开始比对</el-button>
            <span v-if="group.compareResult" class="compare-stat">
              <template v-if="group.compareResult.stats.total === 0">无差异</template>
              <template v-else>
                共 {{ group.compareResult.stats.total }} 条变动<template v-if="group.compareResult.stats.version">，{{ group.compareResult.stats.version }} 项版本变更</template><template v-if="group.compareResult.stats.added">，{{ group.compareResult.stats.added }} 项新增</template><template v-if="group.compareResult.stats.deleted">，{{ group.compareResult.stats.deleted }} 项删除</template>
              </template>
            </span>
          </div>

          <!-- 门禁提示：比对完成后对 after 文件里的全部物料编码做过校验，检测到命中会自动弹窗；
               关闭弹窗后用这条小提示可以随时重新打开（block 存在时禁用确认按钮的逻辑不受影响） -->
          <div v-if="group.gateChecking" class="gate-checking-hint">门禁校验中…</div>
          <div
            v-else-if="group.compareResult && (!group.gateHitsOk || group.gateHits.warn.length || group.gateHits.block.length)"
            class="gate-reopen-hint"
            :class="{ 'gate-reopen-hint--block': group.gateHits.block.length }"
            @click="group.gateDialogVisible = true"
          >
            {{ group.gateHitsOk
              ? `存在 ${group.gateHits.block.length + group.gateHits.warn.length} 项物料门禁提示，点击查看`
              : '物料门禁校验未完成，点击查看' }}
          </div>
          <MaterialGateHitDialog v-model="group.gateDialogVisible" :hits="group.gateHits" :ok="group.gateHitsOk" />

          <!-- 确认栏：比对完成后显示，确认后才纳入预览/导出；命中门禁"禁止"时不可确认 -->
          <div v-if="group.compareResult" class="confirm-bar">
            <template v-if="!group.confirmed">
              <el-button size="small" type="primary" :disabled="!!group.gateHits.block.length" @click="group.confirmed = true">确认此变更</el-button>
              <span class="confirm-hint">
                {{ group.gateHits.block.length ? '存在被门禁"禁止"的物料，无法确认' : '确认后将纳入预览和导出' }}
              </span>
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

    <!-- ── 笔记悬浮入口（右上角） ──────────────── -->
    <!-- ── 笔记抽屉（覆盖，从右滑入） ──────────── -->
    <Transition name="notes-drawer">
      <div v-if="notesOpen" class="notes-drawer" :style="{ width: notesWidth + 'px' }">
        <!-- 左侧拖拽手柄 -->
        <div class="notes-resize-handle" @mousedown="startNotesResize" />
        <div class="notes-drawer-header">
          <span class="notes-drawer-title">笔记</span>
          <div class="notes-drawer-actions">
            <!-- 最小化（收起）按钮 -->
            <button class="notes-action-btn notes-action-btn--minimize" title="收起" @click="notesOpen = false">
              <span class="minimize-bar" />
            </button>
          </div>
        </div>

        <!-- 输入区 -->
        <div class="notes-input-area">
          <textarea
            v-model="noteInput"
            class="notes-input"
            placeholder="记录一条笔记…"
            rows="3"
            @keydown="handleNoteKeydown"
          />
          <div class="notes-input-footer">
            <span class="notes-input-hint">Ctrl+Enter 提交</span>
            <button class="notes-add-btn" :disabled="noteAdding" @click="addNote">{{ noteAdding ? '…' : '添加' }}</button>
          </div>
        </div>

        <!-- 笔记列表 -->
        <div class="notes-list">
          <div v-if="notesLoading" class="notes-empty">加载中…</div>
          <div v-else-if="!notesList.length" class="notes-empty">暂无笔记</div>
          <TransitionGroup name="note-item" tag="div" class="notes-list-inner">
            <div v-for="note in notesList" :key="note.id" class="note-item">
              <!-- 编辑模式 -->
              <template v-if="editingNoteId === note.id">
                <textarea
                  v-model="editingNoteText"
                  class="note-edit-input"
                  @keydown.ctrl.enter="saveEditNote(note.id)"
                  @keydown.esc="cancelEditNote"
                />
                <div class="note-edit-actions">
                  <button class="note-save-btn" @click="saveEditNote(note.id)">保存</button>
                  <button class="note-cancel-btn" @click="cancelEditNote">取消</button>
                </div>
              </template>
              <!-- 展示模式 -->
              <template v-else>
                <div class="note-item-text">{{ note.content || note.text }}</div>
                <div class="note-item-footer">
                  <span class="note-item-time">{{ note.time }}</span>
                  <div class="note-item-btns">
                    <button class="note-edit-btn" title="编辑" @click="startEditNote(note)">编辑</button>
                    <button class="note-delete-btn" title="删除" @click="deleteNote(note.id)">
                      <el-icon><Close /></el-icon>
                    </button>
                  </div>
                </div>
              </template>
            </div>
          </TransitionGroup>
        </div>
      </div>
    </Transition>

    </div><!-- /ecr-body -->

  </div>

  <!-- ── 预览弹窗 ──────────────────────────────── -->
  <el-dialog v-model="showPreview" title="变更申请单预览" width="min(1200px, 96vw)" :close-on-click-modal="true" draggable
    style="--el-dialog-margin-top:3vh"
    class="preview-dialog"
  >
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
          <col class="c-level" />
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
            <th rowspan="2">层次</th>
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
          <template v-if="previewRows.length">
            <tr v-for="ch in previewRows" :key="ch.seq + ch.row_type" :class="`detail-row--${ch.row_type}`">
              <td class="tc">{{ ch.seq }}</td>
              <td>{{ ch.main_drawing || '' }}</td>
              <td>{{ ch.drawing      || '' }}</td>
              <td class="tc">{{ ch.level || '' }}</td>
              <td colspan="2" class="tl">{{ ch.name }}</td>
              <td colspan="2" class="tl">{{ ch.spec }}</td>
              <td class="tl">{{ ch.change_method }}</td>
              <!-- 研发列：cancel+add 对合并，填入变更类型 -->
              <td v-if="!ch.rdSkip" :rowspan="ch.rdRowspan" class="tc rd-cell">{{ ch.rdText }}</td>
              <td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td>
            </tr>
          </template>
          <template v-else>
            <tr v-for="n in 6" :key="n">
              <td class="tc">{{ n }}</td>
              <td></td><td></td><td></td><td colspan="2"></td><td colspan="2"></td>
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
  padding: 24px 32px 0 32px;
  box-sizing: border-box;
}

/* ── 中部主体（抽屉定位锚点） ── */
.ecr-body {
  flex: 1 1 0;
  min-height: 0;
  position: relative;
  overflow: hidden;
  display: flex;        /* 让子元素 .ecr-scroll-area 的 flex: 1 生效 */
  flex-direction: column;
}

/* ── 上方可滚动区域（表单 + 材料明细） ── */
.ecr-scroll-area {
  flex: 1 1 0;
  min-width: 0;
  min-height: 0;
  overflow: hidden;   /* 自身不滚动，由左右列各自滚动 */
}


/* ── 笔记抽屉 ── */
.notes-drawer {
  position: absolute;
  top: 8px;
  right: 8px;
  bottom: 16px;
  /* width 由内联 style 动态控制 */
  z-index: 15;
  display: flex;
  flex-direction: column;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 12px;
  box-shadow: -4px 0 20px rgba(0,0,0,0.10), 0 4px 16px rgba(0,0,0,0.07);
  overflow: hidden;
}

/* 左侧拖拽手柄 */
.notes-resize-handle {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 6px;
  cursor: ew-resize;
  z-index: 1;
  border-radius: 12px 0 0 12px;
  transition: background 0.15s;
}
.notes-resize-handle:hover,
.notes-resize-handle:active {
  background: rgba(196,136,58,0.15);
}
.notes-drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 13px 14px 11px 16px;
  border-bottom: 1px solid var(--border);
  background: #faf7f2;
  flex-shrink: 0;
}
.notes-drawer-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--accent);
  letter-spacing: 0.06em;
}
.notes-drawer-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}
.notes-action-btn {
  background: transparent;
  border: none;
  font-size: 11px;
  font-family: var(--font-family);
  color: var(--text-muted);
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 4px;
  transition: color 0.15s, background 0.15s;
  display: flex;
  align-items: center;
  justify-content: center;
}
.notes-action-btn:hover                { color: var(--text-primary); background: rgba(0,0,0,0.05); }
.notes-action-btn--minimize            { width: 22px; height: 22px; }
.notes-action-btn--minimize:hover      { background: rgba(0,0,0,0.07); }
.minimize-bar {
  display: block;
  width: 12px;
  height: 2px;
  background: currentColor;
  border-radius: 1px;
}

/* 输入区 */
.notes-input-area {
  flex-shrink: 0;
  padding: 10px 12px 8px;
  border-bottom: 1px solid var(--border);
  background: #fdfbf8;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.notes-input {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 8px;
  outline: none;
  resize: none;
  padding: 8px 10px;
  font-size: 12.5px;
  font-family: var(--font-family);
  color: var(--text-primary);
  background: #fff;
  line-height: 1.6;
  box-sizing: border-box;
  transition: border-color 0.15s;
}
.notes-input:focus { border-color: var(--accent); }
.notes-input::placeholder { color: #c0b0a0; }
.notes-input-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.notes-input-hint {
  font-size: 10px;
  color: #b0a090;
}
.notes-add-btn {
  background: var(--accent);
  color: #fff;
  border: none;
  border-radius: 6px;
  padding: 3px 12px;
  font-size: 12px;
  font-family: var(--font-family);
  cursor: pointer;
  transition: background 0.15s;
}
.notes-add-btn:hover { background: #e09050; }

/* 笔记列表 */
.notes-list {
  flex: 1;
  overflow-y: auto;
  padding: 10px 12px 12px;
}
.notes-list::-webkit-scrollbar       { width: 4px; }
.notes-list::-webkit-scrollbar-thumb { background: rgba(0,0,0,0.15); border-radius: 2px; }
.notes-list::-webkit-scrollbar-track { background: transparent; }
.notes-list-inner {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.notes-empty {
  text-align: center;
  font-size: 12px;
  color: #c0b0a0;
  padding: 20px 0;
}
.note-item {
  background: #faf7f2;
  border: 1px solid var(--border);
  border-left: 3px solid var(--accent);
  border-radius: 8px;
  padding: 8px 10px;
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.note-item-text {
  font-size: 12.5px;
  color: var(--text-primary);
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}
.note-item-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.note-item-time {
  font-size: 10px;
  color: #b0a090;
}
.note-item-btns {
  display: flex;
  align-items: center;
  gap: 6px;
  opacity: 0;
  transition: opacity 0.15s;
}
.note-item:hover .note-item-btns { opacity: 1; }
.note-edit-btn {
  background: transparent;
  border: none;
  font-size: 11px;
  font-family: var(--font-family);
  color: var(--text-muted);
  cursor: pointer;
  padding: 0;
  transition: color 0.15s;
}
.note-edit-btn:hover { color: var(--accent); }
.note-delete-btn {
  background: transparent;
  border: none;
  color: #c8b8a8;
  cursor: pointer;
  font-size: 12px;
  padding: 0;
  display: flex;
  align-items: center;
  transition: color 0.15s;
}
.note-delete-btn:hover { color: #c0402a; }

/* 编辑模式 */
.note-edit-input {
  width: 100%;
  border: 1px solid var(--accent);
  border-radius: 6px;
  outline: none;
  resize: none;
  padding: 6px 8px;
  font-size: 12.5px;
  font-family: var(--font-family);
  color: var(--text-primary);
  background: #fff;
  line-height: 1.6;
  box-sizing: border-box;
  min-height: 60px;
}
.note-edit-actions {
  display: flex;
  gap: 6px;
  justify-content: flex-end;
  margin-top: 4px;
}
.note-save-btn {
  background: var(--accent);
  color: #fff;
  border: none;
  border-radius: 5px;
  padding: 2px 10px;
  font-size: 11px;
  font-family: var(--font-family);
  cursor: pointer;
  transition: background 0.15s;
}
.note-save-btn:hover { background: #e09050; }
.note-cancel-btn {
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 5px;
  padding: 2px 8px;
  font-size: 11px;
  font-family: var(--font-family);
  color: var(--text-muted);
  cursor: pointer;
  transition: border-color 0.15s, color 0.15s;
}
.note-cancel-btn:hover { border-color: var(--text-muted); color: var(--text-primary); }

/* 列表条目动画 */
.note-item-enter-active { transition: opacity 0.18s, transform 0.18s; }
.note-item-leave-active { transition: opacity 0.15s, transform 0.15s; }
.note-item-enter-from   { opacity: 0; transform: translateY(-6px); }
.note-item-leave-to     { opacity: 0; transform: translateX(10px); }

/* 抽屉滑入滑出动画 */
.notes-drawer-enter-active,
.notes-drawer-leave-active {
  transition: transform 0.24s cubic-bezier(0.4, 0, 0.2, 1),
              opacity   0.24s cubic-bezier(0.4, 0, 0.2, 1);
}
.notes-drawer-enter-from,
.notes-drawer-leave-to {
  transform: translateX(100%);
  opacity: 0;
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
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding-top: 8px;
  margin-top: 4px;
  border-top: 1px solid var(--border);
}
.form-actions-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* ── 笔记跑道按钮 ── */
.notes-pill-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 14px 5px 10px;
  border-radius: 999px;
  border: 1.5px solid var(--accent);
  background: rgba(196,136,58,0.08);
  color: var(--accent);
  font-family: var(--font-family);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s, box-shadow 0.15s;
  box-shadow: 0 1px 4px rgba(196,136,58,0.15);
}
.notes-pill-btn:hover {
  background: rgba(196,136,58,0.15);
  box-shadow: 0 2px 8px rgba(196,136,58,0.25);
}
.notes-pill-btn--active {
  background: var(--accent);
  color: #fff;
  box-shadow: 0 2px 10px rgba(196,136,58,0.35);
}
.notes-pill-btn .el-icon { font-size: 15px; }

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
.preview-detail col.c-seq   { width: 28px; }
.preview-detail col.c-main  { width: 95px; }
.preview-detail col.c-draw  { width: 95px; }
.preview-detail col.c-level { width: 36px; }
.preview-detail col.c-name  { width: 60px; }   /* ×2 = 120px */
.preview-detail col.c-spec  { width: 80px; }   /* ×2 = 160px */
.preview-detail col.c-meth  { width: 50px; }
.preview-detail col.c-rep   { width: 68px; }
.preview-detail col.c-dept  { width: 32px; }   /* ×6 = 192px */
.preview-detail col.c-disp  { width: 55px; }
.preview-detail col.c-resp  { width: 48px; }
.preview-detail td.tl   { text-align: left; }
.preview-detail td.tc   { text-align: center; color: #666; }
.preview-detail td.rd-cell { font-size: 10px; color: #555; vertical-align: middle; }
.detail-row--cancel,
.detail-row--deleted    { background: rgba(192,64,42,0.07); }
.detail-row--add        { background: rgba(50,160,80,0.07); }
.detail-row--added      { background: rgba(50,160,80,0.07); }
.detail-row--deleted    { background: rgba(192,64,42,0.07); }
.preview-submitter      { margin-top: 6px; font-size: 11px; text-align: right; color: #555; }

.gate-checking-hint {
  font-size: 12px;
  color: var(--text-muted);
  padding: 6px 0;
}

/* 门禁弹窗关闭后的重新打开提示条 */
.gate-reopen-hint {
  font-size: 12px;
  color: #8a5a1e;
  background: rgba(196,136,58,0.10);
  border: 1px solid rgba(196,136,58,0.4);
  border-radius: 6px;
  padding: 6px 10px;
  margin: 6px 0;
  cursor: pointer;
  width: fit-content;
}
.gate-reopen-hint:hover { text-decoration: underline; }
.gate-reopen-hint--block {
  color: #a3311e;
  background: rgba(192,64,42,0.08);
  border-color: rgba(192,64,42,0.35);
}


</style>

<!-- 非 scoped：el-dialog 通过 teleport 渲染到 body，scoped 样式无法穿透 -->
<style>
.preview-dialog .el-dialog__body {
  max-height: calc(80vh - 120px);
  overflow-y: auto;
}
.preview-dialog .el-dialog__body::-webkit-scrollbar       { width: 4px; }
.preview-dialog .el-dialog__body::-webkit-scrollbar-thumb { background: rgba(0,0,0,0.18); border-radius: 2px; }
.preview-dialog .el-dialog__body::-webkit-scrollbar-track { background: transparent; }
</style>
