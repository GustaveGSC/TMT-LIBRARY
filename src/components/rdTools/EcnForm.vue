<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, reactive, computed, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { Close } from '@element-plus/icons-vue'
import http from '@/api/http.js'
import logoUrl from '@/assets/logo-banner.png'

// ── 当前用户 ──────────────────────────────────────
const _user     = JSON.parse(localStorage.getItem('user') || '{}')
const submitter = _user.display_name || _user.username || ''

// ── 滚动容器引用 ──────────────────────────────────
const formScrollRef = ref(null)

// ── 常量选项 ──────────────────────────────────────
const DISTRIBUTION_OPTS  = ['研发', '业务', '采购', '生产', '生管', '品牌', '服务', '品管']
const REASON_OPTS        = ['品质不良', '价格变动', '设计优化', '结构优化', '成本优化', '工艺优化', '其他']
const IMPORT_OPTS        = ['立即导入', '清化库存', '随单导入']
const AFFECTED_FILE_OPTS = ['图纸', '模具', 'QC检验图', '包装标准', '作业指导书', '材料比较单', 'BOM', '品检规范', '其他']

// ── 响应式状态 ────────────────────────────────────
// 来自 ECR 的信息（上传解析或手动填写）
const ecr = reactive({
  issuing_unit:   '研发部',
  date:           todayStr(),
  ecr_code:       '',
  project:        '',
  distribution:   [],
  change_reason:  '',
  change_reason_custom: '',
  change_desc:    '',
})

// ECN 专属字段
const form = reactive({
  ecn_code:       '',
  product:        '',
  import_method:  '立即导入',
  affected_files: ['图纸', 'BOM'],
  responsible:    '',           // 来自 ECR 解析（ECR 的填写人员）
})

// 变更明细（来自解析或手动）
const changes      = ref([])
const ecrFilePath  = ref('')
const ecrFileName  = ref('')
const parseLoading = ref(false)
const exportLoading = ref(false)
const showPreview   = ref(false)

// ── 工具函数 ──────────────────────────────────────
function todayStr() {
  return new Date().toISOString().slice(0, 10)
}

function generateEcnCode(consume = true) {
  const today = new Date().toISOString().slice(0, 10).replace(/-/g, '')
  const key   = `ecn_seq_${today}`
  const cur   = parseInt(sessionStorage.getItem(key) || '0')
  const seq   = cur + 1
  if (consume) sessionStorage.setItem(key, String(seq))
  return `ECN.${today}.${String(seq).padStart(2, '0')}`
}

function markText(opts, selected, custom = '') {
  return opts.map(o => {
    const checked = Array.isArray(selected) ? selected.includes(o) : selected === o
    if (checked && o === '其他' && custom) return `☑ 其他：${custom}`
    return checked ? `☑ ${o}` : `☐ ${o}`
  }).join('    ')
}

// ── 上传 ECR 文件并解析 ───────────────────────────
async function selectEcrFile() {
  const result = await window.electronAPI?.showOpenDialog({
    filters: [{ name: 'Excel 文件', extensions: ['xlsx', 'xls'] }],
    properties: ['openFile'],
  })
  if (result?.canceled || !result?.filePaths?.length) return
  const filePath = result.filePaths[0]
  ecrFilePath.value = filePath
  ecrFileName.value = filePath.replace(/.*[/\\]/, '')
  await parseEcr(filePath)
}

async function parseEcr(path) {
  parseLoading.value = true
  try {
    const res = await http.post('/api/rd/ecr/parse-ecr', { ecr_path: path })
    if (!res.success) { ElMessage.error(res.message || '解析失败'); return }
    const d = res.data
    ecr.issuing_unit         = d.issuing_unit  || ecr.issuing_unit
    ecr.date                 = d.date          || ecr.date
    ecr.ecr_code             = d.ecr_code      || ''
    ecr.project              = d.project       || ''
    ecr.distribution         = d.distribution  || []
    ecr.change_reason        = d.change_reason || ''
    ecr.change_desc          = d.change_desc   || ''
    form.product             = d.project       || ''
    form.responsible         = d.submitter     || ''
    changes.value            = d.changes       || []
    if (!form.ecn_code) form.ecn_code = generateEcnCode(false)
    ElMessage.success('解析成功，请确认信息后导出')
  } finally {
    parseLoading.value = false
  }
}

