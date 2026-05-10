<script setup>
import { isElectron } from '@/utils/platform'
</script>

<template>
  <!-- Electron 专用：超细拖拽条（8px），所有页面顶部空白区均可拖动窗口 -->
  <!-- WindowControls 从 top:11px 开始，8px 以内无任何交互元素，安全 -->
  <div v-if="isElectron" class="app-drag-region" />
  <RouterView />
</template>

<style>
html, body, #app {
  background: transparent !important;
  margin: 0;
  padding: 0;
  height: 100%;
  overflow: hidden;
}

.app-drag-region {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: 8px;
  -webkit-app-region: drag;
  z-index: 1400;
}
</style>
