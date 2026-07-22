<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, reactive, computed } from 'vue'
import http from '@/api/http'
import { usePackagedStore } from '@/stores/product/packaged'

/**
 * PackagedEditDialog — 编辑单个产成品（品名/包装尺寸/重量）的弹窗
 *
 * 独立成公共组件，因为同一份编辑内容需要在两处保持一致：
 *   - GEditTagList.vue（成品详情里"产成品清单"tag 上的编辑按键）
 *   - "所有产成品数据"表格（ProductTable.vue）
 * 两处都用这一个组件，改一处两边同步生效，不会出现两套表单字段不一致的情况。
 */

const emit = defineEmits(['saved'])

// ── Store ──────────────────────────────────────────
const packagedStore = usePackagedStore()

// ── 状态 ──────────────────────────────────────────
const editingCode  = ref('')
const originalName = ref('')   // 打开时的原始品名，用于排除自身的重复校验
const visible       = ref(false)
const saving        = ref(false)
const form = reactive({
  name: '', length: null, width: null, height: null,
  gross_weight: null, net_weight: null,
})

// 体积由长宽高自动计算（cm → m³），保留3位小数
const computedVolume = computed(() => {
  const { length, width, height } = form
  if (length == null || width == null || height == null) return null
  return parseFloat((length * width * height / 1_000_000).toFixed(3))
})

// 品名实时校验：空 / 与其他产成品重复（排除自身原始品名）
const nameError = computed(() => {
  const name = form.name.trim()
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

// 打开 → 加载完整数据
async function open(code) {
  await packagedStore.loadAll()
  const data = packagedStore.map[code]

  const name = data?.name ?? ''
  originalName.value = name
  Object.assign(form, {
    name,
    length:       data?.length       ?? null,
    width:        data?.width        ?? null,
    height:       data?.height       ?? null,
    gross_weight: data?.gross_weight ?? null,
    net_weight:   data?.net_weight   ?? null,
  })
  editingCode.value = code
  visible.value     = true
}

function close() {
  visible.value      = false
  editingCode.value  = ''
  originalName.value = ''
}

async function save() {
  if (nameError.value) return
  saving.value = true
  try {
    const res = await http.post('/api/product/packaged', { code: editingCode.value, ...form, volume: computedVolume.value })
    if (res.success) {
      packagedStore.map[editingCode.value] = res.data
      emit('saved', res.data)
      close()
    }
  } finally {
    saving.value = false
  }
}

defineExpose({ open })
</script>

<template>
  <el-dialog
    v-model="visible"
    width="460px"
    :close-on-click-modal="false"
    append-to-body
    @closed="close"
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
            v-model="form.name"
            :fetch-suggestions="suggestNames"
            placeholder="输入或搜索品名"
            class="ped-auto"
            :class="{ 'is-error': nameError }"
            clearable
            @keyup.enter="save"
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
            <el-input-number v-model="form.length" :controls="false" :precision="1" class="ped-num" placeholder="—" />
            <span class="ped-unit">长 (cm)</span>
          </div>
          <div class="ped-num-col">
            <el-input-number v-model="form.width" :controls="false" :precision="1" class="ped-num" placeholder="—" />
            <span class="ped-unit">宽 (cm)</span>
          </div>
          <div class="ped-num-col">
            <el-input-number v-model="form.height" :controls="false" :precision="1" class="ped-num" placeholder="—" />
            <span class="ped-unit">高 (cm)</span>
          </div>
        </div>
      </div>

      <!-- 重量体积 -->
      <div class="ped-group">
        <div class="ped-group-hd">重量体积</div>
        <div class="ped-group-bd">
          <div class="ped-num-col">
            <span class="ped-num-readonly">{{ computedVolume != null ? computedVolume : '—' }}</span>
            <span class="ped-unit">体积 (m³)</span>
          </div>
          <div class="ped-num-col">
            <el-input-number v-model="form.gross_weight" :controls="false" :precision="1" class="ped-num" placeholder="—" />
            <span class="ped-unit">毛重 (kg)</span>
          </div>
          <div class="ped-num-col">
            <el-input-number v-model="form.net_weight" :controls="false" :precision="1" class="ped-num" placeholder="—" />
            <span class="ped-unit">净重 (kg)</span>
          </div>
        </div>
      </div>

    </div>

    <template #footer>
      <div class="ped-footer">
        <button class="ped-btn ped-btn-cancel" @click="close">取消</button>
        <button
          class="ped-btn ped-btn-save"
          :disabled="saving || !!nameError"
          @click="save"
        >{{ saving ? '保存中…' : '保存' }}</button>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
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
.ped-num-readonly {
  width: 100%; height: 32px;
  display: flex; align-items: center; justify-content: center;
  font-size: 13px; color: #6b5e4e;
  background: #f5f0e8; border: 1px solid #e8ddd0; border-radius: 6px;
}

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
