<!-- ─────────────────────────────────────────
  组件：WindowControls
  功能：窗口控制按键（最小化、关闭），右上角固定
        所有页面通用
───────────────────────────────────────── -->

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { ElMessageBox } from 'element-plus'

// ── Props ──────────────────────────────────
const props = defineProps({
  // 点击关闭是否需要二次确认（首页需要，管理页面不需要）
  confirmClose: {
    type:    Boolean,
    default: false,
  },
  // 关闭确认文案
  confirmText: {
    type:    String,
    default: '确认退出两平米软件库？',
  },
  // 是否显示最大化按钮（登录窗口不需要）
  showMaximize: {
    type:    Boolean,
    default: true,
  },
})

// ── 响应式状态 ─────────────────────────────
const isMaximized = ref(false)

// ── 生命周期 ──────────────────────────────
function onMaximize()   { isMaximized.value = true  }
function onUnmaximize() { isMaximized.value = false }

onMounted(() => {
  window.electronAPI?.onMaximize(onMaximize)
  window.electronAPI?.onUnmaximize(onUnmaximize)
})

onUnmounted(() => {
  // preload 未暴露 off，事件监听在窗口销毁时自动清理
})

// ── 最小化 ────────────────────────────────
function handleMinimize() {
  window.electronAPI?.minimizeApp()
}

// ── 最大化 / 还原 ──────────────────────────
function handleMaximize() {
  if (isMaximized.value) {
    window.electronAPI?.unmaximizeApp()
  } else {
    window.electronAPI?.maximizeApp()
  }
}

// ── 关闭 ──────────────────────────────────
async function handleClose() {
  if (props.confirmClose) {
    try {
      await ElMessageBox.confirm(props.confirmText, '退出应用', {
        confirmButtonText: '退出',
        cancelButtonText:  '取消',
        type:              'warning',
      })
      window.electronAPI?.quitApp()
    } catch { }
  } else {
    window.electronAPI?.quitApp()
  }
}
</script>

<template>
  <div class="window-controls">
    <!-- 最小化 -->
    <button class="ctrl-btn minimize" title="最小化" @click="handleMinimize">
      <span class="ctrl-icon">─</span>
    </button>
    <!-- 最大化 / 还原 -->
    <button v-if="showMaximize" class="ctrl-btn maximize" :title="isMaximized ? '还原' : '最大化'" @click="handleMaximize">
      <span class="ctrl-icon">{{ isMaximized ? '❐' : '□' }}</span>
    </button>
    <!-- 关闭 -->
    <button class="ctrl-btn close" title="关闭" @click="handleClose">
      <span class="ctrl-icon">✕</span>
    </button>
  </div>
</template>

<style scoped>
/* ── 窗口控制按键组 ────────────────────────── */
.window-controls {
  position: fixed;
  top: 11px;
  right: 14px;
  z-index: 1500;
  display: flex;
  align-items: center;
  gap: 6px;
}

.ctrl-btn {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--bg-card);
  color: var(--text-muted);
  font-size: 11px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
  box-shadow: 0 1px 4px var(--shadow);
  padding: 0;
  line-height: 1;
}

/* 最小化 hover */
.ctrl-btn.minimize:hover {
  background: rgba(196,136,58,0.1);
  border-color: var(--accent);
  color: var(--accent);
}

/* 最大化/还原 hover */
.ctrl-btn.maximize:hover {
  background: rgba(196,136,58,0.1);
  border-color: var(--accent);
  color: var(--accent);
}

/* 关闭 hover */
.ctrl-btn.close:hover {
  background: #fff0ee;
  border-color: #e0a090;
  color: #c05040;
}

.ctrl-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  font-size: 11px;
  line-height: 1;
}
</style>