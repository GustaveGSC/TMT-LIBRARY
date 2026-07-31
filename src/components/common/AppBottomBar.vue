<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, computed, onMounted } from 'vue'
import { ElMessageBox } from 'element-plus'
import http from '@/api/http'
import { checkUpdateType } from '@/utils/version'
import { isElectron } from '@/utils/platform'
import UserSettingsDrawer from '@/components/user/UserSettingsDrawer.vue'
import UpdateDialog from '@/components/update/UpdateDialog.vue'

// ── 响应式状态 ────────────────────────────────────
const version        = ref('1.0.0')
const settingsDrawer = ref(null)
const updateDialog   = ref(null)
const updateType     = ref('none')
const latestInfo     = ref(null)

// ── 计算属性 ──────────────────────────────────────
const userInfo    = JSON.parse(localStorage.getItem('user') || '{}')
const userName    = computed(() => userInfo.display_name || userInfo.username || '用户')
const userInitial = computed(() => (userName.value?.[0] ?? '?').toUpperCase())

// ── 生命周期 ──────────────────────────────────────
onMounted(async () => {
  // 版本检查只在 Electron 下做：版本徽章与强制更新弹窗都是 isElectron 门控的，
  // Web 端这个请求拿到结果也无处可用。本组件现在挂在每个页面上，
  // 不加这个判断会让每次换页都多打一次 /api/version/latest。
  if (!isElectron) return

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
  } catch { /* 版本检查失败不影响页面使用 */ }
})

// ── 方法 ──────────────────────────────────────────
async function handleUpdate() {
  if (updateType.value === 'none') {
    ElMessageBox.alert('当前已是最新版本', '检查更新', {
      confirmButtonText: '好', type: 'success',
    })
    return
  }
  if (updateType.value === 'optional') {
    await window.electronAPI?.updater.check()
  }
  updateDialog.value?.open({
    latestVersion:  latestInfo.value?.version,
    currentVersion: version.value,
    releaseDate:    latestInfo.value?.releaseDate,
    description:    latestInfo.value?.description,
    isForce:        updateType.value === 'force',
  })
}

function handleUserSetting() { settingsDrawer.value?.open() }
</script>

<template>
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

    <!-- 右：版本徽章 + 用户（管理者/开发者/运维入口在用户设置抽屉里，按权限码显示） -->
    <div class="bar-right">
      <!-- 版本徽章：点击检查/查看更新（桌面端） -->
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

  <UserSettingsDrawer ref="settingsDrawer" />
  <UpdateDialog ref="updateDialog" />
</template>

<style scoped>
/* 作为页面根 flex column 的最后一个子项，占据固定 50px 高度。
   各页根容器都是 height:100vh + flex-direction:column + overflow:hidden，
   所以这里用普通流式定位即可，不需要 fixed，也不会遮挡内容。
   （主页在手机端会把页面改为可滚动，那里另有 :deep(.bottom-bar) 覆盖为 fixed） */
.bottom-bar {
  position: relative; z-index: 1;
  height: 50px; flex-shrink: 0;
  display: flex;
  align-items: center; justify-content: space-between;
  padding: 0 18px;
  background: rgba(255,255,255,0.5);
  border-top: 1px solid var(--border);
  backdrop-filter: blur(12px);
  box-sizing: border-box;
}

/* 左：作者图片 */
.bar-left { display: flex; align-items: center; }
.bar-author {
  height: 28px;
  object-fit: contain;
  opacity: 0.75;
  border-radius: 4px;
}

/* 中：横版 logo */
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

/* 用户按钮 */
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

/* 手机端：仅缩小内容，不改定位（定位由所在页面决定） */
@media (max-width: 768px) {
  .bottom-bar { padding: 0 12px; }
  .bar-logo-banner { height: 18px; }
  .bar-author { height: 24px; }
  .bar-btn { font-size: 11px; }
}
@media (orientation: landscape) and (max-height: 600px) {
  .bottom-bar { padding: 0 12px; }
  .bar-logo-banner { height: 18px; }
}
</style>

<!-- 非 scoped：el-tooltip 的浮层被传送到 body，scoped 选择器匹配不到 -->
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
