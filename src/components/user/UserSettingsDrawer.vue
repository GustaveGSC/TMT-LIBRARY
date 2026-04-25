<!-- ─────────────────────────────────────────
  组件：UserSettingsDrawer
  功能：用户设置抽屉，包含修改密码、切换主题、
        管理员专属（用户管理、权限管理、版本发布）、退出登录
───────────────────────────────────────── -->

<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/api/http'

// ── 路由 ──────────────────────────────────
const router  = useRouter()
const visible = ref(false)

// ── 用户信息 ──────────────────────────────
const userInfo    = ref(JSON.parse(localStorage.getItem('user') || '{}'))
const username    = computed(() => userInfo.value.username || '')
const displayName = computed(() => userInfo.value.display_name || '')
const isAdmin     = computed(() => userInfo.value.roles?.includes('admin') ?? false)
const isAuthor    = computed(() => userInfo.value.username === 'author')
const isGuest     = computed(() => userInfo.value.username === '游客')
const userInitial = computed(() => (displayName.value || username.value || '?')[0].toUpperCase())

// ── 展开分区控制 ──────────────────────────
const openSection = ref('')
function toggleSection(key) {
  openSection.value = openSection.value === key ? '' : key
}

// ── 修改密码 ──────────────────────────────
const pwdLoading   = ref(false)
const passwordForm = ref({ old: '', new: '', confirm: '' })

const passwordValid = computed(() =>
  passwordForm.value.old &&
  passwordForm.value.new.length >= 6 &&
  passwordForm.value.new === passwordForm.value.confirm
)

async function handleChangePassword() {
  pwdLoading.value = true
  try {
    const res = await http.put(`/api/account/users/${userInfo.value.id}/password`, {
      old_password: passwordForm.value.old,
      new_password: passwordForm.value.new,
    })
    if (res.success) {
      ElMessage.success('密码修改成功')
      passwordForm.value = { old: '', new: '', confirm: '' }
      openSection.value  = ''
    } else {
      ElMessage.error(res.message || '修改失败')
    }
  } catch {
    ElMessage.error('网络错误，请重试')
  } finally {
    pwdLoading.value = false
  }
}

// ── 切换主题 ──────────────────────────────
const themes = [
  { key: 'theme-a', name: '奶油纸质', bg: '#ede8dc', accent: '#c4883a' },
  { key: 'theme-b', name: '墨青竹韵', bg: '#e8ede9', accent: '#3a7a5c' },
  { key: 'theme-c', name: '深海墨蓝', bg: '#e4eaf4', accent: '#1d4ed8' },
]

const currentTheme = ref(localStorage.getItem('theme') || 'theme-a')

function switchTheme(key) {
  currentTheme.value = key
  localStorage.setItem('theme', key)
  // theme-a 为默认不需要 class，其他主题加对应 class
  document.documentElement.className = key === 'theme-a' ? '' : key
}

// ── 管理员页面跳转 ────────────────────────
function handleNav(path) {
  visible.value = false
  router.push(path)
}

// ── 退出登录 ──────────────────────────────
async function handleLogout() {
  try {
    await ElMessageBox.confirm('确认退出登录？', '退出登录', {
      confirmButtonText: '退出',
      cancelButtonText:  '取消',
      type:              'warning',
    })
    localStorage.removeItem('user')
    visible.value = false
    if (window.electronAPI) {
      window.electronAPI.logout()
    } else {
      router.push('/login')
    }
  } catch {
    // 取消，不做操作
  }
}

// ── 暴露 open 方法给父组件 ────────────────
function open() {
  userInfo.value    = JSON.parse(localStorage.getItem('user') || '{}')
  openSection.value = ''
  visible.value     = true
}

defineExpose({ open })
</script>

