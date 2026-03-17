<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, reactive, computed } from 'vue'
import http from '@/api/http'
import { usePackagedStore } from '@/stores/product/packaged'


// ── Props / Emits ─────────────────────────────────
// modelValue: [{value: code, state: 'new'|'raw'|'delete'}]
//   state 语义：new=编码不在候选库里，raw=在库里，delete=标记删除
// options:    [{code, name}] 候选产成品列表
const props = defineProps({
  modelValue: { type: Array, required: true },
  options:    { type: Array, default: () => [] },
})
const emit = defineEmits(['update:modelValue'])

// ── Store ──────────────────────────────────────────
const packagedStore = usePackagedStore()

// ── 计算属性 ──────────────────────────────────────

// el-select v-model：仅 non-delete 状态的 codes
const selectValue = computed({
  get: () => props.modelValue.filter(t => t.state !== 'delete').map(t => t.value),
  set: (newCodes) => {
    const list = props.modelValue.map(t => ({ ...t }))
    const currentActive = list.filter(t => t.state !== 'delete').map(t => t.value)
    const removed = currentActive.filter(c => !newCodes.includes(c))
    const added   = newCodes.filter(c => !currentActive.includes(c))
    for (const code of removed) {
      const item = list.find(t => t.value === code)
      if (!item) continue
      if (item.state === 'new') list.splice(list.indexOf(item), 1)
      else item.state = 'delete'
    }
    for (const code of added) {
      const existing = list.find(t => t.value === code)
      if (existing && existing.state === 'delete') {
        existing.state = isInLibrary(code) ? 'raw' : 'new'
      } else if (!existing) {
        list.push({ value: code, state: isInLibrary(code) ? 'raw' : 'new' })
      }
    }
    emit('update:modelValue', list)
  },
})

// delete 状态的 items（在 #tag slot 里额外渲染，不在 v-model 里）
const deletedTags = computed(() => props.modelValue.filter(t => t.state === 'delete'))

// ── tag 状态方法 ──────────────────────────────────

// 判断编码是否在候选库里
function isInLibrary(code) {
  return props.options.some(o => o.code === code)
}

// 获取某个 code 的 state
function getTagState(code) {
  return props.modelValue.find(t => t.value === code)?.state ?? 'raw'
}

// 关闭按钮：new → 直接移除；raw → 标记为 delete
function removeTag(code) {
  const list = props.modelValue.map(t => ({ ...t }))
  const item  = list.find(t => t.value === code)
  if (!item) return
  if (item.state === 'new') list.splice(list.indexOf(item), 1)
  else if (item.state === 'raw') item.state = 'delete'
  emit('update:modelValue', list)
}

// 撤销按钮：delete → 根据是否在库里恢复为 raw 或 new
function undoTag(code) {
  const list = props.modelValue.map(t => ({ ...t }))
  const item  = list.find(t => t.value === code)
  if (item) item.state = isInLibrary(code) ? 'raw' : 'new'
  emit('update:modelValue', list)
}

// ── 产成品编辑 dialog ─────────────────────────────
const editingCode       = ref('')
const originalName      = ref('')   // 打开时的原始品名，用于排除自身的重复校验
const editDialogVisible = ref(false)
const editSaving        = ref(false)
const editForm = reactive({
  name: '', length: null, width: null, height: null,
  volume: null, gross_weight: null, net_weight: null,
})

// 品名实时校验：空 / 与其他产成品重复（排除自身原始品名）
const nameError = computed(() => {
  const name = editForm.name.trim()
  if (!name) return '品名不能为空'
  if (name !== originalName.value) {
    const duplicate = Object.values(packagedStore.map).some(p => p.name?.trim() === name)
    if (duplicate) return '品名已存在，请换一个'
  }
  return ''
})

// 品名 autocomplete 候选：store 中所有产成品的品名
function suggestNames(query, cb) {
  const names = [...new Set(
    Object.values(packagedStore.map).map(p => p.name).filter(Boolean)
  )]
  const filtered = query ? names.filter(n => n.includes(query)) : names
  cb(filtered.map(n => ({ value: n })))
}

