<script setup>
// 按键层：N 个独立按键，用于模拟外部环境状态（联网/过热/提醒/身份），
// 不直接操作屏幕内容——身份需先在此选中，再到手控器上点击 NFC 感应区触发生效
import { useLabHandsetStore } from '@/stores/lab/handset'

const store = useLabHandsetStore()
</script>

<template>
  <div class="control-panel">
    <section class="state-section base-section">
      <header class="section-header">
        <span class="section-title">基础控制</span>
        <span class="section-desc">设备与外设</span>
      </header>
      <div class="section-controls">
        <div class="control-item">
          <span class="control-label">电源</span>
          <el-button size="small" :type="store.isAwake ? 'primary' : 'default'" @click="store.togglePower()">
            {{ store.isAwake ? '息屏' : '唤醒' }}
          </el-button>
        </div>
        <div class="control-item">
          <span class="control-label">氛围灯</span>
          <el-button size="small" :type="store.ambientOn ? 'primary' : 'default'" @click="store.toggleAmbient()">
            {{ store.ambientOn ? '已开启' : '已关闭' }}
          </el-button>
        </div>
      </div>
    </section>

    <section class="state-section persistent-section">
      <header class="section-header">
        <span class="section-title">常驻持久状态</span>
        <span class="section-desc">保持至再次切换</span>
      </header>
      <div class="section-controls">
        <div class="control-item">
          <span class="control-label">WiFi</span>
          <el-button size="small" :type="store.network ? 'primary' : 'default'" @click="store.toggleNetwork()">
            {{ store.network ? '已联网' : '未联网' }}
          </el-button>
        </div>
        <div class="control-item">
          <span class="control-label">通知</span>
          <el-button size="small" :type="store.reminder ? 'warning' : 'default'" @click="store.toggleReminder()">
            {{ store.reminder ? '有通知' : '无通知' }}
          </el-button>
        </div>
        <div class="control-item">
          <span class="control-label">过热保护</span>
          <el-button size="small" :type="store.overheat ? 'danger' : 'default'" @click="store.toggleOverheat()">
            {{ store.overheat ? '保护中' : '正常' }}
          </el-button>
        </div>
      </div>
    </section>

    <section class="state-section trigger-section">
      <header class="section-header">
        <span class="section-title">触发型状态</span>
        <span class="section-desc">主动模拟一次事件</span>
      </header>
      <div class="section-controls trigger-controls">
        <div class="control-item">
          <span class="control-label">遇阻</span>
          <el-button
            size="small"
            type="warning"
            :plain="!store.obstruction"
            :disabled="!store.canTriggerObstruction"
            @click="store.toggleObstruction()"
          >{{ store.obstruction ? '已触发' : '模拟触发' }}</el-button>
        </div>
        <div class="control-item">
          <span class="control-label">故障</span>
          <el-button size="small" type="danger" :plain="!store.fault" @click="store.toggleFault()">
            {{ store.fault ? '已触发' : '模拟触发' }}
          </el-button>
        </div>
      </div>
      <p class="trigger-hint">遇阻仅在设备升降或倾斜时可触发，运动状态将由屏幕操作自动判断。</p>
    </section>

    <section class="state-section identity-section">
      <header class="section-header">
        <span class="section-title">身份模拟</span>
        <span class="section-desc">选中后点击手控器 NFC 生效</span>
      </header>
      <div class="identity-row">
        <div class="identity-btns">
          <el-button
            v-for="u in store.users"
            :key="u.id"
            size="small"
            :type="store.pendingNfcUser === u.id ? 'primary' : 'default'"
            @click="store.setPendingNfcUser(u.id)"
          >{{ u.name }}</el-button>
        </div>
        <div class="current-user">当前登录：{{ store.currentUserName || '未登录' }}</div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.control-panel {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 9px;
  padding: 10px;
  box-sizing: border-box;
  background: #f7f3ec;
  border: 1px solid #e0d4c0;
  border-radius: 16px;
  box-shadow: 0 14px 38px rgba(72, 53, 34, 0.08);
}

.state-section {
  min-width: 0;
  padding: 10px 12px;
  border: 1px solid #e4dbce;
  border-radius: 12px;
  background: rgba(255,255,255,0.8);
  box-shadow: 0 2px 7px rgba(72, 53, 34, 0.045);
}
.persistent-section { border-left: 3px solid #4f91d8; }
.trigger-section { border-left: 3px solid #d8953f; }
.section-header {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 8px;
}
.section-title { font-size: 13px; font-weight: 700; color: #3a3028; }
.section-desc { font-size: 10px; color: #978877; }
.section-controls {
  display: flex;
  align-items: flex-end;
  flex-wrap: wrap;
  gap: 12px;
}
.control-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 5px;
}
.control-label {
  font-size: 10px;
  color: #8a7a6a;
  white-space: nowrap;
}
.trigger-controls { gap: 14px; }
.trigger-hint {
  margin: 7px 0 0;
  line-height: 1.45;
  font-size: 10px;
  color: #a06c2c;
}
.identity-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.identity-btns { display: flex; gap: 6px; }
.current-user {
  font-size: 11px;
  color: #6b5e4e;
}

@media (max-width: 1080px) {
  .control-panel {
    width: min(920px, 100%);
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .trigger-section,
  .identity-section { grid-column: span 2; }
}

@media (max-width: 760px) {
  .control-panel { display: flex; }
  .identity-row { align-items: flex-start; flex-direction: column; }
}
</style>
