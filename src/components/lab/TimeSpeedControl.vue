<script setup>
// 时间流速层：控制模拟时钟倍速，供后续雷达/提醒等计时类逻辑消费
import { computed, onBeforeUnmount, onMounted } from 'vue'
import { RefreshLeft } from '@element-plus/icons-vue'
import { useLabHandsetStore } from '@/stores/lab/handset'

const store = useLabHandsetStore()
const SPEEDS = [1, 2, 3, 5, 20, 60]
let clockTimer = null

const clockDate = computed(() => {
  const date = new Date(store.simulatedTimestamp)
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit', weekday: 'short',
  }).format(date)
})

const clockTime = computed(() => {
  const date = new Date(store.simulatedTimestamp)
  return new Intl.DateTimeFormat('zh-CN', {
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  }).format(date)
})

onMounted(() => {
  store.tickClock()
  clockTimer = setInterval(() => store.tickClock(), 200)
})

onBeforeUnmount(() => clearInterval(clockTimer))
</script>

<template>
  <div class="time-module">
    <div class="clock-display" aria-live="off">
      <span class="clock-label">手控器时间</span>
      <strong>{{ clockTime }}</strong>
      <span class="clock-date">{{ clockDate }}</span>
    </div>

    <div class="speed-control">
      <span class="label">时间流速</span>
      <el-button-group>
        <el-button
          v-for="s in SPEEDS"
          :key="s"
          size="small"
          :type="store.timeSpeed === s ? 'primary' : 'default'"
          @click="store.setTimeSpeed(s)"
        >×{{ s }}</el-button>
      </el-button-group>
    </div>

    <el-button class="reset-button" size="small" plain title="初始化" aria-label="初始化" @click="store.resetAll()">
      <el-icon class="reset-icon"><RefreshLeft /></el-icon><span class="reset-label">初始化</span>
    </el-button>
  </div>
</template>

<style scoped>
.time-module {
  width: min(640px, 100%);
  box-sizing: border-box;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 9px 11px 9px 14px;
  border: 1px solid #dfd5c7;
  border-radius: 13px;
  background: rgba(250, 247, 242, 0.92);
  box-shadow: 0 5px 16px rgba(72, 53, 34, 0.06);
}

.clock-display {
  min-width: 134px;
  display: grid;
  grid-template-columns: auto 1fr;
  grid-template-rows: 1fr 1fr;
  align-items: center;
  column-gap: 8px;
}
.clock-label {
  grid-column: 1;
  grid-row: 1;
  align-self: end;
  padding-bottom: 1px;
  font-size: 9px;
  line-height: 11px;
  color: #9a8977;
}
.clock-display strong {
  grid-column: 2;
  grid-row: 1 / 3;
  align-self: center;
  font-size: 20px;
  line-height: 22px;
  letter-spacing: 0.5px;
  color: #332b24;
  font-variant-numeric: tabular-nums;
}
.clock-date {
  grid-column: 1;
  grid-row: 2;
  align-self: start;
  padding-top: 1px;
  font-size: 9px;
  line-height: 11px;
  color: #786b5d;
  white-space: nowrap;
}

.speed-control {
  display: flex;
  align-items: center;
  gap: 9px;
}

.label {
  font-size: 10px;
  color: #8a7a6a;
  white-space: nowrap;
}

.reset-button { margin-left: auto; }
.reset-icon { margin-right: 3px; }

@media (max-width: 720px) {
  .time-module { flex-wrap: wrap; justify-content: center; }
  .reset-button { margin-left: 0; }
}
</style>
