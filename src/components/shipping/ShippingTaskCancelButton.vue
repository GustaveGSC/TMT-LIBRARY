<script setup>
// ── 导入 ──────────────────────────────────────────
defineProps({
  cancellable:      { type: Boolean, default: false },
  cancelRequested:  { type: Boolean, default: false },
  cancelSubmitting: { type: Boolean, default: false },
  committing:       { type: Boolean, default: false },
})
const emit = defineEmits(['cancel'])
</script>

<template>
  <button
    v-if="cancellable || cancelRequested || committing"
    class="task-cancel-btn"
    data-testid="task-cancel-btn"
    :disabled="cancelRequested || committing || cancelSubmitting"
    @click="emit('cancel')"
  >
    <template v-if="committing">正在提交，无法取消</template>
    <template v-else-if="cancelRequested">正在取消…</template>
    <template v-else>{{ cancelSubmitting ? '取消中…' : '取消导入' }}</template>
  </button>
</template>

<style scoped>
.task-cancel-btn {
  padding: 7px 16px;
  border: 1px solid rgba(192,96,48,0.3);
  border-radius: 8px;
  background: transparent;
  color: #c06030;
  font-size: 13px; font-family: inherit;
  cursor: pointer; transition: all 0.18s;
  white-space: nowrap;
}
.task-cancel-btn:hover:not(:disabled) { background: rgba(192,96,48,0.08); border-color: rgba(192,96,48,0.6); }
.task-cancel-btn:disabled { opacity: 0.6; cursor: not-allowed; }
</style>
