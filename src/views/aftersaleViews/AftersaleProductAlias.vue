<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Edit, Delete } from '@element-plus/icons-vue'
import http from '@/api/http.js'

// ── Props / Emits ─────────────────────────────────
const props = defineProps({
  modelValue: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue', 'updated'])

// ── 响应式状态 ────────────────────────────────────
const loading     = ref(false)
const submitting  = ref(false)
const aliases     = ref([])   // [{id, alias, product_codes:[], sort_order}]

// 表单：null = 隐藏
const form        = ref(null)
const formError   = ref('')

// 品号自动补全
const codeInput   = ref('')
const codeSuggestions = ref([])
let   suggestTimer = null

const visible = ref(false)
watch(() => props.modelValue, (v) => {
  visible.value = v
  if (v) { loadAliases(); form.value = null }
})
watch(visible, (v) => emit('update:modelValue', v))

// ── 方法 ──────────────────────────────────────────

async function loadAliases() {
  loading.value = true
  try {
    const res = await http.get('/api/aftersale/product-aliases')
    if (res.success) aliases.value = res.data
  } finally {
    loading.value = false
  }
}

// 新建
function startNew() {
  form.value      = { id: null, alias: '', product_codes: [], sort_order: 0 }
  formError.value = ''
  codeInput.value = ''
}

// 编辑
function startEdit(item) {
  form.value      = { id: item.id, alias: item.alias,
                      product_codes: [...item.product_codes],
                      sort_order: item.sort_order }
  formError.value = ''
  codeInput.value = ''
}

function cancelForm() {
  form.value = null
}

async function submitForm() {
  formError.value = ''
  const alias = (form.value.alias || '').trim()
  if (!alias) { formError.value = '简称不能为空'; return }
  if (!form.value.product_codes.length) { formError.value = '至少添加一个品号'; return }

  submitting.value = true
  try {
    const payload = {
      alias:         alias,
      product_codes: form.value.product_codes,
      sort_order:    Number(form.value.sort_order) || 0,
    }
    const isNew = form.value.id === null
    const res = isNew
      ? await http.post('/api/aftersale/product-aliases', payload)
      : await http.put(`/api/aftersale/product-aliases/${form.value.id}`, payload)

    if (res.success) {
      ElMessage.success(isNew ? '已创建' : '已更新')
      form.value = null
      await loadAliases()
      emit('updated')
    } else {
      formError.value = res.message || '操作失败'
    }
  } finally {
    submitting.value = false
  }
}

async function deleteAlias(item) {
  try {
    await ElMessageBox.confirm(
      `确认删除简称「${item.alias}」？`,
      '删除简称',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
    )
  } catch { return }

  const res = await http.delete(`/api/aftersale/product-aliases/${item.id}`)
  if (res.success) {
    ElMessage.success('已删除')
    if (form.value?.id === item.id) form.value = null
    await loadAliases()
    emit('updated')
  } else {
    ElMessage.error(res.message || '删除失败')
  }
}

// ── 品号编辑 ──────────────────────────────────────

// 输入品号时触发防抖查询建议
function onCodeInput(val) {
  clearTimeout(suggestTimer)
  if (!val.trim()) { codeSuggestions.value = []; return }
  suggestTimer = setTimeout(async () => {
    const res = await http.get('/api/aftersale/product-code-suggestions', { params: { q: val } })
    if (res.success) codeSuggestions.value = res.data
  }, 300)
}

// 从输入框确认添加品号（回车 / 点击建议）
function addCode(code) {
  const c = (code || codeInput.value || '').trim().toUpperCase()
  if (!c || !form.value) return
  if (!form.value.product_codes.includes(c)) {
    form.value.product_codes.push(c)
  }
  codeInput.value     = ''
  codeSuggestions.value = []
}

function removeCode(idx) {
  form.value?.product_codes.splice(idx, 1)
}
</script>

<template>
  <el-dialog
    v-model="visible"
    title="物料简称管理"
    width="680px"
    :close-on-click-modal="false"
    destroy-on-close
  >
    <div v-loading="loading" class="alias-lib">

      <!-- ── 左列：简称列表 ──────────────────────── -->
      <div class="col-list">
        <div class="col-header">
          <span class="col-title">已定义简称</span>
          <button class="btn-add" title="新建简称" @click="startNew">＋</button>
        </div>

        <div class="list-scroll">
          <div
            v-for="item in aliases"
            :key="item.id"
            class="alias-item"
            :class="{ editing: form?.id === item.id }"
          >
            <div class="alias-item-main">
              <span class="alias-name">{{ item.alias }}</span>
              <div class="alias-codes">
                <span v-for="c in item.product_codes" :key="c" class="code-tag">{{ c }}</span>
              </div>
            </div>
            <div class="alias-actions">
              <button class="btn-tiny" title="编辑" @click="startEdit(item)">
                <el-icon><Edit /></el-icon>
              </button>
              <button class="btn-tiny btn-del" title="删除" @click="deleteAlias(item)">
                <el-icon><Delete /></el-icon>
              </button>
            </div>
          </div>
          <div v-if="aliases.length === 0" class="list-empty">
            暂无简称，点击右上角「＋」添加
          </div>
        </div>
      </div>

      <div class="col-divider"></div>

      <!-- ── 右列：表单 ────────────────────────── -->
      <div class="col-form">
        <template v-if="form">
          <div class="col-header">
            <span class="col-title">{{ form.id ? '编辑简称' : '新建简称' }}</span>
          </div>

          <!-- 简称名称 -->
          <div class="form-row">
            <label class="form-label">简称 <span class="required">*</span></label>
            <el-input
              v-model="form.alias"
              placeholder="如：主机套装、气弹簧"
              @keyup.enter="submitForm"
            />
          </div>

          <!-- 产品代码列表 -->
          <div class="form-row">
            <label class="form-label">包含品号 <span class="required">*</span></label>
            <div class="code-editor">
              <!-- 已添加的品号 tags -->
              <div class="code-tags">
                <span
                  v-for="(c, i) in form.product_codes"
                  :key="i"
                  class="code-tag code-tag--removable"
                >
                  {{ c }}
                  <button class="tag-remove" @click="removeCode(i)">×</button>
                </span>
              </div>

              <!-- 品号输入 + 建议 -->
              <div class="code-input-wrap">
                <el-input
                  v-model="codeInput"
                  size="small"
                  placeholder="输入品号回车添加"
                  @input="onCodeInput"
                  @keyup.enter="addCode()"
                />
              </div>

              <!-- 自动补全建议 -->
              <div v-if="codeSuggestions.length" class="code-suggestions">
                <div
                  v-for="s in codeSuggestions"
                  :key="s.code"
                  class="suggestion-item"
                  @click="addCode(s.code)"
                >
                  <span class="sug-code">{{ s.code }}</span>
                  <span class="sug-name">{{ s.name }}</span>
                </div>
              </div>

              <div class="code-hint">输入品号后回车，或从建议中点击选择</div>
            </div>
          </div>

          <!-- 排序 -->
          <div class="form-row">
            <label class="form-label">排序</label>
            <el-input-number
              v-model="form.sort_order"
              :min="0"
              :step="1"
              controls-position="right"
              style="width:100px"
            />
          </div>

          <div v-if="formError" class="form-error">{{ formError }}</div>

          <div class="form-actions">
            <el-button size="small" @click="cancelForm">取消</el-button>
            <el-button size="small" type="primary" :loading="submitting" @click="submitForm">
              {{ form.id ? '保存' : '创建' }}
            </el-button>
          </div>
        </template>

        <div v-else class="form-placeholder">
          <div class="placeholder-icon">🏷️</div>
          <div>选择简称编辑，或点击「＋」新建</div>
        </div>
      </div>

    </div>
  </el-dialog>
</template>

<style scoped>
.alias-lib {
  display: flex; height: 420px;
}

.col-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 10px; flex-shrink: 0;
}
.col-title {
  font-size: 12px; font-weight: 600; color: var(--text-muted);
  text-transform: uppercase; letter-spacing: 0.05em;
}
.btn-add {
  width: 22px; height: 22px; border-radius: 5px;
  border: 1px dashed var(--border); background: transparent;
  color: var(--text-muted); cursor: pointer; font-size: 14px;
  display: flex; align-items: center; justify-content: center;
  transition: all 0.15s;
}
.btn-add:hover { border-color: var(--accent); color: var(--accent); }

/* ── 左列 ────────────────── */
.col-list {
  width: 280px; flex-shrink: 0;
  display: flex; flex-direction: column; overflow: hidden;
}

.list-scroll {
  flex: 1; overflow-y: auto;
}
.list-scroll::-webkit-scrollbar { width: 4px; }
.list-scroll::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

.alias-item {
  display: flex; align-items: flex-start; justify-content: space-between;
  padding: 8px 6px; border-radius: 6px;
  transition: background 0.15s; gap: 6px;
}
.alias-item:hover { background: var(--bg); }
.alias-item.editing { background: #fff7ed; }

.alias-item-main { flex: 1; overflow: hidden; }
.alias-name {
  font-size: 13px; font-weight: 600; color: var(--text-primary);
  display: block; margin-bottom: 4px;
}
.alias-codes {
  display: flex; flex-wrap: wrap; gap: 3px;
}
.code-tag {
  font-size: 10px; padding: 1px 6px;
  background: #f0ebe0; border: 1px solid var(--border);
  border-radius: 4px; color: var(--text-secondary);
  font-family: monospace;
}

.alias-actions {
  display: none; gap: 2px; flex-shrink: 0; padding-top: 2px;
}
.alias-item:hover .alias-actions { display: flex; }

.btn-tiny {
  width: 22px; height: 22px; border-radius: 4px;
  border: 1px solid var(--border); background: transparent;
  color: var(--text-muted); cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: all 0.15s;
}
.btn-tiny:hover { background: var(--bg-card); color: var(--text-primary); }
.btn-del:hover  { border-color: #f0c0c0; color: #d05a3c; background: #fff0ee; }

.list-empty {
  font-size: 12px; color: var(--text-muted);
  padding: 20px 0; text-align: center;
}

/* ── 分隔线 ────────────────── */
.col-divider {
  width: 1px; background: var(--border);
  margin: 0 14px; flex-shrink: 0;
}

/* ── 右列表单 ────────────────── */
.col-form {
  flex: 1; overflow-y: auto; min-width: 0;
}
.col-form::-webkit-scrollbar { width: 4px; }
.col-form::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

.form-row {
  margin-bottom: 14px;
}
.form-label {
  display: block; font-size: 12px; color: var(--text-secondary);
  margin-bottom: 5px;
}
.required { color: #d05a3c; }

.code-editor {
  background: #faf7f2; border: 1px solid var(--border);
  border-radius: 8px; padding: 8px 10px;
  position: relative;
}
.code-tags {
  display: flex; flex-wrap: wrap; gap: 4px; min-height: 24px;
  margin-bottom: 6px;
}
.code-tag--removable {
  display: flex; align-items: center; gap: 3px;
  padding-right: 4px;
}
.tag-remove {
  background: none; border: none; cursor: pointer;
  color: var(--text-muted); font-size: 12px; line-height: 1;
  padding: 0; transition: color 0.15s;
}
.tag-remove:hover { color: #d05a3c; }

.code-input-wrap { position: relative; }

.code-suggestions {
  position: absolute; left: 0; right: 0; z-index: 10;
  background: #fff; border: 1px solid var(--border);
  border-radius: 8px; box-shadow: 0 4px 16px rgba(0,0,0,0.08);
  max-height: 160px; overflow-y: auto;
  margin-top: 2px;
}
.suggestion-item {
  display: flex; align-items: center; gap: 10px;
  padding: 7px 12px; cursor: pointer; transition: background 0.12s;
}
.suggestion-item:hover { background: #faf7f2; }
.sug-code {
  font-family: monospace; font-size: 12px;
  font-weight: 600; color: var(--text-primary); flex-shrink: 0;
}
.sug-name {
  font-size: 11px; color: var(--text-muted);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}

.code-hint {
  font-size: 10px; color: var(--text-muted); margin-top: 6px;
}

.form-error {
  color: #d05a3c; font-size: 12px; margin-bottom: 10px;
}
.form-actions {
  display: flex; justify-content: flex-end; gap: 8px;
  padding-top: 4px;
}

.form-placeholder {
  height: 100%; display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  gap: 8px; color: var(--text-muted); font-size: 12px;
  text-align: center; padding: 20px;
}
.placeholder-icon { font-size: 28px; opacity: 0.4; }
</style>