// ── 计算属性：预览用变更明细（cancel+add 对合并展示） ──
const previewChanges = computed(() => {
  const list   = changes.value
  const result = []
  let i = 0
  while (i < list.length) {
    const ch = list[i]
    if (ch.row_type === 'cancel' && i + 1 < list.length && list[i + 1].row_type === 'add') {
      result.push({ ...ch,          rdText: ch.change_kind || '', rdRowspan: 2, rdSkip: false })
      result.push({ ...list[i + 1], rdText: '',                   rdRowspan: 1, rdSkip: true  })
      i += 2
    } else {
      result.push({ ...ch, rdText: ch.change_kind || '', rdRowspan: 1, rdSkip: false })
      i++
    }
  }
  return result
})

// ── 校验 ──────────────────────────────────────────
function validate() {
  if (!form.ecn_code.trim())        { ElMessage.warning('请填写据报编号'); return false }
  if (!form.product.trim())         { ElMessage.warning('请填写产品型号'); return false }
  if (!ecr.issuing_unit.trim())     { ElMessage.warning('请填写发出单位'); return false }
  if (!form.import_method)          { ElMessage.warning('请选择导入方式'); return false }
  if (!form.affected_files.length)  { ElMessage.warning('请至少选择一项影响文件'); return false }
  if (!form.responsible.trim())     { ElMessage.warning('请填写负责人'); return false }
  return true
}

// ── 预览 ──────────────────────────────────────────
function handlePreview() {
  if (!validate()) return
  showPreview.value = true
}

