<script setup>
// 模拟手控系统：左侧设备演示，右侧状态控制台
// 屏幕导航用状态机（见 stores/lab/handset.js），本页只负责布局装配
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { HomeFilled, Minus, Plus, Refresh, Share } from '@element-plus/icons-vue'
import WindowControls from '@/components/common/WindowControls.vue'
import AppBottomBar from '@/components/common/AppBottomBar.vue'
import AmbientLightStrip from '@/components/lab/AmbientLightStrip.vue'
import HandsetDevice from '@/components/lab/HandsetDevice.vue'
import HandsetControlPanel from '@/components/lab/HandsetControlPanel.vue'
import TimeSpeedControl from '@/components/lab/TimeSpeedControl.vue'

const route = useRoute()
const router = useRouter()
const isShared = computed(() => route.query.shared === '1')
const handsetZoom = ref(1)
const shareFeedback = ref('分享')
let originalViewport = ''

function adjustZoom(delta) {
  handsetZoom.value = Math.min(1.32, Math.max(0.7, Number((handsetZoom.value + delta).toFixed(2))))
}

function refreshPage() { window.location.reload() }

async function sharePage() {
  const url = `${window.location.origin}${window.location.pathname}#/lab?shared=1`
  const payload = { title: '模拟手控系统', text: '邀请你体验手控器操作并参与评审。', url }
  try {
    if (navigator.share) await navigator.share(payload)
    else {
      await navigator.clipboard.writeText(url)
      shareFeedback.value = '已复制'
      window.setTimeout(() => { shareFeedback.value = '分享' }, 1800)
    }
  } catch (error) {
    if (error?.name !== 'AbortError') {
      shareFeedback.value = '复制失败'
      window.setTimeout(() => { shareFeedback.value = '分享' }, 1800)
    }
  }
}

function stopPagePinch(event) {
  if (event.touches?.length > 1) event.preventDefault()
}

onMounted(() => {
  // 手机评审以真实尺寸为主，初始即使用允许的最大展示比例。
  if (window.matchMedia('(max-width: 760px), (orientation: landscape) and (max-height: 600px)').matches) handsetZoom.value = 1.32
  const viewport = document.querySelector('meta[name="viewport"]')
  originalViewport = viewport?.getAttribute('content') || ''
  viewport?.setAttribute('content', 'width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no')
  document.addEventListener('touchmove', stopPagePinch, { passive: false })
})

onBeforeUnmount(() => {
  const viewport = document.querySelector('meta[name="viewport"]')
  viewport?.setAttribute('content', originalViewport || 'width=device-width, initial-scale=1.0')
  document.removeEventListener('touchmove', stopPagePinch)
})
</script>

<template>
  <div class="page-wrapper">
    <WindowControls v-if="!isShared" :confirm-close="true" confirm-text="确认退出两平米软件库？" />
    <div class="top-bar">
      <el-button v-if="!isShared" link title="返回主页" @click="router.push('/index')" style="color:var(--text-secondary);padding:0 4px">
        <el-icon><HomeFilled /></el-icon>
      </el-button>
      <span class="page-title">模拟手控系统</span>

      <div class="stage-tools" aria-label="手控器显示控制">
        <el-button circle text title="缩小手控器" aria-label="缩小手控器" :disabled="handsetZoom <= 0.7" @click="adjustZoom(-0.08)"><el-icon><Minus /></el-icon></el-button>
        <el-button circle text title="放大手控器" aria-label="放大手控器" :disabled="handsetZoom >= 1.32" @click="adjustZoom(0.08)"><el-icon><Plus /></el-icon></el-button>
        <el-button circle text title="刷新获取最新内容" aria-label="刷新获取最新内容" @click="refreshPage"><el-icon><Refresh /></el-icon></el-button>
      </div>

      <el-button v-if="!isShared" class="share-button" round @click="sharePage">
        <el-icon><Share /></el-icon><span>{{ shareFeedback }}</span>
      </el-button>

      <details class="mobile-control-menu">
        <summary aria-label="打开状态模拟菜单">
          <span class="menu-glyph" aria-hidden="true"><i /><i /><i /></span>
          <span>状态模拟</span>
        </summary>
        <div class="mobile-control-popover">
          <HandsetControlPanel />
        </div>
      </details>
    </div>

    <div class="page-body">
      <main class="device-stage">
        <section class="layer layer-light">
          <AmbientLightStrip :ui-scale="handsetZoom" />
        </section>

        <section class="layer layer-handset">
          <HandsetDevice :ui-scale="handsetZoom" />
        </section>

        <section class="layer layer-time">
          <TimeSpeedControl />
        </section>

      </main>

      <aside class="control-sidebar" aria-label="手控器状态模拟控制台">
        <HandsetControlPanel />
      </aside>
    </div>
    <AppBottomBar v-if="!isShared" />
  </div>