<template>
  <el-drawer
    v-model="visible"
    direction="rtl"
    :size="320"
    :with-header="false"
    class="user-drawer"
  >
    <div class="drawer-inner">

      <!-- 头部用户信息 -->
      <div class="drawer-header">
        <div class="user-avatar">{{ userInitial }}</div>
        <div class="user-info">
          <div class="user-name">{{ displayName || username }}</div>
          <div class="user-role">{{ isAdmin ? '管理员' : isGuest ? '游客' : '普通用户' }}</div>
        </div>
      </div>

      <div class="drawer-divider"></div>

      <!-- 修改密码（游客不显示） -->
      <template v-if="!isGuest">
        <div class="section">
          <div class="section-title" @click="toggleSection('password')">
            <span>修改密码</span>
            <span class="section-arrow" :class="{ open: openSection === 'password' }">›</span>
          </div>
          <transition name="expand">
            <div v-if="openSection === 'password'" class="section-body">
              <div class="field">
                <div class="field-label">原密码</div>
                <el-input v-model="passwordForm.old" type="password" placeholder="输入原密码" show-password />
              </div>
              <div class="field">
                <div class="field-label">新密码</div>
                <el-input v-model="passwordForm.new" type="password" placeholder="至少 6 位" show-password />
              </div>
              <div class="field">
                <div class="field-label">确认新密码</div>
                <el-input v-model="passwordForm.confirm" type="password" placeholder="再次输入新密码" show-password />
              </div>
              <el-button
                type="primary"
                :loading="pwdLoading"
                :disabled="!passwordValid"
                style="width:100%;margin-top:4px;"
                @click="handleChangePassword"
              >
                确认修改
              </el-button>
            </div>
          </transition>
        </div>
        <div class="drawer-divider"></div>
      </template>

      <!-- 切换主题 -->
      <div class="section">
        <div class="section-title" @click="toggleSection('theme')">
          <span>切换主题</span>
          <span class="section-arrow" :class="{ open: openSection === 'theme' }">›</span>
        </div>
        <transition name="expand">
          <div v-if="openSection === 'theme'" class="section-body">
            <div class="theme-list">
              <div
                v-for="t in themes"
                :key="t.key"
                class="theme-item"
                :class="{ active: currentTheme === t.key }"
                @click="switchTheme(t.key)"
              >
                <div class="theme-preview">
                  <div class="theme-color" :style="{ background: t.bg }"></div>
                  <div class="theme-color" :style="{ background: t.accent }"></div>
                </div>
                <span class="theme-name">{{ t.name }}</span>
                <span v-if="currentTheme === t.key" class="theme-check">✓</span>
              </div>
            </div>
          </div>
        </transition>
      </div>

      <div class="drawer-divider"></div>

      <!-- 管理员专属区域 -->
      <template v-if="isAdmin">
        <div class="section-group-label">管理员</div>

        <div class="section">
          <div class="section-title nav" @click="handleNav('/admin/users')">
            <div class="nav-icon-wrap">
              <span class="nav-icon">👥</span>
              <span>用户管理</span>
            </div>
            <span class="section-arrow">›</span>
          </div>
        </div>

        <div class="section">
          <div class="section-title nav" @click="handleNav('/admin/permissions')">
            <div class="nav-icon-wrap">
              <span class="nav-icon">🔑</span>
              <span>权限管理</span>
            </div>
            <span class="section-arrow">›</span>
          </div>
        </div>

        <div class="section">
          <div class="section-title nav" @click="handleNav('/admin/version-release')">
            <div class="nav-icon-wrap">
              <span class="nav-icon">🚀</span>
              <span>版本发布</span>
            </div>
            <span class="section-arrow">›</span>
          </div>
        </div>

        <div class="drawer-divider"></div>
      </template>

      <!-- author 专属 -->
      <template v-if="isAuthor">
        <div class="section-group-label">开发者</div>

        <div class="section">
          <div class="section-title nav" @click="handleNav('/admin/login-logs')">
            <div class="nav-icon-wrap">
              <span class="nav-icon">🔍</span>
              <span>用户分析</span>
            </div>
            <span class="section-arrow">›</span>
          </div>
        </div>

        <div class="drawer-divider"></div>
      </template>

      <!-- 退出登录 -->
      <div class="section">
        <div class="section-title logout" @click="handleLogout">
          <span>退出登录</span>
          <span class="section-arrow">›</span>
        </div>
      </div>

    </div>
  </el-drawer>