// 点击 ✎ → 加载完整数据，打开 dialog
async function openEdit(code) {
  await packagedStore.loadAll()
  const data = packagedStore.map[code]

  console.log('openEdit', code, data)

  const name = data?.name ?? ''
  originalName.value = name
  Object.assign(editForm, {
    name,
    length:       data?.length       ?? null,
    width:        data?.width        ?? null,
    height:       data?.height       ?? null,
    volume:       data?.volume       ?? null,
    gross_weight: data?.gross_weight ?? null,
    net_weight:   data?.net_weight   ?? null,
  })
  editingCode.value       = code
  editDialogVisible.value = true
}

function closeEdit() {
  editDialogVisible.value = false
  editingCode.value       = ''
  originalName.value      = ''
}

// 保存：nameError 已校验，直接提交
async function saveEdit() {
  if (nameError.value) return
  editSaving.value = true
  try {
    const res = await http.post('/api/product/packaged', { code: editingCode.value, ...editForm })
    if (res.success) {
      packagedStore.map[editingCode.value] = res.data
      closeEdit()
    }
  } finally {
    editSaving.value = false
  }
}
</script>

<template>
  <el-select
    v-model="selectValue"
    multiple filterable
    placeholder="搜索或选择产成品编码"
    class="g-etl"
  >
    <template #tag="{ data }">
      <!-- non-delete 状态的 tags（来自 v-model） -->
      <span
        v-for="item in data"
        :key="item.value"
        class="etl-tag"
        :class="`etl-tag-${getTagState(item.value)}`"
      >
        <span class="etl-tag-text">{{ item.value }}</span>
        <button
          class="etl-btn etl-btn-edit"
          :class="getTagState(item.value) === 'new' ? 'etl-btn-red' : 'etl-btn-grey'"
          @click.stop="openEdit(item.value)"
        >✎</button>
        <button class="etl-btn etl-btn-close" @click.stop="removeTag(item.value)">×</button>
      </span>

      <!-- delete 状态的 tags（额外渲染，不在 v-model 里） -->
      <span
        v-for="item in deletedTags"
        :key="'del-' + item.value"
        class="etl-tag etl-tag-delete"
      >
        <span class="etl-tag-text">{{ item.value }}</span>
        <button class="etl-btn etl-btn-edit etl-btn-grey" @click.stop="openEdit(item.value)">✎</button>
        <button class="etl-btn etl-btn-undo etl-btn-red" @click.stop="undoTag(item.value)">↩</button>
      </span>
    </template>

    <!-- 下拉选项 -->
    <el-option
      v-for="opt in options"
      :key="opt.code"
      :value="opt.code"
      :label="opt.code"
    >
      <span class="etl-opt-code">{{ opt.code }}</span>
      <span class="etl-opt-name">{{ opt.name }}</span>
    </el-option>
  </el-select>

  <!-- ── 编辑产成品 Dialog ──────────────────────── -->
  <el-dialog
    v-model="editDialogVisible"
    width="460px"
    :close-on-click-modal="false"
    append-to-body
    @closed="closeEdit"
  >
    <!-- 自定义标题 -->
    <template #header>
      <div class="ped-header">
        <span class="ped-title">编辑产成品</span>
        <span class="ped-code-badge">{{ editingCode }}</span>
      </div>
    </template>

    <div class="ped-body">

      <!-- 品名 -->
      <div class="ped-field">
        <label class="ped-lbl">品名 <span class="ped-req">*</span></label>
        <div class="ped-ctrl">
          <el-autocomplete
            v-model="editForm.name"
            :fetch-suggestions="suggestNames"
            placeholder="输入或搜索品名"
            class="ped-auto"
            :class="{ 'is-error': nameError }"
            clearable
            @keyup.enter="saveEdit"
          />
          <transition name="err-fade">
            <div v-if="nameError" class="ped-errmsg">
              <span class="ped-err-icon">!</span>{{ nameError }}
            </div>
          </transition>
        </div>
      </div>

      <!-- 包装尺寸 -->
      <div class="ped-group">
        <div class="ped-group-hd">包装尺寸</div>
        <div class="ped-group-bd">
          <div class="ped-num-col">
            <el-input-number v-model="editForm.length" :controls="false" class="ped-num" placeholder="—" />
            <span class="ped-unit">长 (cm)</span>
          </div>
          <div class="ped-num-col">
            <el-input-number v-model="editForm.width" :controls="false" class="ped-num" placeholder="—" />
            <span class="ped-unit">宽 (cm)</span>
          </div>
          <div class="ped-num-col">
            <el-input-number v-model="editForm.height" :controls="false" class="ped-num" placeholder="—" />
            <span class="ped-unit">高 (cm)</span>
          </div>
        </div>
      </div>

      <!-- 重量体积 -->
      <div class="ped-group">
        <div class="ped-group-hd">重量体积</div>
        <div class="ped-group-bd">
          <div class="ped-num-col">
            <el-input-number v-model="editForm.volume" :controls="false" class="ped-num" placeholder="—" />
            <span class="ped-unit">体积 (m³)</span>
          </div>
          <div class="ped-num-col">
            <el-input-number v-model="editForm.gross_weight" :controls="false" class="ped-num" placeholder="—" />
            <span class="ped-unit">毛重 (kg)</span>
          </div>
          <div class="ped-num-col">
            <el-input-number v-model="editForm.net_weight" :controls="false" class="ped-num" placeholder="—" />
            <span class="ped-unit">净重 (kg)</span>
          </div>
        </div>
      </div>

    </div>

    <template #footer>
      <div class="ped-footer">
        <button class="ped-btn ped-btn-cancel" @click="closeEdit">取消</button>
        <button
          class="ped-btn ped-btn-save"
          :disabled="editSaving || !!nameError"
          @click="saveEdit"
        >{{ editSaving ? '保存中…' : '保存' }}</button>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
