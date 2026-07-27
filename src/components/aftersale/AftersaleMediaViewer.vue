<script setup>
// ── 导入 ──────────────────────────────────────────
// 统一图片/视频查看器：同一个框里左右切换，不区分类型（图片用 img，视频用 video）
import { ref, computed, watch } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { ArrowLeft, ArrowRight, Close, Delete } from '@element-plus/icons-vue'
import http from '@/api/http.js'

// ── Props / Emits ──────────────────────────────────
const props = defineProps({
  modelValue: { type: Boolean, default: false },
  items: { type: Array, default: () => [] },   // [{id, file_type, oss_url, original_filename}]
  initialIndex: { type: Number, default: 0 },
  canDelete: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue', 'deleted'])

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
})

const index = ref(props.initialIndex)
watch(() => props.modelValue, (val) => { if (val) index.value = props.initialIndex })

const current = computed(() => props.items[index.value] || null)
const deleting = ref(false)

function prev() { if (index.value > 0) index.value-- }
function next() { if (index.value < props.items.length - 1) index.value++ }

function onKeydown(e) {
  if (e.key === 'ArrowLeft') prev()
  else if (e.key === 'ArrowRight') next()
}

async function deleteCurrent() {
  if (!current.value) return
  try {
    await ElMessageBox.confirm(`确认删除「${current.value.original_filename}」？此操作不可撤销。`, '删除媒体', { type: 'warning' })
  } catch { return }
  deleting.value = true
  try {
    const res = await http.delete(`/api/aftersale/media/${current.value.id}`)
    if (res.success) {
      ElMessage.success('已删除')
      emit('deleted', current.value.id)
      if (index.value >= props.items.length - 1) index.value = Math.max(0, props.items.length - 2)
    } else {
      ElMessage.error(res.message || '删除失败')
    }
  } finally {
    deleting.value = false
  }
}
</script>

<template>
  <el-dialog
    v-model="visible"
    width="820px"
    append-to-body
    destroy-on-close
    class="media-viewer-dialog"
    :show-close="false"
    @keydown="onKeydown"
  >
    <div class="viewer-body" tabindex="0" @keydown="onKeydown">
      <button class="viewer-close" @click="visible = false"><el-icon><Close /></el-icon></button>
      <button v-if="canDelete" class="viewer-delete" :disabled="deleting" @click="deleteCurrent"><el-icon><Delete /></el-icon></button>

      <button class="viewer-nav viewer-nav-prev" :disabled="index === 0" @click="prev"><el-icon><ArrowLeft /></el-icon></button>
      <button class="viewer-nav viewer-nav-next" :disabled="index === items.length - 1" @click="next"><el-icon><ArrowRight /></el-icon></button>

      <div class="viewer-content">
        <img v-if="current?.file_type === 'image'" :src="current.oss_url" class="viewer-media" />
        <video v-else-if="current?.file_type === 'video'" :src="current.oss_url" controls autoplay class="viewer-media" />
      </div>

      <div class="viewer-footer">
        <span>{{ current?.original_filename }}</span>
        <span class="viewer-counter">{{ index + 1 }} / {{ items.length }}</span>
      </div>
    </div>
  </el-dialog>
</template>

<style scoped>
.media-viewer-dialog :deep(.el-dialog__header) { display: none; }
.media-viewer-dialog :deep(.el-dialog__body) { padding: 0; }
.viewer-body { position: relative; background: #1a1a1a; border-radius: 8px; overflow: hidden; }
.viewer-content { display: flex; align-items: center; justify-content: center; min-height: 420px; max-height: 70vh; }
.viewer-media { max-width: 100%; max-height: 70vh; object-fit: contain; }
.viewer-footer { display: flex; justify-content: space-between; align-items: center; padding: 8px 16px; color: #ddd; font-size: 13px; background: #222; }
.viewer-counter { color: #999; }
.viewer-close, .viewer-delete, .viewer-nav {
  position: absolute; z-index: 2; background: rgba(0,0,0,0.45); color: #fff; border: none;
  border-radius: 50%; width: 36px; height: 36px; display: flex; align-items: center; justify-content: center;
  cursor: pointer;
}
.viewer-close { top: 10px; right: 10px; }
.viewer-delete { top: 10px; right: 54px; }
.viewer-delete:disabled { opacity: 0.5; cursor: not-allowed; }
.viewer-nav { top: 50%; transform: translateY(-50%); }
.viewer-nav-prev { left: 10px; }
.viewer-nav-next { right: 10px; }
.viewer-nav:disabled { opacity: 0.25; cursor: not-allowed; }
</style>