// ── 导出 ──────────────────────────────────────────
async function handleExport() {
  if (!validate()) return
  exportLoading.value = true
  try {
    const code = generateEcnCode(true)
    form.ecn_code = code

    const res = await http.post('/api/rd/ecr/export-ecn', {
      // ECR 信息
      issuing_unit:         ecr.issuing_unit,
      date:                 ecr.date,
      ecr_code:             ecr.ecr_code,
      project:              ecr.project,
      distribution:         ecr.distribution,
      change_reason:        ecr.change_reason,
      change_reason_custom: ecr.change_reason_custom,
      change_desc:          ecr.change_desc,
      // ECN 专属
      ecn_code:       form.ecn_code,
      product:        form.product,
      import_method:  form.import_method,
      affected_files: form.affected_files,
      responsible:    form.responsible,
      // 明细
      changes: changes.value.length ? changes.value : null,
    }, { responseType: 'arraybuffer' })

    const saveResult = await window.electronAPI?.showSaveDialog({
      defaultPath: `${form.ecn_code} ${form.product} 变更通知单.xlsx`,
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
  ecrFilePath.value = ''
  ecrFileName.value = ''
  ecr.issuing_unit         = ''
  ecr.date                 = todayStr()
  ecr.ecr_code             = ''
  ecr.project              = ''
  ecr.distribution         = []
  ecr.change_reason        = ''
  ecr.change_reason_custom = ''
  ecr.change_desc          = ''
  form.ecn_code       = ''
  form.product        = ''
  form.import_method  = '立即导入'
  form.affected_files = ['图纸', 'BOM']
  form.responsible    = ''
  changes.value       = []
  nextTick(() => { if (formScrollRef.value) formScrollRef.value.scrollTop = 0 })
}
</script>

<template>
  <div class="ecn-wrap">
    <div class="ecn-scroll" ref="formScrollRef">
      <div class="ecn-body">

        <!-- ── 左列：信息填写 ───────────────────── -->
        <div class="col-left">

          <!-- 上传 ECR 申请单 -->
          <div class="section-label">上传变更申请单（ECR）</div>
          <div class="ecr-upload-bar">
            <el-button size="small" :loading="parseLoading" @click="selectEcrFile">
              选择 ECR 文件
            </el-button>
            <span class="file-name" :class="{ 'file-name--set': ecrFileName }">
              {{ ecrFileName || '未选择（选择后自动解析填充）' }}
            </span>
            <el-icon v-if="ecrFileName" class="file-clear" @click="resetForm">
              <Close />
            </el-icon>
          </div>

          <!-- 基本信息 -->
          <div class="section-label">基本信息</div>

          <div class="form-row form-row--3">
            <div class="form-item">
              <label class="form-label">发出单位 <span class="req">*</span></label>
              <el-input v-model="ecr.issuing_unit" placeholder="请输入发出单位" />
            </div>
            <div class="form-item">
              <label class="form-label">日期</label>
              <el-input v-model="ecr.date" disabled />
            </div>
            <div class="form-item">
              <label class="form-label">ECR 变更编码</label>
              <el-input v-model="ecr.ecr_code" placeholder="来自 ECR 申请单" />
            </div>
          </div>

          <div class="form-row form-row--2">
            <div class="form-item">
              <label class="form-label">产品型号 <span class="req">*</span></label>
              <el-input v-model="form.product" placeholder="如：JQ43120F（外贸捷克eliNeli）" />
            </div>
            <div class="form-item">
              <label class="form-label">据报编号（ECN） <span class="req">*</span></label>
              <el-input v-model="form.ecn_code" placeholder="自动生成，可修改" />
            </div>
          </div>

          <!-- 分类选项 -->
          <div class="section-label">变更分类</div>

          <div class="form-row form-row--full">
            <div class="form-item">
              <label class="form-label">分发单位</label>
              <el-checkbox-group v-model="ecr.distribution" class="check-group">
                <el-checkbox v-for="opt in DISTRIBUTION_OPTS" :key="opt" :value="opt">{{ opt }}</el-checkbox>
              </el-checkbox-group>
            </div>
          </div>

          <div class="form-row form-row--full">
            <div class="form-item">
              <label class="form-label">变更原因</label>
              <el-radio-group v-model="ecr.change_reason" class="radio-group">
                <el-radio v-for="opt in REASON_OPTS" :key="opt" :value="opt">{{ opt }}</el-radio>
              </el-radio-group>
              <el-input v-show="ecr.change_reason === '其他'" v-model="ecr.change_reason_custom"
                placeholder="请说明变更原因" style="margin-top:6px" />
            </div>
          </div>

          <div class="form-row form-row--full">
            <div class="form-item">
              <label class="form-label">变更内容说明</label>
              <el-input v-model="ecr.change_desc" type="textarea" :rows="3" placeholder="来自 ECR 申请单，可手动填写" />
            </div>
          </div>

          <!-- ECN 专属 -->
          <div class="section-label">通知单专项</div>

          <div class="form-row form-row--full">
            <div class="form-item">
              <label class="form-label">导入方式 <span class="req">*</span></label>
              <el-radio-group v-model="form.import_method" class="radio-group">
                <el-radio v-for="opt in IMPORT_OPTS" :key="opt" :value="opt">{{ opt }}</el-radio>
              </el-radio-group>
            </div>
          </div>

          <div class="form-row form-row--full">
            <div class="form-item">
              <label class="form-label">影响文件 <span class="req">*</span></label>
              <el-checkbox-group v-model="form.affected_files" class="check-group">
                <el-checkbox v-for="opt in AFFECTED_FILE_OPTS" :key="opt" :value="opt">{{ opt }}</el-checkbox>
              </el-checkbox-group>
            </div>
          </div>

          <div class="form-row form-row--full">
            <div class="form-item">
              <label class="form-label">负责人 <span class="req">*</span></label>
              <el-input v-model="form.responsible" placeholder="来自 ECR 填写人员，可修改" />
            </div>
          </div>

          <!-- 操作按钮 -->
          <div class="form-actions">
            <el-button @click="resetForm">重置</el-button>
            <el-button @click="handlePreview">预览</el-button>
            <el-button type="primary" :loading="exportLoading" @click="handleExport">导出 XLSX</el-button>
          </div>

        </div>

        <!-- ── 右列：变更明细预览 ─────────────── -->
        <div class="col-right">

          <div class="section-label">
            变更明细
            <span class="section-tip">来自 ECR 解析，{{ changes.length ? `共 ${changes.length} 条` : '暂无' }}</span>
          </div>

          <div v-if="!changes.length" class="empty-detail">
            选择 ECR 文件后自动填充，或上传后手动调整
          </div>

          <div v-else class="detail-wrap">
            <table class="diff-table">
              <thead>
                <tr>
                  <th class="col-seq">序</th>
                  <th class="col-level">层次</th>
                  <th>图号</th>
                  <th>品名</th>
                  <th>规格</th>
                  <th class="col-meth">方式</th>
                  <th class="col-kind">变更类型</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="row in previewChanges"
                  :key="row.seq + '-' + row.row_type"
                  :class="`diff-row--${row.row_type}`"
                >
                  <td class="tc">{{ row.seq }}</td>
                  <td class="tc">{{ row.level }}</td>
                  <td class="mono">{{ row.drawing }}</td>
                  <td>{{ row.name }}</td>
                  <td class="spec-cell">{{ row.spec }}</td>
                  <td class="tc">{{ row.change_method }}</td>
                  <td v-if="!row.rdSkip" :rowspan="row.rdRowspan" class="tc kind-cell">{{ row.rdText }}</td>
                </tr>
              </tbody>
            </table>
          </div>

        </div>

      </div>
    </div><!-- /ecn-scroll -->

    <!-- ── 预览弹窗 ──────────────────────────── -->
    <el-dialog
      v-model="showPreview"
      title="变更通知单预览"
      width="min(1100px, 96vw)"
      :close-on-click-modal="true"
      draggable
      style="--el-dialog-margin-top:3vh"
      class="ecn-preview-dialog"
    >
      <div class="preview-sheet">

        <div class="preview-top">
          <img :src="logoUrl" class="preview-logo" alt="" />
          <div class="preview-title">变 更 通 知 单</div>
          <div class="preview-docno">2M2-QM-25-03-A2</div>
        </div>

        <!-- 表头信息 -->
        <table class="preview-table">
          <tbody>
            <tr>
              <td class="pt-label">发出单位</td>
              <td class="pt-value">{{ ecr.issuing_unit }}</td>
              <td class="pt-label">产品型号</td>
              <td class="pt-value" colspan="2">{{ form.product }}</td>
              <td class="pt-label">负责人</td>
              <td class="pt-value" colspan="2">{{ form.responsible }}</td>
              <td class="pt-label">日期</td>
              <td class="pt-value">{{ ecr.date }}</td>
              <td class="pt-label ecn-code-label">{{ form.ecn_code }}</td>
            </tr>
            <tr>
              <td class="pt-label">导入方式</td>
              <td class="pt-value pt-check" colspan="10">
                {{ markText(IMPORT_OPTS, form.import_method) }}
              </td>
            </tr>
            <tr>
              <td class="pt-label">分发单位</td>
              <td class="pt-value pt-check" colspan="10">
                {{ markText(DISTRIBUTION_OPTS, ecr.distribution) }}
              </td>
            </tr>
            <tr>
              <td class="pt-label">变更原因</td>
              <td class="pt-value pt-check" colspan="10">
                {{ markText(REASON_OPTS, ecr.change_reason, ecr.change_reason_custom) }}
              </td>
            </tr>
            <tr>
              <td class="pt-label">变更内容</td>
              <td class="pt-value pt-multiline" colspan="10">{{ ecr.change_desc }}</td>
            </tr>
            <tr>
              <td class="pt-label">影响文件</td>
              <td class="pt-value pt-check" colspan="10">
                {{ markText(AFFECTED_FILE_OPTS, form.affected_files) }}
              </td>
            </tr>
          </tbody>
        </table>

        <!-- 明细表 -->
        <table class="preview-table preview-detail">
          <colgroup>
            <col style="width:28px" />
            <col style="width:80px" /><col style="width:80px" />
            <col style="width:80px" /><col style="width:80px" />
            <col style="width:36px" />
            <col style="width:90px" /><col style="width:90px" />
            <col style="width:110px" /><col style="width:110px" />
            <col style="width:55px" />
            <col style="width:80px" />
            <col style="width:65px" />
            <col style="width:55px" />
            <col style="width:55px" />
          </colgroup>
          <thead>
            <tr>
              <th>序号</th>
              <th colspan="2">主件图号</th>
              <th colspan="2">图号</th>
              <th>层次</th>
              <th colspan="2">品名</th>
              <th colspan="2">规格</th>
              <th>变更方式</th>
              <th>取替代关系</th>
              <th>处理意见</th>
              <th>负责人</th>
              <th>备注</th>
            </tr>
          </thead>
          <tbody>
            <template v-if="previewChanges.length">
              <tr
                v-for="row in previewChanges"
                :key="row.seq + '-' + row.row_type"
                :class="`detail-row--${row.row_type}`"
              >
                <td class="tc">{{ row.seq }}</td>
                <td colspan="2" class="mono">{{ row.main_drawing }}</td>
                <td colspan="2" class="mono">{{ row.drawing }}</td>
                <td class="tc">{{ row.level || '' }}</td>
                <td colspan="2" class="tl">{{ row.name }}</td>
                <td colspan="2" class="tl">{{ row.spec }}</td>
                <td class="tc">{{ row.change_method || '' }}</td>
                <td class="tc">{{ row.substitution || row.qty_desc || row.change_kind || '' }}</td>
                <td class="tc">{{ row.handling || '' }}</td>
                <td class="tc">{{ row.responsible_person || '' }}</td>
                <td></td>
              </tr>
            </template>
            <template v-else>
              <tr v-for="n in 5" :key="n">
                <td class="tc">{{ n }}</td>
                <td colspan="2"></td><td colspan="2"></td>
                <td></td>
                <td colspan="2"></td><td colspan="2"></td>
                <td></td><td></td><td></td><td></td><td></td>
              </tr>
            </template>
          </tbody>
        </table>

      </div>

      <template #footer>
        <el-button @click="showPreview = false">关闭</el-button>
        <el-button type="primary" :loading="exportLoading" @click="showPreview = false; handleExport()">导出 XLSX</el-button>
      </template>
    </el-dialog>

  </div>
</template>

<style scoped>
.ecn-wrap {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 24px 32px 0;
  box-sizing: border-box;
}

.ecn-scroll {
  flex: 1 1 0;
  min-height: 0;
  overflow-y: auto;
}
.ecn-scroll::-webkit-scrollbar       { width: 4px; }
.ecn-scroll::-webkit-scrollbar-thumb { background: rgba(0,0,0,0.18); border-radius: 2px; }
.ecn-scroll::-webkit-scrollbar-track { background: transparent; }

/* ── 双列布局 ── */
.ecn-body {
  width: 100%;
  min-height: 100%;
  display: grid;
  grid-template-columns: minmax(460px, 540px) 1fr;
  gap: 0;
  align-items: start;
  padding-bottom: 24px;
}

.col-left {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-right: 28px;
  border-right: 1px solid var(--border);
}

.col-right {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-left: 28px;
}

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
  position: sticky;
  top: 0;
  z-index: 2;
  background: var(--bg);
}
.section-label:first-child { margin-top: 0; }
.section-tip {
  font-size: 10px;
  font-weight: 400;
  color: var(--text-muted);
  letter-spacing: 0;
  text-transform: none;
}

/* ── ECR 上传栏 ── */
.ecr-upload-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  background: rgba(255,255,255,0.5);
  border: 1px dashed var(--border);
  border-radius: 10px;
}
.file-name {
  flex: 1;
  font-size: 12px;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.file-name--set   { color: var(--text-primary); }
.file-clear       { color: var(--text-muted); cursor: pointer; flex-shrink: 0; font-size: 13px; transition: color 0.15s; }
.file-clear:hover { color: #c0402a; }

/* ── 行布局 ── */
.form-row       { display: grid; gap: 16px; }
.form-row--2    { grid-template-columns: 1fr 1fr; }
.form-row--3    { grid-template-columns: 1fr 1fr 1fr; }
.form-row--full { grid-template-columns: 1fr; }

.form-item  { display: flex; flex-direction: column; gap: 6px; }
.form-label { font-size: 12px; font-weight: 600; color: var(--text-muted); letter-spacing: 0.03em; }
.req        { color: #c0402a; margin-left: 2px; }

.radio-group { display: flex; flex-wrap: wrap; gap: 4px 16px; padding: 6px 0; }
.check-group { display: flex; flex-wrap: wrap; gap: 4px 14px; padding: 6px 0; }

/* ── 操作栏 ── */
.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding-top: 8px;
  margin-top: 4px;
  border-top: 1px solid var(--border);
}

/* ── 右列：明细表 ── */
.empty-detail {
  font-size: 12px;
  color: var(--text-muted);
  padding: 20px;
  text-align: center;
  background: rgba(255,255,255,0.4);
  border: 1px dashed var(--border);
  border-radius: 10px;
}

.detail-wrap {
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
}
.diff-table td {
  padding: 4px 7px;
  border-bottom: 1px solid var(--border);
  vertical-align: middle;
}
.diff-table tr:last-child td { border-bottom: none; }
.diff-table .col-seq   { width: 28px; }
.diff-table .col-level { width: 40px; }
.diff-table .col-meth  { width: 40px; }
.diff-table .col-kind  { width: 70px; }
.diff-table .tc        { text-align: center; color: var(--text-muted); }
.diff-table .mono      { font-family: monospace; white-space: nowrap; }
.diff-table .spec-cell { max-width: 160px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.diff-table .kind-cell { font-size: 10px; color: #555; }

.diff-row--cancel,
.diff-row--deleted { background: rgba(192,64,42,0.06); }
.diff-row--add,
.diff-row--added   { background: rgba(50,160,80,0.06); }

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
.preview-logo  { height: 28px; width: auto; object-fit: contain; flex-shrink: 0; }
.preview-title { flex: 1; text-align: center; font-size: 18px; font-weight: bold; letter-spacing: 0.15em; }
.preview-docno { font-size: 10px; color: #666; flex-shrink: 0; }

.preview-table { width: 100%; border-collapse: collapse; }
.preview-table td,
.preview-table th { border: 1px solid #999; padding: 4px 6px; font-size: 11px; vertical-align: middle; }
.pt-label       { background: #f0ede6; font-weight: 600; white-space: nowrap; text-align: center; width: 56px; }
.pt-value       { background: #fff; }
.pt-check       { letter-spacing: 0.05em; }
.pt-multiline   { white-space: pre-wrap; min-height: 24px; }
.ecn-code-label { font-size: 11px; font-weight: 700; text-align: center; }

.preview-detail         { margin-top: 0; table-layout: fixed; min-width: 760px; }
.preview-detail th      { background: #f0ede6; font-weight: 600; text-align: center; font-size: 10px; padding: 3px; }
.preview-detail td      { text-align: center; height: 20px; font-size: 10px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.preview-detail .tc     { text-align: center; color: #666; }
.preview-detail .tl     { text-align: left; }
.preview-detail .mono   { font-family: monospace; }
.detail-row--cancel,
.detail-row--deleted { background: rgba(192,64,42,0.07); }
.detail-row--add,
.detail-row--added   { background: rgba(50,160,80,0.07); }

.preview-footer { margin-top: 6px; font-size: 11px; color: #555; }
</style>

<style>
.ecn-preview-dialog .el-dialog__body {
  max-height: calc(80vh - 120px);
  overflow-y: auto;
}
.ecn-preview-dialog .el-dialog__body::-webkit-scrollbar       { width: 4px; }
.ecn-preview-dialog .el-dialog__body::-webkit-scrollbar-thumb { background: rgba(0,0,0,0.18); border-radius: 2px; }
.ecn-preview-dialog .el-dialog__body::-webkit-scrollbar-track { background: transparent; }
</style>
