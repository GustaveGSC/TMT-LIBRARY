<script setup>
// ── 物料门禁命中提示：弹窗形式 ──────────────────────
// 检测到门禁（PDM转BOM / 变更申请单填写 / 材料清单校验）时用这个弹窗展示，不再用行内
// banner。列表按 禁止(block) 在前、提醒(warn) 在后展示；每项显示名称、物料编码、门禁原因。
// block 存在时调用方需要自行禁用"下一步"操作，本组件只负责展示。
import { computed } from 'vue'
import { CircleCloseFilled, WarningFilled } from '@element-plus/icons-vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  hits: { type: Object, default: () => ({ warn: [], block: [] }) },
  ok:   { type: Boolean, default: true },
})
const emit = defineEmits(['update:modelValue'])

function displayName(item) {
  return item.name || '（未登记名称）'
}

const total = computed(() => (props.hits?.block?.length || 0) + (props.hits?.warn?.length || 0))
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    @update:model-value="v => emit('update:modelValue', v)"
    title="物料门禁提示"
    width="min(560px, 92vw)"
    draggable
    class="gate-hit-dialog"
  >
    <div v-if="!ok" class="gate-hit-unknown">
      <el-icon><WarningFilled /></el-icon>
      <span>物料门禁校验未完成（接口异常），本次结果可能不含门禁提示，建议稍后重试</span>
    </div>

    <template v-else>
      <div v-if="!total" class="gate-hit-empty">未命中任何门禁物料</div>

      <template v-else>
        <div v-if="hits.block.length" class="gate-hit-section gate-hit-section--block">
          <div class="gate-hit-section-title">
            <el-icon><CircleCloseFilled /></el-icon>
            禁止（{{ hits.block.length }}）—— 存在此类物料时无法继续下一步
          </div>
          <div v-for="item in hits.block" :key="'block-' + item.code" class="gate-hit-row">
            <div class="gate-hit-name">{{ displayName(item) }}</div>
            <div class="gate-hit-code">{{ item.code }}</div>
            <div class="gate-hit-reason">{{ item.reason }}</div>
          </div>
        </div>

        <div v-if="hits.warn.length" class="gate-hit-section gate-hit-section--warn">
          <div class="gate-hit-section-title">
            <el-icon><WarningFilled /></el-icon>
            提醒（{{ hits.warn.length }}）
          </div>
          <div v-for="item in hits.warn" :key="'warn-' + item.code" class="gate-hit-row">
            <div class="gate-hit-name">{{ displayName(item) }}</div>
            <div class="gate-hit-code">{{ item.code }}</div>
            <div class="gate-hit-reason">{{ item.reason }}</div>
          </div>
        </div>
      </template>
    </template>

    <template #footer>
      <el-button size="small" @click="emit('update:modelValue', false)">关闭</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.gate-hit-unknown {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--text-muted);
  background: rgba(0,0,0,0.04);
  border: 1px dashed var(--border);
  border-radius: 8px;
  padding: 10px 12px;
}
.gate-hit-empty {
  text-align: center;
  color: #267840;
  background: rgba(38,120,64,0.06);
  border: 1px solid rgba(38,120,64,0.25);
  border-radius: 8px;
  padding: 14px;
  font-size: 13px;
}

.gate-hit-section { margin-bottom: 14px; }
.gate-hit-section:last-child { margin-bottom: 0; }
.gate-hit-section-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 8px;
}
.gate-hit-section--block .gate-hit-section-title { color: #a3311e; }
.gate-hit-section--warn  .gate-hit-section-title { color: #8a5a1e; }

.gate-hit-row {
  padding: 8px 10px;
  border-radius: 6px;
  margin-bottom: 6px;
  font-size: 13px;
}
/* 文字颜色固定写死，不跟随主题变量——命中提示是警示类内容，必须在任何主题下都保持
   醒目、高对比度、易读，不能因为主题切换导致文字和背景色系一起变浅、看不清。 */
.gate-hit-section--block .gate-hit-row { background: #fdecea; border: 1px solid #f0b6ac; }
.gate-hit-section--warn  .gate-hit-row { background: #fdf3e3; border: 1px solid #edc98a; }
.gate-hit-row:last-child { margin-bottom: 0; }
.gate-hit-name { font-weight: 700; font-size: 14px; }
.gate-hit-code { font-family: monospace; font-weight: 600; margin-top: 3px; }
.gate-hit-reason { margin-top: 3px; line-height: 1.5; }

.gate-hit-section--block .gate-hit-name   { color: #7a1f12; }
.gate-hit-section--block .gate-hit-code   { color: #96392a; }
.gate-hit-section--block .gate-hit-reason { color: #7a3226; }

.gate-hit-section--warn .gate-hit-name   { color: #5c3a0a; }
.gate-hit-section--warn .gate-hit-code   { color: #7a5a1e; }
.gate-hit-section--warn .gate-hit-reason { color: #6b4f20; }
</style>
