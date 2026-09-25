<script setup>
// ── 物料门禁命中提示条 ──────────────────────────────
// 提醒(warn)：黄色，可关闭，不阻断；禁止(block)：红色，不可关闭，命中期间调用方需要
// 自行禁用"下一步"操作（导出/确认按钮），本组件只负责展示，不负责阻断逻辑。
import { ref, watch } from 'vue'
import { WarningFilled, CircleCloseFilled } from '@element-plus/icons-vue'

const props = defineProps({
  hits: { type: Object, default: () => ({ warn: [], block: [] }) },
  ok:   { type: Boolean, default: true },   // false = 门禁校验接口本身失败，未能确认是否命中
})

const warnDismissed = ref(false)
// 每次拿到新的提醒命中都重新展开一次，避免上一轮关闭状态残留到下一次校验
watch(() => props.hits?.warn, () => { warnDismissed.value = false })
</script>

<template>
  <div v-if="!ok" class="gate-banner gate-banner--unknown">
    <el-icon><WarningFilled /></el-icon>
    <span>物料门禁校验未完成（接口异常），本次结果可能不含门禁提示，建议稍后重试</span>
  </div>

  <div v-if="hits?.block?.length" class="gate-banner gate-banner--block">
    <div class="gate-banner-head">
      <el-icon><CircleCloseFilled /></el-icon>
      <span>检测到 {{ hits.block.length }} 项被门禁"禁止"的物料，无法继续</span>
    </div>
    <div class="gate-hit-list">
      <div v-for="item in hits.block" :key="item.code" class="gate-hit-item">
        <span class="gate-hit-code">{{ item.code }}</span>
        <span class="gate-hit-reason">{{ item.reason }}</span>
      </div>
    </div>
  </div>

  <div v-if="hits?.warn?.length && !warnDismissed" class="gate-banner gate-banner--warn">
    <div class="gate-banner-head">
      <el-icon><WarningFilled /></el-icon>
      <span>检测到 {{ hits.warn.length }} 项被门禁"提醒"的物料，请核对</span>
      <span class="gate-banner-dismiss" @click="warnDismissed = true">关闭</span>
    </div>
    <div class="gate-hit-list">
      <div v-for="item in hits.warn" :key="item.code" class="gate-hit-item">
        <span class="gate-hit-code">{{ item.code }}</span>
        <span class="gate-hit-reason">{{ item.reason }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.gate-banner {
  border-radius: 8px;
  padding: 8px 12px;
  margin: 8px 0;
  font-size: 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.gate-banner-head {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
}
.gate-banner--block {
  background: rgba(192,64,42,0.08);
  border: 1px solid rgba(192,64,42,0.35);
  color: #a3311e;
}
.gate-banner--warn {
  background: rgba(196,136,58,0.10);
  border: 1px solid rgba(196,136,58,0.4);
  color: #8a5a1e;
}
.gate-banner--unknown {
  background: rgba(0,0,0,0.04);
  border: 1px dashed var(--border);
  color: var(--text-muted);
  flex-direction: row;
  align-items: center;
}
.gate-banner-dismiss {
  margin-left: auto;
  cursor: pointer;
  font-weight: 400;
  text-decoration: underline;
  flex-shrink: 0;
}
.gate-hit-list {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding-left: 22px;
}
.gate-hit-item {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.gate-hit-code {
  font-family: monospace;
  font-weight: 600;
}
.gate-hit-reason {
  color: inherit;
  opacity: 0.9;
}
</style>
