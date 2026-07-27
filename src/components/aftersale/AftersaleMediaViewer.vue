<script setup>
// ── 导入 ──────────────────────────────────────────
// 统一图片/视频查看器：全屏遮罩，图片支持滚轮缩放+拖拽平移+双击缩放（参考微信查看图片的交互），
// 视频不自动播放，需用户手动点击播放。左右切换不区分类型。
import { ref, computed, watch, nextTick } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { ArrowLeft, ArrowRight, Close, Delete, ZoomIn, ZoomOut, RefreshRight } from '@element-plus/icons-vue'
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
watch(() => props.modelValue, (val) => { if (val) { index.value = props.initialIndex; resetZoom() } })

const current = computed(() => props.items[index.value] || null)
const deleting = ref(false)

// ── 缩放/平移状态（仅图片；参考微信：滚轮/按钮缩放，拖拽平移，双击切换 1x/2x） ──
const scale = ref(1)
const translateX = ref(0)
const translateY = ref(0)
const MIN_SCALE = 1
const MAX_SCALE = 5
let dragging = false
let dragStartX = 0, dragStartY = 0, startTranslateX = 0, startTranslateY = 0

function resetZoom() { scale.value = 1; translateX.value = 0; translateY.value = 0 }
watch(index, resetZoom)

function zoomBy(delta, clientX, clientY, containerEl) {
  const newScale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale.value + delta))
  if (newScale === scale.value) return
  // 以鼠标/触点为中心缩放，而不是图片中心，体验更接近微信/系统看图
  if (containerEl) {
    const rect = containerEl.getBoundingClientRect()
    const cx = clientX - rect.left - rect.width / 2
    const cy = clientY - rect.top - rect.height / 2
    const ratio = newScale / scale.value
    translateX.value = (translateX.value - cx) * ratio + cx
    translateY.value = (translateY.value - cy) * ratio + cy
  }
  scale.value = newScale
  if (scale.value === MIN_SCALE) { translateX.value = 0; translateY.value = 0 }
}

function onWheel(e) {
  if (current.value?.file_type !== 'image') return
  e.preventDefault()
  zoomBy(e.deltaY < 0 ? 0.3 : -0.3, e.clientX, e.clientY, e.currentTarget)
}

function onDblClick(e) {
  if (current.value?.file_type !== 'image') return
  if (scale.value > MIN_SCALE) resetZoom()
  else zoomBy(1.5, e.clientX, e.clientY, e.currentTarget)
}

function onMouseDown(e) {
  if (current.value?.file_type !== 'image' || scale.value <= MIN_SCALE) return
  dragging = true
  dragStartX = e.clientX; dragStartY = e.clientY
  startTranslateX = translateX.value; startTranslateY = translateY.value
}
function onMouseMove(e) {
  if (!dragging) return
  translateX.value = startTranslateX + (e.clientX - dragStartX)
  translateY.value = startTranslateY + (e.clientY - dragStartY)
}
function onMouseUp() { dragging = false }

function prev() { if (index.value > 0) index.value-- }
function next() { if (index.value < props.items.length - 1) index.value++ }

