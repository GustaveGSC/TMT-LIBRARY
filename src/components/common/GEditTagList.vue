<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, computed } from 'vue'
import { Edit, RefreshLeft } from '@element-plus/icons-vue'
import { usePackagedStore } from '@/stores/product/packaged'
import PackagedEditDialog from '@/components/product/PackagedEditDialog.vue'


// ── Props / Emits ─────────────────────────────────
// modelValue: [{value: code, state: 'original'|'added'|'deleted'}]
//   state 语义（两个独立维度）：
//     原始列表维度：original=编辑开始时已在清单中，added=本次新增
//     删除维度：    deleted=原本在清单中，标记删除（可撤销）
//   编辑按键颜色由 isInLibrary(code) 单独决定（与 state 无关）
// options:    [{code, name}] 候选产成品列表
const props = defineProps({
  modelValue: { type: Array, required: true },
  options:    { type: Array, default: () => [] },
})
const emit = defineEmits(['update:modelValue'])

// ── Store ──────────────────────────────────────────
const packagedStore = usePackagedStore()

// ── 计算属性 ──────────────────────────────────────

// el-select v-model：仅活跃（non-deleted）状态的 codes
const selectValue = computed({
  get: () => props.modelValue.filter(t => t.state !== 'deleted').map(t => t.value),
  set: (newCodes) => {
    const list = props.modelValue.map(t => ({ ...t }))
    const currentActive = list.filter(t => t.state !== 'deleted').map(t => t.value)
    const removed = currentActive.filter(c => !newCodes.includes(c))
    const added   = newCodes.filter(c => !currentActive.includes(c))
    for (const code of removed) {
      const item = list.find(t => t.value === code)
      if (!item) continue
      if (item.state === 'added') list.splice(list.indexOf(item), 1)  // 新增的直接移除
      else item.state = 'deleted'                                       // 原始的标记删除
    }
    for (const code of added) {
      const existing = list.find(t => t.value === code)
      if (existing && existing.state === 'deleted') {
        existing.state = 'original'   // 撤销删除，恢复原始
      } else if (!existing) {
        list.push({ value: code, state: 'added' })  // 新增项
      }
    }
    emit('update:modelValue', list)
  },
})

// deleted 状态的 items（在 #tag slot 里额外渲染，带删除线和撤销按键）
const deletedTags = computed(() => props.modelValue.filter(t => t.state === 'deleted'))

// ── tag 状态方法 ──────────────────────────────────

// 判断编码是否在产成品库里（以 packagedStore.map 为准）
function isInLibrary(code) {
  return code in packagedStore.map
}

// 获取某个 code 的 state
function getTagState(code) {
  return props.modelValue.find(t => t.value === code)?.state ?? 'original'
}

// 关闭按钮：added → 直接移除；original → 标记为 deleted
function removeTag(code) {
  const list = props.modelValue.map(t => ({ ...t }))
  const item  = list.find(t => t.value === code)
  if (!item) return
  if (item.state === 'added') list.splice(list.indexOf(item), 1)
  else if (item.state === 'original') item.state = 'deleted'
  emit('update:modelValue', list)
}

// 撤销按钮：deleted → 恢复为 original（始终是 original，因为只有 original 才能变 deleted）
function undoTag(code) {
  const list = props.modelValue.map(t => ({ ...t }))
  const item  = list.find(t => t.value === code)
  if (item) item.state = 'original'
  emit('update:modelValue', list)
}

