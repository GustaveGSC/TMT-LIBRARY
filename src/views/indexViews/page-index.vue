<template>
  <div class="index-page">
    <div class="bg-circle bg-circle-1"></div>
    <div class="bg-circle bg-circle-2"></div>

    <WindowControls :confirm-close="true" confirm-text="确认退出两平米软件库？" />

    <main class="main-area">
      <div class="module-groups">
        <div v-for="group in moduleGroups" :key="group.label" class="module-group">
          <div class="group-label">{{ group.label }}</div>
          <div class="modules">
            <div
              v-for="(mod, i) in group.items"
              :key="mod.key"
              class="module-card"
              :class="{ disabled: mod.disabled || mod.noPermission }"
              :style="{ animationDelay: `${0.05 + i * 0.07}s` }"
              @click="handleEnter(mod)"
            >
              <div class="module-icon">
                <component :is="mod.iconComp" :size="40" weight="duotone" color="#c4883a" />
              </div>
              <div class="module-name">{{ mod.name }}</div>
              <div class="module-desc">{{ mod.desc }}</div>
              <div v-if="mod.disabled" class="module-badge">即将上线</div>
              <div v-else-if="mod.noPermission" class="module-badge module-badge--noperm">无权限</div>
            </div>
          </div>
        </div>
      </div>
    </main>

    <footer class="bottom-bar">
      <!-- 左：作者图片 -->
      <div class="bar-left">
        <el-tooltip
          placement="top"
          :show-after="300"
          effect="light"
          popper-class="author-tooltip"
        >
          <template #content>
            <div class="author-tip">
              <div class="author-tip-title">遇到问题了？</div>
              <div class="author-tip-body">联系管理员获取帮助</div>
              <div class="author-tip-email">gusc@2m2.cc</div>
            </div>
          </template>
          <img src="@/assets/author.png" class="bar-author" alt="author" />
        </el-tooltip>
      </div>

      <!-- 中：横版 logo -->
      <div class="bar-center">
        <img src="@/assets/logo-banner.png" class="bar-logo-banner" alt="logo" />
      </div>

      <!-- 右：版本徽章 + 用户 -->
      <div class="bar-right">

        <!-- 版本徽章：点击检查/查看更新 -->
        <button v-if="isElectron" class="version-badge" :class="{ 'has-update': updateType !== 'none' }" @click="handleUpdate">
          <span class="version-text">v{{ version }}</span>
          <span v-if="updateType !== 'none'" class="version-dot"></span>
        </button>

        <div class="bar-divider"></div>

        <!-- 用户按钮 -->
        <button class="bar-btn" @click="handleUserSetting">
          <span class="bar-btn-avatar">{{ userInitial }}</span>
          <span>{{ userName }}</span>
        </button>
      </div>
    </footer>
  </div>

  <UserSettingsDrawer ref="settingsDrawer" />
  <UpdateDialog ref="updateDialog" />
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import http from '@/api/http'
import { checkUpdateType } from '@/utils/version'
import { usePermission } from '@/composables/usePermission'
import { isElectron } from '@/utils/platform'
import UserSettingsDrawer from '@/components/user/UserSettingsDrawer.vue'
import UpdateDialog from '@/components/update/UpdateDialog.vue'
import WindowControls from '@/components/common/WindowControls.vue'
import { PhCube, PhTruck, PhDatabase, PhWrench, PhCode } from '@phosphor-icons/vue'

const router         = useRouter()
const version        = ref('1.0.0')
const settingsDrawer = ref(null)
const updateDialog   = ref(null)

const updateType = ref('none')
const latestInfo = ref(null)

onMounted(async () => {
  if (window.electronAPI) {
    version.value = await window.electronAPI.getVersion()
  }

  try {
    const res = await http.get('/api/version/latest')
    if (res.success && res.data) {
      latestInfo.value = res.data
      const type = checkUpdateType(version.value, res.data.version)
      updateType.value = type

      if (type === 'force' && window.electronAPI) {
        await window.electronAPI.updater.check()
        updateDialog.value?.open({
          latestVersion:  res.data.version,
          currentVersion: version.value,
          releaseDate:    res.data.releaseDate,
          description:    res.data.description,
          isForce:        true,
        })
      }
    }
  } catch { }
})

const { isAdmin, canViewProduct, canViewShipping, canEditShipping, canViewAftersale, canViewRd } = usePermission()

const userInfo    = JSON.parse(localStorage.getItem('user') || '{}')
const userName    = computed(() => userInfo.display_name || userInfo.username || '游客')
const userInitial = computed(() => (userName.value?.[0] ?? '?').toUpperCase())
const isAuthor    = userInfo.username === 'author'

// 模块分组，各组独立渲染
// noPermission=true：无权限时禁用并显示"无权限"标签
// hidden=true：对当前用户不可见
const moduleGroups = computed(() => [
  {
    label: '业务数据',
    items: [
      {
        key: 'product',
        name: '产品库',
        desc: '产品信息管理与检索',
        iconComp: PhCube,
        route: '/product',
        disabled: false,
        noPermission: !canViewProduct,
      },
      {
        key: 'shipping',
        name: '发货数据',
        desc: '发货记录查询与统计',
        iconComp: PhTruck,
        route: '/shipping',
        disabled: false,
        noPermission: !canViewShipping,
      },
      {
        key: 'aftersale',
        name: '售后数据',
        desc: '售后记录查询与分析',
        iconComp: PhWrench,
        route: '/aftersale',
        disabled: false,
        noPermission: !canViewAftersale,
      },
    ],
  },
  {
    label: '工具',
    items: [
      {
        key: 'data-mgmt',
        name: '数据管理',
        desc: '导入数据与操作人配置',
        iconComp: PhDatabase,
        route: '/data-mgmt',
        disabled: false,
        noPermission: !canEditShipping,
      },
      // 研发部工具：有 rd:view 权限的用户可见
      {
        key: 'rd-tools',
        name: '研发部工具',
        desc: 'PDM转BOM · 变更单填写',
        iconComp: PhCode,
        route: '/rd-tools',
        disabled: false,
        noPermission: !canViewRd,
      },
    ],
  },
])

