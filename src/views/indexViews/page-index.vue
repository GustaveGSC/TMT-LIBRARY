<template>
  <div class="index-page">
    <div class="bg-circle bg-circle-1"></div>
    <div class="bg-circle bg-circle-2"></div>

    <WindowControls :confirm-close="true" confirm-text="确认退出两平米资料站？" />

    <main class="main-area">
      <div class="module-groups">
        <div v-for="group in moduleGroups" :key="group.label" class="module-group">
          <div class="group-label">{{ group.label }}</div>
          <div class="modules">
            <div
              v-for="(mod, i) in group.items"
              :key="mod.key"
              class="module-card"
              :class="{ disabled: mod.disabled }"
              :style="{ animationDelay: `${0.05 + i * 0.07}s` }"
              @click="handleEnter(mod)"
            >
              <div class="module-icon">
                <img :src="mod.icon" class="module-icon-img" alt="" />
              </div>
              <div class="module-name">{{ mod.name }}</div>
              <div v-if="mod.disabled" class="module-badge">即将上线</div>
            </div>
          </div>
        </div>
      </div>
    </main>

    <AppBottomBar />
  </div>
</template>

<script setup>
import { computed, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { usePermission } from '@/composables/usePermission'
import { isElectron } from '@/utils/platform'
import WindowControls from '@/components/common/WindowControls.vue'
import AppBottomBar from '@/components/common/AppBottomBar.vue'
import iconProduct   from '@/assets/icons/icon_product.png'
import iconShipping  from '@/assets/icons/icon_shipping.png'
import iconAftersale from '@/assets/icons/icon_aftersale.png'
import iconMaterial from '@/assets/icons/icon_material.png'
import iconRdTools      from '@/assets/icons/icon_rd_tools.png'
import iconAftersaleTools from '@/assets/icons/icon_aftersale_tools.png'
import iconGeneralTools from '@/assets/icons/icon_general_tools.png'
import iconLab from '@/assets/icons/icon_handset_sim.png'

const router = useRouter()

// 移动端 web：本页需要纵向滚动，临时解除全局 overflow:hidden
if (!isElectron) {
  onMounted(() => {
    document.documentElement.style.overflow = 'auto'
    document.body.style.overflow = 'auto'
  })
  onBeforeUnmount(() => {
    document.documentElement.style.overflow = ''
    document.body.style.overflow = ''
  })
}

// 版本检查、用户信息、用户设置抽屉与更新弹窗均已移入 AppBottomBar 组件

const { canViewProduct, canViewShipping, canViewAftersale, canViewRd } = usePermission()

// 模块分组，各组独立渲染
// 无权限的功能入口直接不渲染（不显示"无权限"标签），与全站其他位置的权限处理方式统一。
// disabled=true 是另一回事（即将上线，与权限无关），继续保留标签展示。
const moduleGroups = computed(() => [
  {
    label: '业务数据',
    items: [
      {
        key: 'product',
        name: '产品库',
        icon: iconProduct,
        route: '/product',
        disabled: false,
        visible: canViewProduct,
      },
      {
        key: 'shipping',
        name: '发货数据',
        icon: iconShipping,
        route: '/shipping',
        disabled: false,
        visible: canViewShipping,
      },
      {
        key: 'aftersale',
        name: '售后数据',
        icon: iconAftersale,
        route: '/aftersale',
        disabled: false,
        visible: canViewAftersale,
      },
      // 物料库：ERP 导入数据与编码规则的归属地
      {
        key: 'material',
        name: '物料库',
        icon: iconMaterial,
        route: '/material',
        disabled: false,
        visible: canViewProduct,
      },
    ].filter(mod => mod.visible),
  },
  {
    label: '工具',
    items: [
      // 研发部工具：有 rd:view 权限的用户可见
      {
        key: 'rd-tools',
        name: '研发部工具',
        icon: iconRdTools,
        route: '/rd-tools',
        disabled: false,
        visible: canViewRd,
      },
      // 售后工具：售后记录填写与导出，页面尚未开发，先占位
      {
        key: 'aftersale-tools',
        name: '售后工具',
        icon: iconAftersaleTools,
        route: '/aftersale-tools',
        disabled: true,
        visible: canViewAftersale,
      },
      {
        key: 'general-tools',
        name: '通用工具',
        icon: iconGeneralTools,
        route: '/general-tools',
        disabled: false,
        visible: true,
      },
    ].filter(mod => mod.visible),
  },
  {
    label: '实验室',
    items: [
      {
        key: 'lab',
        name: '模拟手控系统',
        icon: iconLab,
        route: '/lab',
        disabled: false,
        visible: true,
      },
    ].filter(mod => mod.visible),
  },
].filter(group => group.items.length > 0))

const MOBILE_UNSUPPORTED = ['rd-tools']

function handleEnter(mod) {
  if (mod.disabled) return
  if (window.innerWidth <= 768 && MOBILE_UNSUPPORTED.includes(mod.key)) {
    ElMessage({ message: '手机端不支持该功能', type: 'warning', duration: 2000 })
    return
  }
  router.push(mod.route)
}

</script>

<style scoped>
.index-page {
  width: 100vw; height: 100vh;
  background: var(--bg);
  display: flex;
  flex-direction: column;
  justify-content: center;
  position: relative;
  overflow: hidden;
  font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

.bg-circle { position: absolute; border-radius: 50%; pointer-events: none; }
.bg-circle-1 {
  width: 500px; height: 500px;
  background: radial-gradient(circle, rgba(196,136,58,0.09) 0%, transparent 70%);
  top: -120px; right: -80px;
}
.bg-circle-2 {
  width: 360px; height: 360px;
  background: radial-gradient(circle, rgba(160,100,40,0.06) 0%, transparent 70%);
  bottom: 60px; left: -60px;
}

.main-area {
  flex: 1; display: flex;
  align-items: center; justify-content: center;
  position: relative; z-index: 1;
}

.module-groups {
  display: flex;
  flex-direction: column;
  gap: 20px;
  padding: 16px 48px;
}

.module-group {
  display: flex;
  flex-direction: column;
  gap: 14px;
  background: rgba(255, 255, 255, 0.55);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 16px 20px 18px;
  backdrop-filter: blur(8px);
}

.group-label {
  font-size: 11px;
  font-weight: 700;
  color: var(--accent);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  display: flex;
  align-items: center;
  gap: 8px;
}
.group-label::before {
  content: '';
  display: inline-block;
  width: 3px;
  height: 12px;
  background: var(--accent);
  border-radius: 2px;
  opacity: 0.7;
}

.modules { display: flex; gap: 24px; flex-wrap: wrap; justify-content: flex-start; }

.module-card {
  position: relative; width: 130px;
  display: flex; flex-direction: column;
  align-items: center; gap: 10px;
  cursor: pointer;
  animation: card-in 0.5s cubic-bezier(0.16, 1, 0.3, 1) both;
}

@keyframes card-in {
  from { opacity: 0; transform: translateY(20px) scale(0.95); }
  to   { opacity: 1; transform: translateY(0) scale(1); }
}

.module-card:not(.disabled):hover .module-icon {
  transform: translateY(-6px) scale(1.05);
  box-shadow: 0 16px 40px rgba(196,136,58,0.2), 0 4px 12px rgba(196,136,58,0.12);
}
.module-card:not(.disabled):hover .module-name { color: var(--accent); }
.module-card:not(.disabled):active .module-icon { transform: translateY(-2px) scale(0.98); }
.module-card.disabled { opacity: 0.45; cursor: not-allowed; }

.module-icon {
  width: 96px; height: 96px; border-radius: 26px;
  display: flex; align-items: center; justify-content: center;
  background: var(--bg-card);
  border: 1.5px solid var(--border);
  box-shadow: 0 4px 16px var(--shadow), inset 0 1px 0 rgba(255,255,255,0.8);
  transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}
.module-icon-img { width: 56px; height: 56px; object-fit: contain; }
.module-emoji { font-size: 38px; line-height: 1; }
.module-name { font-size: 13px; font-weight: 600; color: var(--text-primary); letter-spacing: 0.04em; transition: color 0.2s; }
.module-badge {
  position: absolute; top: -6px; right: 8px;
  background: var(--accent-bg); border: 1px solid var(--border);
  border-radius: 6px; padding: 2px 7px;
  font-size: 10px; color: var(--text-muted);
}


/* ── 移动端响应式（≤768px 竖屏）────────────────────────── */
@media (max-width: 768px) {
  /* 页面自然高度，允许滚动；底栏 fixed 钉在视口底部 */
  .index-page {
    height: auto;
    min-height: 100vh;
    overflow-x: hidden;
    padding-bottom: 50px; /* 为 fixed 底栏留空 */
  }
  .main-area { flex: unset; padding: 16px 0 8px; }
  .bottom-bar {
    position: fixed;
    bottom: 0; left: 0; right: 0;
    z-index: 100;
  }
  .module-groups { padding: 8px 16px; gap: 14px; }
  .module-group { padding: 12px 14px 14px; }
  .modules { gap: 14px; }
  .module-card { width: 100px; }
  .module-icon { width: 72px; height: 72px; border-radius: 18px; }
  .module-icon-img { width: 40px; height: 40px; }
  .module-name { font-size: 12px; }
  .bottom-bar { padding: 0 12px; }
  .bar-logo-banner { height: 18px; }
}
@media (max-width: 400px) {
  .module-card { width: 86px; }
  .module-icon { width: 60px; height: 60px; border-radius: 14px; }
  .module-icon-img { width: 34px; height: 34px; }
  .modules { gap: 10px; }
}

/* ── 手机横屏：视口矮，页面可滚动，底栏 fixed ───────────── */
@media (orientation: landscape) and (max-height: 600px) {
  .index-page {
    height: auto;
    min-height: 100vh;
    overflow-x: hidden;
    padding-bottom: 50px;
  }
  .main-area { flex: unset; padding: 8px 0; }
  .bottom-bar {
    position: fixed;
    bottom: 0; left: 0; right: 0;
    z-index: 100;
    padding: 0 12px;
  }
  .module-groups { padding: 6px 24px; gap: 10px; }
  .module-group { padding: 10px 14px 12px; }
  .modules { gap: 14px; }
  .module-card { width: 90px; }
  .module-icon { width: 60px; height: 60px; border-radius: 16px; }
  .module-icon-img { width: 34px; height: 34px; }
  .module-name { font-size: 11px; }
}
</style>