// ── 产成品编辑 dialog（抽成公共组件，成品详情和"所有产成品数据"表格共用同一份）
const editDialogRef = ref(null)
function openEdit(code) {
  editDialogRef.value?.open(code)
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
      <!-- 活跃状态的 tags（original / added，来自 v-model） -->
      <span
        v-for="item in data"
        :key="item.value"
        class="etl-tag"
        :class="`etl-tag-${getTagState(item.value)}`"
      >
        <span class="etl-tag-text">{{ item.value }}</span>
        <!-- 编辑按键颜色：是否在产成品库里（与 state 无关） -->
        <button
          class="etl-btn etl-btn-edit"
          :class="isInLibrary(item.value) ? 'etl-btn-grey' : 'etl-btn-red'"
          :title="isInLibrary(item.value) ? '编辑产成品' : '该编码不在产成品库中'"
          @click.stop="openEdit(item.value)"
        ><el-icon><Edit /></el-icon></button>
        <!-- 关闭按键：added → 直接移除，original → 标记删除 -->
        <button class="etl-btn etl-btn-close" title="移除" @click.stop="removeTag(item.value)">×</button>
      </span>

      <!-- deleted 状态的 tags（额外渲染，带删除线，可撤销） -->
      <span
        v-for="item in deletedTags"
        :key="'del-' + item.value"
        class="etl-tag etl-tag-deleted"
      >
        <span class="etl-tag-text">{{ item.value }}</span>
        <button
          class="etl-btn etl-btn-edit"
          :class="isInLibrary(item.value) ? 'etl-btn-grey' : 'etl-btn-red'"
          :title="isInLibrary(item.value) ? '编辑产成品' : '该编码不在产成品库中'"
          @click.stop="openEdit(item.value)"
        ><el-icon><Edit /></el-icon></button>
        <button class="etl-btn etl-btn-undo" title="撤销删除" @click.stop="undoTag(item.value)">
          <el-icon><RefreshLeft /></el-icon>
        </button>
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

  <!-- ── 编辑产成品 Dialog（公共组件，见 PackagedEditDialog.vue） ──── -->
  <PackagedEditDialog ref="editDialogRef" />
</template>

<style scoped>
/* ── el-select 根容器 ─────────────────────────── */
.g-etl { flex: 1; min-width: 0; }
.g-etl :deep(.el-select__wrapper) {
  height: unset !important; min-height: 32px !important;
  align-items: center; 
  padding: 4px 8px !important;
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
  height: 26px; font-size: 11px;
  font-family: 'Microsoft YaHei UI', 'Microsoft YaHei', monospace;
  border-radius: 4px; border: 1px solid;
  overflow: visible; flex-shrink: 0; position: relative;
  margin-left: 3px;
}
/* added（本次新增）→ 蓝色背景 */
.etl-tag-added {
  color: #3a7bc8; background: #edf4ff; border-color: #c5d9f5;
}
.etl-tag-added .etl-btn { border-left-color: #c5d9f5; }
/* original（原始清单里，活跃）→ 灰色背景 */
.etl-tag-original {
  color: #6b5e4e; background: #f5f0e8; border-color: #d4c8b8;
}
.etl-tag-original .etl-btn { border-left-color: #d4c8b8; }
/* deleted（原始清单里，标记删除）→ 灰色+删除线 */
.etl-tag-deleted {
  color: #999; background: #f5f0e8; border-color: #d4c8b8;
  opacity: 0.75;
}
.etl-tag-deleted .etl-btn { border-left-color: #d4c8b8; }
.etl-tag-deleted .etl-tag-text { text-decoration: line-through; }
.etl-tag-text { padding: 0 5px 0 6px; white-space: nowrap; }

.etl-btn {
  display: flex; align-items: center; justify-content: center;
  height: 24px; width: 24px;
  border: none; border-left: 1px solid #c5d9f5;
  cursor: pointer; font-size: 14px; flex-shrink: 0;
  transition: background 0.12s, color 0.12s; padding: 0; line-height: 1;
}
.etl-btn-red  { background: #fde8e8; color: #cf1322; }
.etl-btn-red:hover  { background: #ffc5c5; }
.etl-btn-grey { background: #ede7dc; color: #8a7a6a; }
.etl-btn-grey:hover { background: #ddd4c6; }
.etl-btn-close { background: transparent; color: #8a7a6a; }
.etl-btn-close:hover { background: rgba(0,0,0,0.07); }
.etl-tag-added .etl-btn-close { color: #3a7bc8; }
.etl-tag-added .etl-btn-close:hover { background: #c5d9f5; }
.etl-btn-undo { background: transparent; color: #8a7a6a; }
.etl-btn-undo:hover { background: rgba(0,0,0,0.07); color: #3a3028; }

/* 下拉选项行 */
.etl-opt-code { font-family: 'Microsoft YaHei UI', 'Microsoft YaHei', monospace; font-size: 12px; color: #2c2420; }
.etl-opt-name { font-size: 11px; color: #999; margin-left: 8px; }

/* 编辑产成品弹窗样式已迁到 PackagedEditDialog.vue */
</style>