function handleEnter(mod) {
  if (mod.disabled || mod.noPermission) return
  router.push(mod.route)
}

async function handleUpdate() {
  if (updateType.value === 'none') {
    ElMessageBox.alert('当前已是最新版本', '检查更新', {
      confirmButtonText: '确定',
      type: 'success',
    })
    return
  }
  // optional 更新未在 onMounted 触发 electron-updater，此处确保 updateInfo 已加载
  // force 更新重复调用无害
  if (updateType.value === 'optional') {
    await window.electronAPI?.updater.check()
  }
  updateDialog.value?.open({
    latestVersion:  latestInfo.value?.version    || '',
    currentVersion: version.value,
    releaseDate:    latestInfo.value?.releaseDate || '',
    description:    latestInfo.value?.description || '',
    isForce:        updateType.value === 'force',
  })
}

function handleUserSetting() { settingsDrawer.value?.open() }
</script>

<style scoped>
.index-page {
  width: 100vw; height: 100vh;
  background: var(--bg);
  display: flex;
  flex-direction: column;
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
.module-emoji { font-size: 38px; line-height: 1; }
.module-name { font-size: 13px; font-weight: 600; color: var(--text-primary); letter-spacing: 0.04em; transition: color 0.2s; }
.module-desc { font-size: 11px; color: var(--text-muted); text-align: center; margin-top: -4px; }
.module-badge {
  position: absolute; top: -6px; right: 8px;
  background: var(--accent-bg); border: 1px solid var(--border);
  border-radius: 6px; padding: 2px 7px;
  font-size: 10px; color: var(--text-muted);
}
.module-badge--noperm {
  background: rgba(210, 70, 50, 0.07);
  border-color: rgba(210, 70, 50, 0.25);
  color: #c0402a;
}

.bottom-bar {
  position: relative; z-index: 1;
  height: 50px; display: flex;
  align-items: center; justify-content: space-between;
  padding: 0 18px;
  background: rgba(255,255,255,0.5);
  border-top: 1px solid var(--border);
  backdrop-filter: blur(12px);
}

/* 左：作者图片 */
.bar-left { display: flex; align-items: center; }
.bar-author {
  height: 28px;
  object-fit: contain;
  opacity: 0.75;
  border-radius: 4px;
}

/* 中：横版logo */
.bar-center {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
}
.bar-logo-banner {
  height: 22px;
  object-fit: contain;
  opacity: 0.6;
}

/* 右：版本徽章 + 用户 */
.bar-right { display: flex; align-items: center; gap: 4px; }
.bar-divider { width: 1px; height: 13px; background: var(--border); margin: 0 4px; }

/* 版本徽章 */
.version-badge {
  position: relative;
  display: flex; align-items: center;
  padding: 4px 9px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg-card);
  cursor: pointer;
  transition: all 0.2s;
  font-family: inherit;
}
.version-badge:hover { border-color: var(--accent); }
.version-badge.has-update { border-color: rgba(200,60,50,0.3); }

.version-text {
  font-size: 11px;
  color: var(--text-muted);
  font-family: monospace;
}

.version-dot {
  position: absolute;
  top: -3px; right: -3px;
  width: 7px; height: 7px;
  border-radius: 50%;
  background: #e05040;
  border: 1.5px solid var(--bg);
}

.bar-btn {
  position: relative;
  display: flex; align-items: center; gap: 5px;
  padding: 5px 10px; border: none;
  background: transparent; color: var(--text-muted);
  font-size: 12px; font-family: inherit;
  cursor: pointer; border-radius: 6px;
  transition: all 0.2s; letter-spacing: 0.03em;
}
.bar-btn:hover { background: rgba(196,136,58,0.08); color: var(--accent); }

.bar-btn-avatar {
  width: 18px; height: 18px; border-radius: 50%;
  background: linear-gradient(135deg, var(--accent), var(--accent-hover));
  display: flex; align-items: center; justify-content: center;
  font-size: 10px; font-weight: 700; color: #fff; flex-shrink: 0;
}
</style>

<!-- 全局样式：tooltip popper 穿透 scoped -->
<style>
.author-tooltip.el-popper {
  border-radius: 10px !important;
  border: 1px solid #e8dece !important;
  box-shadow: 0 8px 24px rgba(0,0,0,0.1) !important;
  padding: 0 !important;
}
.author-tip {
  padding: 12px 16px;
  font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
  min-width: 160px;
}
.author-tip-title {
  font-size: 13px;
  font-weight: 600;
  color: #3a2e22;
  margin-bottom: 4px;
}
.author-tip-body {
  font-size: 12px;
  color: #8a7a68;
  margin-bottom: 8px;
}
.author-tip-email {
  font-size: 12px;
  color: #c4883a;
  letter-spacing: 0.02em;
}
</style>