/* ── el-select 根容器 ─────────────────────────── */
.g-etl { flex: 1; min-width: 0; }
.g-etl :deep(.el-select__wrapper) {
  height: unset !important; min-height: 32px !important;
  align-items: center; padding: 4px 8px !important;
  border-radius: 4px; box-shadow: none !important;
  border: 1px solid #e8ddd0; background: #fff;
  transition: border-color 0.15s;
}
.g-etl :deep(.el-select__wrapper):hover      { border-color: #c4883a; }
.g-etl :deep(.el-select__wrapper.is-focused) { border-color: #c4883a; box-shadow: none !important; }
.g-etl :deep(.el-select__selection) { flex-wrap: wrap; gap: 4px; align-items: center; }
.g-etl :deep(.el-select__placeholder),
.g-etl :deep(.el-select__input) { font-size: 13px; }

/* ── 自定义 tag ───────────────────────────────── */
.etl-tag {
  display: inline-flex; align-items: center;
  height: 22px; font-size: 11px;
  font-family: 'Microsoft YaHei UI', 'Microsoft YaHei', monospace;
  color: #3a7bc8; background: #edf4ff;
  border: 1px solid #c5d9f5; border-radius: 4px;
  overflow: visible; flex-shrink: 0; position: relative;
}
.etl-tag-delete { opacity: 0.75; }
.etl-tag-delete .etl-tag-text { text-decoration: line-through; color: #888; }
.etl-tag-text { padding: 0 5px 0 6px; white-space: nowrap; }

.etl-btn {
  display: flex; align-items: center; justify-content: center;
  height: 22px; width: 20px;
  border: none; border-left: 1px solid #c5d9f5;
  cursor: pointer; font-size: 11px; flex-shrink: 0;
  transition: background 0.12s, color 0.12s; padding: 0; line-height: 1;
}
.etl-btn-red  { background: #fde8e8; color: #cf1322; }
.etl-btn-red:hover  { background: #ffc5c5; }
.etl-btn-grey { background: #f5f0e8; color: #8a7a6a; }
.etl-btn-grey:hover { background: #e8ddd0; }
.etl-btn-close { background: #deeeff; color: #3a7bc8; }
.etl-btn-close:hover { background: #c5d9f5; color: #1a5ba8; }

/* 下拉选项行 */
.etl-opt-code { font-family: 'Microsoft YaHei UI', 'Microsoft YaHei', monospace; font-size: 12px; color: #2c2420; }
.etl-opt-name { font-size: 11px; color: #999; margin-left: 8px; }

/* ── Dialog 标题 ──────────────────────────────── */
.ped-header { display: flex; align-items: center; gap: 10px; }
.ped-title  { font-size: 15px; font-weight: 600; color: #2c2420; }
.ped-code-badge {
  font-size: 12px; font-weight: 600; color: #6b5e4e;
  background: #f5f0e8; border: 1px solid #e8ddd0;
  border-radius: 4px; padding: 2px 9px;
  font-family: 'Microsoft YaHei UI', 'Microsoft YaHei', monospace;
}

/* ── Dialog 内容区 ────────────────────────────── */
.ped-body {
  display: flex; flex-direction: column; gap: 16px;
  font-family: 'Microsoft YaHei UI', 'Microsoft YaHei', sans-serif;
}

/* 品名行 */
.ped-field { display: flex; align-items: flex-start; gap: 10px; }
.ped-lbl {
  flex-shrink: 0; width: 40px; padding-top: 8px;
  font-size: 13px; color: #6b5e4e; font-weight: 600; text-align: right;
}
.ped-req  { color: #d05a3c; }
.ped-ctrl { flex: 1; display: flex; flex-direction: column; gap: 5px; }

/* el-autocomplete */
.ped-auto { width: 100%; }
.ped-auto :deep(.el-input__wrapper) {
  height: 34px; padding: 0 10px; border-radius: 7px;
  box-shadow: none !important; border: 1px solid #e8ddd0; background: #fff;
  transition: border-color 0.15s;
}
.ped-auto :deep(.el-input__wrapper):hover    { border-color: #c4883a; }
.ped-auto :deep(.el-input__wrapper.is-focus) { border-color: #c4883a !important; }
.ped-auto :deep(.el-input__inner) { font-size: 13px; color: #2c2420; }

/* 错误状态：红色边框 + 浅红背景 */
.ped-auto.is-error :deep(.el-input__wrapper) {
  border-color: #d05a3c !important;
  background: #fff8f7 !important;
}
.ped-auto.is-error :deep(.el-input__wrapper):hover {
  border-color: #d05a3c !important;
}

/* 错误提示 */
.ped-errmsg {
  display: flex; align-items: center; gap: 5px;
  font-size: 12px; color: #d05a3c;
}
.ped-err-icon {
  display: inline-flex; align-items: center; justify-content: center;
  width: 14px; height: 14px; border-radius: 50%;
  background: #d05a3c; color: #fff;
  font-size: 10px; font-weight: 700; flex-shrink: 0; line-height: 1;
}
.err-fade-enter-active, .err-fade-leave-active { transition: opacity 0.15s, transform 0.15s; }
.err-fade-enter-from, .err-fade-leave-to { opacity: 0; transform: translateY(-4px); }

/* ── 数值分组卡片 ─────────────────────────────── */
.ped-group {
  background: #faf7f2; border: 1px solid #eee6d8;
  border-radius: 8px; overflow: hidden;
}
.ped-group-hd {
  padding: 6px 14px;
  font-size: 11px; font-weight: 600; color: #8a7a6a;
  letter-spacing: 0.5px;
  border-bottom: 1px solid #eee6d8;
  background: #f5f0e8;
}
.ped-group-bd {
  display: flex; gap: 1px;
  background: #eee6d8;   /* 用作列分隔线色 */
  padding: 0;
}
.ped-num-col {
  flex: 1; display: flex; flex-direction: column; align-items: center;
  gap: 4px; padding: 10px 8px 8px;
  background: #faf7f2;
}
.ped-num { width: 100%; }
.ped-num :deep(.el-input__wrapper) {
  height: 32px; padding: 0 6px; border-radius: 6px;
  box-shadow: none !important; border: 1px solid #e8ddd0; background: #fff;
  transition: border-color 0.15s;
}
.ped-num :deep(.el-input__wrapper):hover    { border-color: #c4883a; }
.ped-num :deep(.el-input__wrapper.is-focus) { border-color: #c4883a !important; }
.ped-num :deep(.el-input__inner) { font-size: 13px; color: #2c2420; text-align: center; }
.ped-unit { font-size: 11px; color: #a09080; }

/* ── footer ──────────────────────────────────── */
.ped-footer { display: flex; justify-content: flex-end; gap: 8px; }
.ped-btn {
  padding: 6px 20px; border-radius: 7px; font-size: 13px;
  cursor: pointer; border: 1px solid; transition: all 0.15s;
  font-family: 'Microsoft YaHei UI', 'Microsoft YaHei', sans-serif;
}
.ped-btn-save { background: #c4883a; border-color: #c4883a; color: #fff; }
.ped-btn-save:hover:not(:disabled) { background: #b07830; }
.ped-btn-save:disabled { opacity: 0.5; cursor: not-allowed; }
.ped-btn-cancel { background: #fff; border-color: #e0d4c0; color: #6b5e4e; }
.ped-btn-cancel:hover { background: #faf5ee; border-color: #c4883a; color: #c4883a; }
</style>
