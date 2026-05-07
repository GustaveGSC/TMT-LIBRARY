<template>
  <GToast ref="toast" />

  <div class="login-page">
    <div class="bg-circle bg-circle-1"></div>
    <div class="bg-circle bg-circle-2"></div>

    <WindowControls :show-maximize="false" />

    <div class="card" :class="{ 'is-flipping': isFlipping }">
      <div class="tabs">
        <div class="tab" :class="{ active: mode === 'login' }" @click="switchMode('login')">登录</div>
        <div class="tab" :class="{ active: mode === 'register' }" @click="switchMode('register')">注册</div>
      </div>

      <transition name="fade-slide" mode="out-in">

        <div v-if="mode === 'login'" key="login" class="form">
          <div class="field">
            <div class="field-label">
              <span>用户名</span>
              <label class="remember-label">
                <input v-model="rememberAccount" type="checkbox" class="remember-checkbox" />
                <span>记住账号</span>
              </label>
            </div>
            <input v-model="loginForm.username" class="input" type="text" placeholder="输入用户名" @keyup.enter="handleLogin" />
          </div>
          <div class="field">
            <div class="field-label">
              <span>密码</span>
              <span class="link" @click="handleForgotPassword">忘记密码？</span>
            </div>
            <input v-model="loginForm.password" class="input" type="password" placeholder="输入密码" @keyup.enter="handleLogin" />
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

        <div v-else key="register" class="form">
          <div class="field">
            <div class="field-label">用户名 <span class="required">*</span></div>
            <input
              v-model="registerForm.username" class="input"
              :class="{ 'input-error': registerTouched.username && registerErrors.username }"
              type="text" placeholder="输入用户名"
              @blur="registerTouched.username = true"
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

      <div class="card-footer">
        <img src="@/assets/logo.png" class="footer-logo" alt="logo" />
        <span class="footer-name">两平米软件库</span>
        <span class="footer-version">v{{ version }}</span>
      </div>
    </div>
  </div>

  <!-- 强制更新弹窗（与主页同一套 electron-updater 逻辑） -->
  <UpdateDialog ref="updateDialog" />
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { checkUpdateType } from '@/utils/version'
import http from '@/api/http'
import GToast from '@/components/common/GToast.vue'
import WindowControls from '@/components/common/WindowControls.vue'
import UpdateDialog from '@/components/update/UpdateDialog.vue'

const router = useRouter()
const toast  = ref(null)
const updateDialog = ref(null)
const mode       = ref('login')
const loading    = ref(false)
const isFlipping = ref(false)
const version    = ref('1.0.0')

window.electronAPI?.getVersion().then(v => { version.value = v })

const rememberAccount = ref(localStorage.getItem('remembered_username') !== null)
const loginForm    = reactive({
  username: localStorage.getItem('remembered_username') ?? '',
  password: '',
})
const registerForm = reactive({ username: '', displayName: '', password: '', confirmPassword: '' })
const registerTouched = reactive({ username: false, password: false, confirmPassword: false })

const registerErrors = computed(() => ({
  username:        !registerForm.username.trim(),
  password:        registerForm.password.length > 0 && registerForm.password.length < 6,
  confirmPassword: registerForm.confirmPassword.length > 0 && registerForm.confirmPassword !== registerForm.password
}))

const registerValid = computed(() =>
  registerForm.username.trim() &&
  registerForm.password.length >= 6 &&
  registerForm.password === registerForm.confirmPassword
)

onMounted(async () => {
  if (window.electronAPI) {
    version.value = await window.electronAPI.getVersion()
  }

  try {
    const res = await http.get('/api/version/latest')
    if (res.success && res.data) {
      const type = checkUpdateType(version.value, res.data.version)
      if (type === 'force') {
        await window.electronAPI?.updater.check()
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

<style scoped>
.login-page {
  width: 100vw;
  height: 100vh;
  background: var(--bg);
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
  font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

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

.card {
  width: 100%; height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--bg-card);
  padding: 44px 48px 20px;
  animation: card-in 0.5s cubic-bezier(0.16, 1, 0.3, 1) both;
}
@keyframes card-in {
  from { opacity: 0; transform: translateY(16px); }
  to   { opacity: 1; transform: translateY(0); }
}
.card.is-flipping { pointer-events: none; }

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

.divider { display: flex; align-items: center; gap: 12px; margin: 14px 0; }
.divider-line { flex: 1; height: 1px; background: var(--border); }
.divider-text { font-size: 12px; color: var(--text-muted); }

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

</style>