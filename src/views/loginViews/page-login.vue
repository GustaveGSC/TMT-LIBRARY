<script setup>
// 导入
import { ref, reactive, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { checkUpdateType } from '@/utils/version'
import { isElectron } from '@/utils/platform'
import http from '@/api/http'
import GToast from '@/components/common/GToast.vue'
import WindowControls from '@/components/common/WindowControls.vue'
import UpdateDialog from '@/components/update/UpdateDialog.vue'
import { View as IconView, Hide as IconHide } from '@element-plus/icons-vue'

// ── 路由 & 全局 ref ──────────────────────────────────────────
const router      = useRouter()
const toast       = ref(null)
const updateDialog = ref(null)

// ── 表单状态 ─────────────────────────────────────────────────
const mode        = ref('login')
const loading     = ref(false)
const isFlipping  = ref(false)
const version     = ref('1.0.0')
const showPassword = ref(false)

const mottos = [
  '享受每一天的好心情',
  '保持你的好奇心',
  '今天也要元气满满',
  '把每件小事做到位',
]
const motto = mottos[Math.floor(Math.random() * mottos.length)]

window.electronAPI?.getVersion().then(v => { version.value = v })

const rememberAccount = ref(localStorage.getItem('remembered_username') !== null)
const loginForm = reactive({
  username: localStorage.getItem('remembered_username') ?? '',
  password: '',
})
const registerForm    = reactive({ username: '', displayName: '', password: '', confirmPassword: '' })
const registerTouched = reactive({ username: false, password: false, confirmPassword: false })

// ── 计算属性 ─────────────────────────────────────────────────
const registerErrors = computed(() => ({
  username:        !registerForm.username.trim(),
  password:        registerForm.password.length > 0 && registerForm.password.length < 6,
  confirmPassword: registerForm.confirmPassword.length > 0 && registerForm.confirmPassword !== registerForm.password,
}))

const registerValid = computed(() =>
  registerForm.username.trim() &&
  registerForm.password.length >= 6 &&
  registerForm.password === registerForm.confirmPassword
)

// ── 动画角色状态 ─────────────────────────────────────────────
const purpleRef = ref(null)
const blackRef  = ref(null)
const orangeRef = ref(null)
const yellowRef = ref(null)

// 每个角色的动画 pose（bodySkew/faceX/faceY/eyeX/eyeY/blinking）
const purplePose = reactive({ bodySkew: 0, faceX: 0, faceY: 0, eyeX: 0, eyeY: 0, blinking: false })
const blackPose  = reactive({ bodySkew: 0, faceX: 0, faceY: 0, eyeX: 0, eyeY: 0, blinking: false })
const orangePose = reactive({ bodySkew: 0, faceX: 0, faceY: 0, eyeX: 0, eyeY: 0 })
const yellowPose = reactive({ bodySkew: 0, faceX: 0, faceY: 0, eyeX: 0, eyeY: 0 })

// Purple 特有动画（密码偷看）
const purpleHeight    = ref(280)  // peek时 280 → 308
const purpleExtraSkew = ref(0)    // peek时额外倾斜 -12deg

// 交互状态
const isLookingAtEachOther = ref(false)
const isLookingAway        = ref(false)

// 缓存 bounding rect（避免每帧 reflow）
const charRects = { purple: null, black: null, orange: null, yellow: null }
const blinkTimers = []
let rafId     = null
let lookTimer = null

// ── 动画工具函数 ──────────────────────────────────────────────
function clamp(v, min, max) { return Math.min(Math.max(v, min), max) }

function refreshRects() {
  if (purpleRef.value) charRects.purple = purpleRef.value.getBoundingClientRect()
  if (blackRef.value)  charRects.black  = blackRef.value.getBoundingClientRect()
  if (orangeRef.value) charRects.orange = orangeRef.value.getBoundingClientRect()
  if (yellowRef.value) charRects.yellow = yellowRef.value.getBoundingClientRect()
}

function computePose(rect, mx, my, { lookAway = false, forceDir = null, lookAtCenter = false } = {}) {
  if (!rect) return { bodySkew: 0, faceX: 0, faceY: 0, eyeX: 0, eyeY: 0 }
  const cx = rect.left + rect.width  / 2
  const cy = rect.top  + rect.height / 3   // 聚焦头部区域
  let dx = mx - cx
  let dy = my - cy
  if (lookAtCenter)     { dx = 0; dy = 0 }                      // 互看：眼睛向中
  else if (forceDir)    { dx = forceDir.dx; dy = forceDir.dy }  // 强制方向（偷看密码）
  else if (lookAway)    { dx = -dx * 0.3; dy = -dy * 0.3 }      // 密码可见时看向反方向
  return {
    bodySkew: clamp(-dx / 120, -6, 6),
    faceX:    clamp( dx /  20, -15, 15),
    faceY:    clamp( dy /  30, -10, 10),
    eyeX:     clamp( dx /  25, -5, 5),
    eyeY:     clamp( dy /  35, -4, 4),
  }
}

function updateAllPoses(mx, my) {
  const isPeeking = loginForm.password.length > 0 && !showPassword.value
  const peekDir   = isPeeking ? { dx: 120, dy: -40 } : null     // 朝向右侧表单方向
  const lookAway  = isLookingAway.value && !isPeeking
  const atCenter  = isLookingAtEachOther.value
  const x = mx ?? 0
  const y = my ?? 0
  Object.assign(purplePose, computePose(charRects.purple, x, y, { lookAway, forceDir: peekDir, lookAtCenter: atCenter }))
  Object.assign(blackPose,  computePose(charRects.black,  x, y, { lookAway, forceDir: peekDir, lookAtCenter: atCenter }))
  Object.assign(orangePose, computePose(charRects.orange, x, y, { lookAway }))
  Object.assign(yellowPose, computePose(charRects.yellow, x, y, { lookAway }))
}

// mousemove + RAF 节流
let lastMx = 0, lastMy = 0
function onMouseMove(e) {
  lastMx = e.clientX; lastMy = e.clientY
  if (rafId) return
  rafId = requestAnimationFrame(() => {
    rafId = null
    updateAllPoses(lastMx, lastMy)
  })
}

// 随机眨眼（自调度，避免 setInterval 漂移）
function scheduleBlink(pose) {
  const id = setTimeout(() => {
    pose.blinking = true
    const id2 = setTimeout(() => {
      pose.blinking = false
      scheduleBlink(pose)
    }, 150)
    blinkTimers.push(id2)
  }, 3000 + Math.random() * 4000)
  blinkTimers.push(id)
}

// 聚焦输入框 → 角色互视 800ms
function onInputFocus() {
  isLookingAtEachOther.value = true
  if (lookTimer) clearTimeout(lookTimer)
  lookTimer = setTimeout(() => {
    isLookingAtEachOther.value = false
    updateAllPoses(lastMx, lastMy)
  }, 800)
}

// ── Watch: 密码状态 → Purple peek 动画 ───────────────────────
watch(
  () => [loginForm.password, showPassword.value],
  ([pwd, show]) => {
    if (pwd.length > 0 && !show) {
      // 有密码且隐藏：Purple 长高偷看
      purpleHeight.value    = 308
      purpleExtraSkew.value = -12
      isLookingAway.value   = false
    } else if (pwd.length > 0 && show) {
      // 有密码且显示：角色看向别处
      purpleHeight.value    = 280
      purpleExtraSkew.value = 0
      isLookingAway.value   = true
    } else {
      // 无密码：恢复正常
      purpleHeight.value    = 280
      purpleExtraSkew.value = 0
      isLookingAway.value   = false
    }
    updateAllPoses(lastMx, lastMy)
  }
)

// ── 生命周期 ─────────────────────────────────────────────────
onMounted(async () => {
  if (window.electronAPI) {
    version.value = await window.electronAPI.getVersion()
  }

  // 强制更新检测（仅 Electron）
  if (window.electronAPI) {
    try {
      const res = await http.get('/api/version/latest')
      if (res.success && res.data) {
        const type = checkUpdateType(version.value, res.data.version)
        if (type === 'force') {
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
  }

  // 角色动画初始化
  window.addEventListener('mousemove', onMouseMove)
  window.addEventListener('resize', () => { refreshRects(); updateAllPoses(lastMx, lastMy) })
  await nextTick()
  refreshRects()
  scheduleBlink(purplePose)
  scheduleBlink(blackPose)
})

onUnmounted(() => {
  window.removeEventListener('mousemove', onMouseMove)
  window.removeEventListener('resize', refreshRects)
  if (rafId) cancelAnimationFrame(rafId)
  blinkTimers.forEach(clearTimeout)
  if (lookTimer) clearTimeout(lookTimer)
})

// ── 表单方法 ─────────────────────────────────────────────────
function switchMode(target) {
  if (mode.value === target) return
  isFlipping.value = true
  setTimeout(() => {
    mode.value = target
    isFlipping.value = false
    if (target === 'login') {
      Object.assign(registerForm, { username: '', displayName: '', password: '', confirmPassword: '' })
      Object.assign(registerTouched, { username: false, password: false, confirmPassword: false })
    } else {
      Object.assign(loginForm, { username: '', password: '' })
    }
  }, 150)
}

async function handleLogin() {
  if (!loginForm.username || !loginForm.password) {
    toast.value?.show('请填写用户名和密码', 'error'); return
  }
  loading.value = true
  try {
    const res = await http.post('/api/account/login',
      { username: loginForm.username, password: loginForm.password },
      { timeout: 12000 },
    )
    if (res.success) {
      if (rememberAccount.value) {
        localStorage.setItem('remembered_username', loginForm.username)
      } else {
        localStorage.removeItem('remembered_username')
      }
      localStorage.setItem('user', JSON.stringify(res.data))
      window.electronAPI ? window.electronAPI.loginSuccess() : router.push('/index')
    } else {
      toast.value?.show(res.message || '登录失败，请重试', 'error')
    }
  } catch (err) {
    const isTimeout = err.code === 'ECONNABORTED' || err.message?.includes('timeout')
    toast.value?.show(isTimeout ? '服务器响应超时，请稍后重试' : '网络错误，请重试', 'error')
  } finally { loading.value = false }
}

async function handleRegister() {
  loading.value = true
  try {
    const res = await http.post('/api/account/users', {
      username:     registerForm.username,
      password:     registerForm.password,
      display_name: registerForm.displayName || undefined,
    })
    if (res.success) {
      Object.assign(registerForm, { username: '', displayName: '', password: '', confirmPassword: '' })
      Object.assign(registerTouched, { username: false, password: false, confirmPassword: false })
      switchMode('login')
      setTimeout(() => toast.value?.show('注册成功，请登录', 'success'), 200)
    } else {
      toast.value?.show(res.message || '注册失败', 'error')
    }
  } catch { toast.value?.show('网络错误，请重试', 'error') }
  finally { loading.value = false }
}

function handleForgotPassword() {
  ElMessage({ message: '请联系管理员重置密码。', type: 'info', duration: 3000 })
}

async function handleGuest() {
  loading.value = true
  try {
    const res = await http.get('/api/account/guest')
    if (res.success) {
      localStorage.setItem('user', JSON.stringify(res.data))
      window.electronAPI ? window.electronAPI.loginSuccess() : router.push('/index')
    } else {
      toast.value?.show(res.message || '游客登录失败', 'error')
    }
  } catch {
    toast.value?.show('网络错误，请重试', 'error')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <GToast ref="toast" />

  <div :class="['login-shell', { 'login-shell--web': !isElectron }]">
  <div class="login-page">

    <!-- ── 左侧角色面板（仅宽屏/Web 显示） ───────────────── -->
    <div class="left-panel" aria-hidden="true">
      <!-- 占位（保持 space-between 布局） -->
      <div></div>

      <!-- 角色舞台 -->
      <div class="characters-stage">
        <!-- Purple — 最后层（z=1），高个矩形 -->
        <div
          class="char char-purple"
          ref="purpleRef"
          :style="{
            height: purpleHeight + 'px',
            transform: `skewX(${purplePose.bodySkew + purpleExtraSkew}deg)`,
          }"
        >
          <div
            class="char-face"
            :class="{ blinking: purplePose.blinking }"
            :style="{ transform: `translate(calc(-50% + ${purplePose.faceX}px), ${purplePose.faceY}px)` }"
          >
            <div class="eye">
              <div class="pupil" :style="{ transform: `translate(${purplePose.eyeX}px, ${purplePose.eyeY}px)` }" />
            </div>
            <div class="eye">
              <div class="pupil" :style="{ transform: `translate(${purplePose.eyeX}px, ${purplePose.eyeY}px)` }" />
            </div>
          </div>
        </div>

        <!-- Black — 中层（z=2） -->
        <div
          class="char char-black"
          ref="blackRef"
          :style="{ transform: `skewX(${blackPose.bodySkew}deg)` }"
        >
          <div
            class="char-face"
            :class="{ blinking: blackPose.blinking }"
            :style="{ transform: `translate(calc(-50% + ${blackPose.faceX}px), ${blackPose.faceY}px)` }"
          >
            <div class="eye">
              <div class="pupil" :style="{ transform: `translate(${blackPose.eyeX}px, ${blackPose.eyeY}px)` }" />
            </div>
            <div class="eye">
              <div class="pupil" :style="{ transform: `translate(${blackPose.eyeX}px, ${blackPose.eyeY}px)` }" />
            </div>
          </div>
        </div>

        <!-- Orange — 前左（z=3），半圆，裸瞳孔 -->
        <div
          class="char char-orange"
          ref="orangeRef"
          :style="{ transform: `skewX(${orangePose.bodySkew}deg)` }"
        >
          <div
            class="char-face char-face--bare"
            :style="{ transform: `translate(calc(-50% + ${orangePose.faceX}px), ${orangePose.faceY}px)` }"

          >
            <div class="pupil-bare" :style="{ transform: `translate(${orangePose.eyeX}px, ${orangePose.eyeY}px)` }" />
            <div class="pupil-bare" :style="{ transform: `translate(${orangePose.eyeX}px, ${orangePose.eyeY}px)` }" />
          </div>
        </div>

        <!-- Yellow — 前右（z=4），裸瞳孔 + 嘴巴 -->
        <div
          class="char char-yellow"
          ref="yellowRef"
          :style="{ transform: `skewX(${yellowPose.bodySkew}deg)` }"
        >
          <div
            class="char-face char-face--bare"
            :style="{ transform: `translate(calc(-50% + ${yellowPose.faceX}px), ${yellowPose.faceY}px)` }"
          >
            <div class="pupil-bare" :style="{ transform: `translate(${yellowPose.eyeX}px, ${yellowPose.eyeY}px)` }" />
            <div class="pupil-bare" :style="{ transform: `translate(${yellowPose.eyeX}px, ${yellowPose.eyeY}px)` }" />
          </div>
          <div
            class="char-mouth"
            :style="{ transform: `translateX(calc(-50% + ${yellowPose.faceX * 0.5}px))` }"
          />
        </div>
      </div>

      <!-- 底部装饰文字（每次随机） -->
      <div class="left-footer">
        <span>{{ motto }}</span>
      </div>
    </div>

    <!-- ── 右侧表单面板 ────────────────────────────────── -->
    <div class="right-panel">
      <!-- WindowControls 在 Electron 时浮于右上角（position:fixed，不影响布局） -->
      <WindowControls :show-maximize="false" />

      <!-- 背景装饰圆 -->
      <div class="bg-circle bg-circle-1"></div>
      <div class="bg-circle bg-circle-2"></div>

      <div class="form-wrapper" :class="{ 'is-flipping': isFlipping }">
        <!-- Tab 切换 -->
        <div class="tabs">
          <div class="tab" :class="{ active: mode === 'login' }" @click="switchMode('login')">登录</div>
          <div class="tab" :class="{ active: mode === 'register' }" @click="switchMode('register')">注册</div>
        </div>

        <transition name="fade-slide" mode="out-in">

          <!-- 登录表单 -->
          <div v-if="mode === 'login'" key="login" class="form">
            <div class="field">
              <div class="field-label">
                <span>用户名</span>
                <label class="remember-label">
                  <input v-model="rememberAccount" type="checkbox" class="remember-checkbox" />
                  <span>记住账号</span>
                </label>
              </div>
              <input
                v-model="loginForm.username"
                class="input"
                type="text"
                placeholder="输入用户名"
                @keyup.enter="handleLogin"
                @focus="onInputFocus"
              />
            </div>
            <div class="field">
              <div class="field-label">
                <span>密码</span>
                <span class="link" @click="handleForgotPassword">忘记密码？</span>
              </div>
              <div class="input-with-toggle">
                <input
                  v-model="loginForm.password"
                  class="input"
                  :type="showPassword ? 'text' : 'password'"
                  placeholder="输入密码"
                  @keyup.enter="handleLogin"
                />
                <button
                  type="button"
                  class="toggle-visibility"
                  @click="showPassword = !showPassword"
                  :title="showPassword ? '隐藏密码' : '显示密码'"
                >
                  <el-icon><IconHide v-if="showPassword" /><IconView v-else /></el-icon>
                </button>
              </div>
            </div>
            <button class="btn-primary" :disabled="loading" @click="handleLogin">
              <span v-if="!loading">登 录</span>
              <span v-else class="loading-dot">···</span>
            </button>
            <div class="divider">
              <span class="divider-line"></span>
              <span class="divider-text">或</span>
              <span class="divider-line"></span>
            </div>
            <button class="btn-ghost" :disabled="loading" @click="handleGuest">游客模式进入</button>
          </div>

          <!-- 注册表单 -->
          <div v-else key="register" class="form">
            <div class="field">
              <div class="field-label">用户名 <span class="required">*</span></div>
              <input
                v-model="registerForm.username" class="input"
                :class="{ 'input-error': registerTouched.username && registerErrors.username }"
                type="text" placeholder="输入用户名"
                @blur="registerTouched.username = true"
                @focus="onInputFocus"
              />
              <p v-if="registerTouched.username && registerErrors.username" class="field-error">用户名不能为空</p>
            </div>
            <div class="field">
              <div class="field-label">显示名称</div>
              <input v-model="registerForm.displayName" class="input" type="text" placeholder="可选" />
            </div>
            <div class="field">
              <div class="field-label">密码 <span class="required">*</span></div>
              <input
                v-model="registerForm.password" class="input"
                :class="{ 'input-error': registerTouched.password && registerErrors.password }"
                type="password" placeholder="至少 6 位"
                @blur="registerTouched.password = true"
              />
              <p v-if="registerTouched.password && registerErrors.password" class="field-error">密码至少 6 位</p>
            </div>
            <div class="field">
              <div class="field-label">确认密码 <span class="required">*</span></div>
              <input
                v-model="registerForm.confirmPassword" class="input"
                :class="{ 'input-error': registerErrors.confirmPassword }"
                type="password" placeholder="再次输入密码"
                @blur="registerTouched.confirmPassword = true"
                @keyup.enter="handleRegister"
              />
              <p v-if="registerErrors.confirmPassword" class="field-error">两次密码不一致</p>
            </div>
            <button class="btn-primary" :disabled="loading || !registerValid" @click="handleRegister">
              <span v-if="!loading">注 册</span>
              <span v-else class="loading-dot">···</span>
            </button>
          </div>

        </transition>

        <!-- 页脚 -->
        <div class="card-footer">
          <img src="@/assets/logo.png" class="footer-logo" alt="logo" />
          <span class="footer-name">两平米软件库</span>
          <span class="footer-version">v{{ version }}</span>
        </div>
      </div>
    </div>
  </div>
  </div>

  <!-- 强制更新弹窗 -->
  <UpdateDialog ref="updateDialog" />
</template>

<style scoped>
/* ── Web 居中壳 ───────────────────────────────────────────── */
.login-shell {
  /* Electron：透明壳，不影响布局 */
}
.login-shell--web {
  width: 100vw;
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #d8d0c0;  /* 比卡片背景稍深，衬托卡片 */
  overflow: auto;
}
.login-shell--web .login-page {
  width: 860px;
  height: 640px;
  min-height: unset;
  border-radius: 14px;
  box-shadow: 0 12px 48px rgba(0, 0, 0, 0.18);
  overflow: hidden;
  flex-shrink: 0;
}
.login-shell--web .right-panel {
  min-height: unset;
  height: 100%;
}

/* ── 页面布局 ─────────────────────────────────────────────── */
.login-page {
  width: 100vw;
  min-height: 100vh;
  display: grid;
  grid-template-columns: 1fr 420px;
  overflow: hidden;
  font-family: 'Microsoft YaHei UI', 'Microsoft YaHei', 'PingFang SC', sans-serif;
}

/* ── 左侧面板 ─────────────────────────────────────────────── */
.left-panel {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: space-between;
  padding: 44px 0 36px;
  background: linear-gradient(135deg, #b87830 0%, #c4883a 50%, #a06828 100%);
  overflow: hidden;
  position: relative;
  -webkit-app-region: drag;  /* 左侧整块可拖拽 */
}


.left-footer {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.5);
  letter-spacing: 0.06em;
}

/* ── 角色舞台 ─────────────────────────────────────────────── */
.characters-stage {
  position: relative;
  width: 290px;
  height: 310px;
  flex-shrink: 0;
}

/* 角色基础样式 */
.char {
  position: absolute;
  bottom: 0;
  transform-origin: bottom center;
  will-change: transform;
  transition:
    height 0.5s cubic-bezier(0.34, 1.56, 0.64, 1),
    transform 0.08s linear;
}

/* Purple — z=1，高个矩形 */
.char-purple {
  width: 112px;
  height: 280px;   /* 由 :style 覆盖 */
  background: #6C3FF5;
  border-radius: 8px 8px 0 0;
  z-index: 1;
  left: 35px;
}

/* Black — z=2 */
.char-black {
  width: 78px;
  height: 210px;
  background: #2D2D2D;
  border-radius: 6px 6px 0 0;
  z-index: 2;
  left: 140px;
}

/* Orange — z=3，半圆 */
.char-orange {
  width: 155px;
  height: 135px;
  background: #FF9B6B;
  border-radius: 78px 78px 0 0;
  z-index: 3;
  left: 0;
}

/* Yellow — z=4，前右半椭圆 */
.char-yellow {
  width: 92px;
  height: 155px;
  background: #E8D754;
  border-radius: 46px 46px 0 0;
  z-index: 4;
  left: 200px;
}

/* ── 眼睛（白色眼球 + 瞳孔，用于 Purple/Black） ──────────── */
.char-face {
  position: absolute;
  top: 10%;           /* Purple/Black: 眼睛靠近顶部 */
  left: 50%;
  display: flex;
  gap: 7px;
  will-change: transform;
  /* transform 由 :style 内联控制，含 -50% 居中偏移 */
}

.eye {
  width: 13px;
  height: 13px;
  background: #ffffff;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  transition: transform 0.12s ease;
  flex-shrink: 0;
}

/* 眨眼：scaleY 压扁 */
.blinking .eye {
  transform: scaleY(0.06);
}

.pupil {
  width: 6px;
  height: 6px;
  background: #1a1a1a;
  border-radius: 50%;
  flex-shrink: 0;
  will-change: transform;
}

/* ── 裸瞳孔（Orange/Yellow，无白色眼球） ─────────────────── */
.char-face--bare {
  gap: 11px;
}

/* Orange 半圆：眼睛在圆弧中部 90/190 ≈ 47% */
.char-orange .char-face {
  top: 47%;
}

/* Yellow：眼睛靠近顶部圆弧 40/220 ≈ 18% */
.char-yellow .char-face {
  top: 18%;
}

.pupil-bare {
  width: 8px;
  height: 8px;
  background: #1a1a1a;
  border-radius: 50%;
  flex-shrink: 0;
  will-change: transform;
}

/* Yellow 嘴巴：88/220 ≈ 40% from top */
.char-mouth {
  position: absolute;
  width: 35px;
  height: 3px;
  background: rgba(0, 0, 0, 0.28);
  border-radius: 2px;
  top: 40%;
  left: 50%;
  transform: translateX(-50%);
  will-change: transform;
}

/* ── 右侧面板 ─────────────────────────────────────────────── */
.right-panel {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  background: var(--bg);
  overflow: hidden;
}

/* 背景装饰圆（移自原 .login-page） */
.bg-circle { position: absolute; border-radius: 50%; pointer-events: none; }
.bg-circle-1 {
  width: 500px; height: 500px;
  background: radial-gradient(circle, rgba(196,136,58,0.1) 0%, transparent 70%);
  top: -130px; right: -100px;
}
.bg-circle-2 {
  width: 380px; height: 380px;
  background: radial-gradient(circle, rgba(160,100,40,0.07) 0%, transparent 70%);
  bottom: -80px; left: -70px;
}

/* ── 表单容器（原 .card） ────────────────────────────────── */
.form-wrapper {
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: 340px;
  display: flex;
  flex-direction: column;
  padding: 44px 40px 20px;
  animation: card-in 0.5s cubic-bezier(0.16, 1, 0.3, 1) both;
}
@keyframes card-in {
  from { opacity: 0; transform: translateY(16px); }
  to   { opacity: 1; transform: translateY(0); }
}
.form-wrapper.is-flipping { pointer-events: none; }

/* ── Tab 切换 ─────────────────────────────────────────────── */
.tabs {
  display: flex;
  border-bottom: 1.5px solid var(--border);
  margin-bottom: 24px;
  gap: 24px;
}
.tab {
  padding-bottom: 10px;
  font-size: 14px;
  color: var(--text-muted);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -1.5px;
  font-weight: 500;
  letter-spacing: 0.03em;
  transition: all 0.2s;
  user-select: none;
}
.tab.active { color: var(--text-primary); border-bottom-color: var(--accent); }

/* ── 表单字段 ─────────────────────────────────────────────── */
.form { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.field { margin-bottom: 14px; }
.field-label {
  font-size: 11px;
  color: var(--text-muted);
  letter-spacing: 0.08em;
  margin-bottom: 6px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.required { color: var(--accent); }

.link {
  font-size: 11px;
  color: var(--text-muted);
  cursor: pointer;
  transition: color 0.2s;
  letter-spacing: 0;
}
.link:hover { color: var(--accent); }

.input {
  width: 100%;
  background: var(--accent-bg);
  border: 1.5px solid var(--border);
  border-radius: 10px;
  padding: 11px 14px;
  font-size: 14px;
  color: var(--text-primary);
  font-family: inherit;
  outline: none;
  transition: all 0.2s;
  box-sizing: border-box;
}
.input:focus {
  border-color: var(--accent);
  background: var(--bg-card);
  box-shadow: 0 0 0 3px rgba(196,136,58,0.1);
}
.input::placeholder { color: var(--text-muted); opacity: 0.55; }
.input-error {
  border-color: #d07060 !important;
  background: #fff8f6 !important;
  box-shadow: 0 0 0 3px rgba(208,112,96,0.1) !important;
}
.field-error { font-size: 11px; color: #c05040; margin-top: 5px; padding-left: 2px; }

/* 密码显示切换 */
.input-with-toggle {
  position: relative;
  display: flex;
  align-items: center;
}
.input-with-toggle .input {
  padding-right: 44px;
}
.toggle-visibility {
  position: absolute;
  right: 10px;
  background: none;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  padding: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  transition: color 0.2s;
  font-size: 15px;
}
.toggle-visibility:hover { color: var(--accent); }

/* ── 按钮 ─────────────────────────────────────────────────── */
.btn-primary {
  width: 100%;
  padding: 12px;
  background: linear-gradient(135deg, var(--accent), var(--accent-hover));
  border: none;
  border-radius: 10px;
  color: #fff;
  font-size: 13px;
  font-family: inherit;
  font-weight: 600;
  letter-spacing: 0.1em;
  cursor: pointer;
  margin-top: 4px;
  box-shadow: 0 4px 14px rgba(196,136,58,0.28);
  transition: all 0.2s;
}
.btn-primary:hover:not(:disabled) {
  opacity: 0.92;
  transform: translateY(-1px);
  box-shadow: 0 6px 20px rgba(196,136,58,0.35);
}
.btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }

.btn-ghost {
  width: 100%;
  padding: 11px;
  background: transparent;
  border: 1.5px solid var(--border);
  border-radius: 10px;
  color: var(--text-muted);
  font-size: 13px;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.2s;
  letter-spacing: 0.03em;
}
.btn-ghost:hover { border-color: var(--accent); color: var(--accent); background: rgba(196,136,58,0.04); }

/* ── 分隔线 ───────────────────────────────────────────────── */
.divider { display: flex; align-items: center; gap: 12px; margin: 14px 0; }
.divider-line { flex: 1; height: 1px; background: var(--border); }
.divider-text { font-size: 12px; color: var(--text-muted); }

/* ── 页脚 ─────────────────────────────────────────────────── */
.card-footer {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  margin-top: auto;
  padding-top: 20px;
}
.footer-logo { width: 30px; height: 30px; object-fit: contain; opacity: 0.35; }
.footer-name { font-size: 12px; color: var(--text-muted); letter-spacing: 0.12em; }
.footer-version {
  font-size: 11px; color: var(--text-muted);
  background: var(--accent-bg); border: 1px solid var(--border);
  border-radius: 4px; padding: 1px 6px; opacity: 0.7;
}

/* ── 辅助组件样式 ─────────────────────────────────────────── */
.remember-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-muted);
  cursor: pointer;
  user-select: none;
}
.remember-checkbox {
  width: 14px;
  height: 14px;
  accent-color: var(--accent);
  cursor: pointer;
}

.loading-dot { display: inline-block; animation: blink 1s infinite; letter-spacing: 0.2em; }
@keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }

.fade-slide-enter-active, .fade-slide-leave-active { transition: all 0.15s ease; }
.fade-slide-enter-from { opacity: 0; transform: translateY(8px); }
.fade-slide-leave-to   { opacity: 0; transform: translateY(-8px); }

/* ── 超窄屏回退（≤599px） ────────────────────────────────── */
@media (max-width: 599px) {
  .login-page {
    grid-template-columns: 1fr;
  }
  .left-panel {
    display: none;
  }
  .right-panel {
    min-height: 100vh;
  }
  .form-wrapper {
    max-width: 100%;
    padding: 44px 32px 20px;
  }
}
</style>