</template>

<style scoped>
.page-wrapper {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #ffffff;
  font-family: var(--font-family);
  overflow: hidden;
}

.top-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 20px 6px;
  flex-shrink: 0;
}

.page-title { font-size: 17px; font-weight: 700; color: var(--text-primary); }
.stage-tools { display: none; align-items: center; gap: 1px; margin-left: -5px; }
.stage-tools .el-button { color: #5d554c; }
.share-button { margin-left: auto; color: #fff; border-color: #374740; background: #374740; font-weight: 700; }
.share-button:hover { color: #fff; border-color: #202a26; background: #202a26; }
.mobile-control-menu { display: none; }

.page-body {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  display: grid;
  grid-template-columns: minmax(620px, 1fr) minmax(330px, 390px);
  align-items: stretch;
  gap: clamp(18px, 2.4vw, 42px);
  padding: 12px clamp(24px, 3vw, 54px) 18px;
}

.layer { width: 100%; display: flex; justify-content: center; }

.device-stage {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: clamp(10px, 1.8vh, 18px);
}

.control-sidebar {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

@media (max-width: 1080px) {
  .page-body {
    overflow-y: auto;
    grid-template-columns: 1fr;
  }

  .control-sidebar { justify-content: center; }
}

/* 手机横屏时宽度会超过常规断点；以较小的可用高度继续保持操作优先布局。 */
@media (max-width: 760px), (orientation: landscape) and (max-height: 600px) {
  .top-bar {
    position: relative;
    min-height: 42px;
    padding: 8px 14px 5px;
  }
  .page-title { font-size: 15px; }
  .stage-tools { margin-left: -4px; }
  .stage-tools { display: flex; }
  .stage-tools .el-button { width: 27px; height: 27px; }
  .share-button { min-width: 0; margin-left: 3px; padding: 0 9px; font-size: 11px; }
  .mobile-control-menu {
    display: block;
    margin-left: auto;
    position: relative;
    z-index: 30;
  }
  .mobile-control-menu summary {
    height: 30px;
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 0 10px;
    list-style: none;
    border: 1px solid #ded6ca;
    border-radius: 999px;
    color: #54483c;
    background: rgba(255, 255, 255, 0.92);
    box-shadow: 0 3px 10px rgba(69, 51, 32, 0.1);
    font-size: 11px;
    font-weight: 700;
    cursor: pointer;
  }
  .mobile-control-menu summary::-webkit-details-marker { display: none; }
  .mobile-control-menu[open] summary {
    color: #fff;
    border-color: #3c4944;
    background: #303a36;
  }
  .menu-glyph { display: inline-flex; flex-direction: column; gap: 2px; }
  .menu-glyph i { width: 11px; height: 1.5px; border-radius: 99px; background: currentColor; }
  .mobile-control-popover {
    position: absolute;
    top: calc(100% + 8px);
    right: 0;
    width: min(360px, calc(100vw - 24px));
    max-height: min(68vh, 520px);
    overflow-y: auto;
    border-radius: 16px;
    box-shadow: 0 18px 42px rgba(24, 31, 28, 0.26);
  }
  .page-body {
    position: relative;
    overflow: hidden;
    display: flex;
    padding: 4px 12px 10px;
  }
  .device-stage {
    position: relative;
    width: 100%;
    justify-content: center;
  }
  /* 灯带作为手控器上方的环境层，不再将设备主体挤向视口底部。 */
  .layer-light {
    margin-bottom: -64px;
    transform: translateY(-12px);
  }
  .control-sidebar { display: none; }
  .layer-time {
    position: absolute;
    z-index: 15;
    top: 50%;
    right: 8px;
    width: auto;
    transform: translateY(-50%);
  }
  .layer-time :deep(.time-module) {
    width: 50px;
    flex-direction: column;
    gap: 7px;
    padding: 7px 5px;
  }
  .layer-time :deep(.clock-display),
  .layer-time :deep(.clock-label),
  .layer-time :deep(.clock-date),
  .layer-time :deep(.label) { display: none; }
  .layer-time :deep(.speed-control) { flex-direction: column; gap: 0; }
  .layer-time :deep(.el-button-group) { display: flex; flex-direction: column; gap: 4px; }
  .layer-time :deep(.el-button-group .el-button) {
    width: 40px;
    min-width: 40px;
    height: 33px;
    padding: 0;
    border-radius: 6px !important;
  }
  .layer-time :deep(.reset-button) {
    width: 40px;
    height: 34px;
    min-width: 40px;
    margin-left: 0;
    padding: 0;
  }
  .layer-time :deep(.reset-label) { display: none; }
  .layer-time :deep(.reset-icon) { font-size: 19px; }
}
</style>
