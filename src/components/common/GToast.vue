<template>
  <teleport to="body">
    <transition name="toast">
      <div v-if="visible" class="toast" :class="type">
        <span class="toast-icon">{{ type === 'success' ? '✓' : '✕' }}</span>
        <span class="toast-msg">{{ message }}</span>
      </div>
    </transition>
  </teleport>
</template>

<script setup>
import { ref } from 'vue'

const visible = ref(false)
const message = ref('')
const type    = ref('success')
let timer     = null

function show(msg, t = 'success', duration = 2500) {
  message.value = msg
  type.value    = t
  visible.value = true
  clearTimeout(timer)
  timer = setTimeout(() => { visible.value = false }, duration)
}

defineExpose({ show })
</script>

<style scoped>
.toast {
  position: fixed;
  top: 24px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 9999;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 20px;
  border-radius: 10px;
  font-size: 13px;
  font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
  border: 1px solid;
  white-space: nowrap;
  pointer-events: none;
  box-shadow: 0 4px 16px rgba(0,0,0,0.08);
}

.toast.success {
  background: #f0faf4;
  border-color: #a8dbb8;
  color: #2d7a4a;
}

.toast.error {
  background: #fff4f2;
  border-color: #f0b0a0;
  color: #c04030;
}

.toast-icon { font-size: 12px; font-weight: 700; }

.toast-enter-active, .toast-leave-active { transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1); }
.toast-enter-from, .toast-leave-to { opacity: 0; transform: translateX(-50%) translateY(-12px); }
</style>