</template>

<style>
/* 覆盖 el-drawer 默认样式（非 scoped，需要穿透） */
.user-drawer .el-drawer {
  background: var(--bg-card) !important;
  border-left: 1px solid var(--border) !important;
}
.user-drawer .el-drawer__body {
  padding: 0 !important;
}
</style>

<style scoped>
/* ── 抽屉主体 ─────────────────────────────── */
.drawer-inner {
  height: 100%;
  display: flex;
  flex-direction: column;
  font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
  overflow-y: auto;
}

/* ── 头部 ──────────────────────────────────── */
.drawer-header {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 28px 24px 24px;
}

.user-avatar {
  width: 44px; height: 44px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--accent), var(--accent-hover));
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  font-weight: 700;
  color: #fff;
  flex-shrink: 0;
  box-shadow: 0 4px 12px rgba(196,136,58,0.25);
}

.user-name { font-size: 15px; font-weight: 600; color: var(--text-primary); }
.user-role { font-size: 12px; color: var(--text-muted); margin-top: 3px; }

/* ── 分隔线 ────────────────────────────────── */
.drawer-divider { height: 1px; background: var(--border); margin: 0 24px; }

/* ── 分区 ──────────────────────────────────── */
.section { padding: 0 24px; }

.section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 0;
  font-size: 14px;
  color: var(--text-primary);
  cursor: pointer;
  user-select: none;
  transition: color 0.2s;
}
.section-title:hover { color: var(--accent); }
.section-title.logout { color: #c05040; }
.section-title.logout:hover { color: #a03020; }

.section-arrow {
  font-size: 16px;
  color: var(--text-muted);
  transition: transform 0.2s;
  line-height: 1;
}
.section-arrow.open { transform: rotate(90deg); }
.section-body { padding-bottom: 16px; }

/* ── 管理员分组标签 ────────────────────────── */
.section-group-label {
  font-size: 11px;
  color: var(--text-muted);
  letter-spacing: 0.1em;
  padding: 12px 24px 4px;
  opacity: 0.6;
}

/* ── 管理员导航项 ──────────────────────────── */
.nav-icon-wrap { display: flex; align-items: center; gap: 10px; }
.nav-icon { font-size: 15px; line-height: 1; }

/* ── 字段 ──────────────────────────────────── */
.field { margin-bottom: 12px; }
.field-label {
  font-size: 11px;
  color: var(--text-muted);
  letter-spacing: 0.08em;
  margin-bottom: 6px;
}

/* ── 主题选择 ──────────────────────────────── */
.theme-list { display: flex; flex-direction: column; gap: 8px; }

.theme-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1.5px solid var(--border);
  cursor: pointer;
  transition: all 0.2s;
  background: var(--accent-bg);
}
.theme-item:hover { border-color: var(--accent); }
.theme-item.active { border-color: var(--accent); background: var(--bg-card); }

.theme-preview { display: flex; gap: 4px; }
.theme-color {
  width: 14px; height: 14px;
  border-radius: 4px;
  border: 1px solid rgba(0,0,0,0.06);
}
.theme-name { font-size: 13px; color: var(--text-primary); flex: 1; }
.theme-check { font-size: 12px; color: var(--accent); font-weight: 700; }

/* ── 展开动画 ──────────────────────────────── */
.expand-enter-active, .expand-leave-active {
  transition: all 0.2s ease;
  overflow: hidden;
}
.expand-enter-from, .expand-leave-to { opacity: 0; max-height: 0; }
.expand-enter-to, .expand-leave-from { opacity: 1; max-height: 400px; }
</style>