function onKeydown(e) {
  if (e.key === 'ArrowLeft') prev()
  else if (e.key === 'ArrowRight') next()
  else if (e.key === 'Escape') visible.value = false
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

// 打开时聚焦，保证键盘左右/Esc 立即可用
const rootEl = ref(null)
watch(() => props.modelValue, async (val) => { if (val) { await nextTick(); rootEl.value?.focus() } })
</script>

<template>
  <teleport to="body">
    <div
      v-if="visible" ref="rootEl" class="viewer-overlay" tabindex="0"
      @keydown="onKeydown" @mousemove="onMouseMove" @mouseup="onMouseUp"
    >
      <button class="viewer-close" @click="visible = false"><el-icon><Close /></el-icon></button>
      <button v-if="canDelete" class="viewer-delete" :disabled="deleting" @click="deleteCurrent"><el-icon><Delete /></el-icon></button>

      <button class="viewer-nav viewer-nav-prev" :disabled="index === 0" @click="prev"><el-icon><ArrowLeft /></el-icon></button>
      <button class="viewer-nav viewer-nav-next" :disabled="index === items.length - 1" @click="next"><el-icon><ArrowRight /></el-icon></button>

      <div
        class="viewer-content"
        @wheel="onWheel" @dblclick="onDblClick" @mousedown="onMouseDown"
      >
        <img
          v-if="current?.file_type === 'image'"
          :src="current.oss_url"
          class="viewer-media viewer-image"
          :style="{ transform: `translate(${translateX}px, ${translateY}px) scale(${scale})`, cursor: scale > 1 ? 'grab' : 'zoom-in' }"
          draggable="false"
        />
        <!-- 视频不自动播放，需用户手动点击播放 -->
        <video v-else-if="current?.file_type === 'video'" :src="current.oss_url" controls class="viewer-media" />
      </div>

      <div v-if="current?.file_type === 'image'" class="viewer-zoom-bar">
        <button @click="zoomBy(-0.5, 0, 0, null)"><el-icon><ZoomOut /></el-icon></button>
        <span>{{ Math.round(scale * 100) }}%</span>
        <button @click="zoomBy(0.5, 0, 0, null)"><el-icon><ZoomIn /></el-icon></button>
        <button @click="resetZoom"><el-icon><RefreshRight /></el-icon></button>
      </div>

      <div class="viewer-footer">
        <span>{{ current?.original_filename }}</span>
        <span class="viewer-counter">{{ index + 1 }} / {{ items.length }}</span>
      </div>
    </div>
  </teleport>
</template>

<style scoped>
.viewer-overlay {
  position: fixed; inset: 0; z-index: 3000; background: rgba(0,0,0,0.88);
  display: flex; flex-direction: column; outline: none;
}
.viewer-content {
  flex: 1; display: flex; align-items: center; justify-content: center;
  overflow: hidden; position: relative; user-select: none;
}
.viewer-media { max-width: 92vw; max-height: 82vh; object-fit: contain; }
.viewer-image { transition: transform 0.05s linear; }
.viewer-footer {
  display: flex; justify-content: space-between; align-items: center;
  padding: 10px 20px; color: #ddd; font-size: 13px; background: rgba(0,0,0,0.4); flex-shrink: 0;
}
.viewer-counter { color: #999; }
.viewer-close, .viewer-delete, .viewer-nav {
  position: absolute; z-index: 2; background: rgba(255,255,255,0.12); color: #fff; border: none;
  border-radius: 50%; width: 40px; height: 40px; display: flex; align-items: center; justify-content: center;
  cursor: pointer; font-size: 16px;
}
.viewer-close:hover, .viewer-delete:hover, .viewer-nav:hover { background: rgba(255,255,255,0.25); }
.viewer-close { top: 16px; right: 16px; }
.viewer-delete { top: 16px; right: 66px; }
.viewer-delete:disabled { opacity: 0.5; cursor: not-allowed; }
.viewer-nav { top: 50%; transform: translateY(-50%); width: 48px; height: 48px; }
.viewer-nav-prev { left: 16px; }
.viewer-nav-next { right: 16px; }
.viewer-nav:disabled { opacity: 0.2; cursor: not-allowed; }
.viewer-zoom-bar {
  position: absolute; bottom: 70px; left: 50%; transform: translateX(-50%);
  display: flex; align-items: center; gap: 10px; background: rgba(0,0,0,0.5);
  border-radius: 20px; padding: 6px 14px; color: #fff; font-size: 12px;
}
.viewer-zoom-bar button {
  background: transparent; border: none; color: #fff; cursor: pointer;
  display: flex; align-items: center; font-size: 15px;
}
</style>
