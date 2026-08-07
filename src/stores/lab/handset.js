// 模拟手控系统：手控器屏幕状态机 + 外部环境状态（联网/过热/身份等）
// 屏幕导航逻辑收敛在一个状态机里，不采用"每个界面自己维护显示/隐藏"的写法，
// 后续新增界面（锁定/设置/记忆位/轮播）只需往 SCREEN_TRANSITIONS 里加节点和事件。
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useFSM } from '@/composables/useFSM'

// ── 屏幕状态机 ──────────────────────────────────────
// black: 黑屏（未唤醒）  main: 主页  settings: 设置页  settingsDetail: 设置子页
const SCREEN_TRANSITIONS = {
  black: { WAKE: 'main' },
  main:  { SLEEP: 'black', SETTINGS: 'settings', AMBIENT: 'ambient' },
  ambient: { SLEEP: 'black', HOME: 'main' },
  settings: { SLEEP: 'black', HOME: 'main', DETAIL: 'settingsDetail' },
  settingsDetail: { SLEEP: 'black', BACK: 'settings' },
}

export const useLabHandsetStore = defineStore('lab/handset', () => {
  const { state: screenState, send: sendScreen } = useFSM(SCREEN_TRANSITIONS, 'black')
  const settingsPage = ref(0)
  const settingsPageCount = 2
  const settingsDetail = ref(null)
  const navigationStack = ref([])

  // ── 常驻持久状态 ─────────────────────────────────
  // WiFi 始终显示在线/离线；通知与过热只在激活时显示在状态栏。
  const network   = ref(true)
  const overheat  = ref(false)
  const reminder  = ref(false)   // 铃铛提醒状态
  const locked = ref(false) // 锁定时保留界面导航，仅禁止桌面运动与场景操作

  // ── 触发型状态 ───────────────────────────────────
  // 遇阻仅允许在升降或倾斜运动中触发；故障不依赖运动状态。
  // 由屏幕的升降/倾斜操作写入，控制面板不再提供人工选择
  const motionMode = ref('idle')  // idle | lift | tilt
  const obstruction = ref(false)
  const fault = ref(false)

  // ── 设备数据与外设 ───────────────────────────────
  const deskHeightMm = ref(1000)  // 内部以 mm 保存，避免长按累计时丢失精度
  const tiltAngleRaw = ref(15)    // 内部保留小数精度，界面显示整数度
  const ambientOn  = ref(false)   // 氛围灯，默认不亮
  const ambientPresets = ref([
    { id: 'focus', name: '专注', color: '#f4d6a1', brightness: 65, effect: '常亮' },
    { id: 'relax', name: '放松', color: '#ffae78', brightness: 35, effect: '呼吸' },
    { id: 'immerse', name: '沉浸', color: '#798cff', brightness: 48, effect: '渐变' },
  ])
  const ambientPresetId = ref('focus')
  const heightDirection = ref(null) // up | down | null
  const tiltDirection = ref(null)   // up | down | null

  // 屏幕主题先提供状态接口，后续由设置页切换；当前默认白色方案。
  const colorScheme = ref('light') // light | dark

  // ── 场景：名称与图标后续由小程序扩展，手控器仅消费前三个和绑定数据。 ──
  const scenes = ref([
    { id: 'study', name: '学习', icon: 'study', posture: 'sit', binding: null, ambientPresetId: null },
    { id: 'work', name: '工作', icon: 'work', posture: 'stand', binding: null, ambientPresetId: null },
    { id: 'series', name: '追剧', icon: 'series', posture: 'sit', binding: null, ambientPresetId: null },
    { id: 'game', name: '游戏', icon: 'game', posture: 'stand', binding: null, ambientPresetId: null },
  ])
  const boundScenes = computed(() => scenes.value.filter(scene => scene.binding))
  function bindScene(id, posture = null) {
    const scene = scenes.value.find(item => item.id === id)
    if (!scene) return false
    if (posture !== null) scene.posture = posture
    scene.binding = { height: deskHeight.value, tilt: tiltAngle.value }
    return true
  }
  function setScenePosture(id, posture) {
    const scene = scenes.value.find(item => item.id === id)
    if (!scene || !['sit', 'stand', 'none'].includes(posture)) return false
    scene.posture = posture
    return true
  }

  // ── 身份 ────────────────────────────────────────
  const users = ref([
    { id: 'user-mizai', name: '米仔', avatar: 'sky', wechat: 'mizai_88' },
    { id: 'user-laowang', name: '老王', avatar: 'moss', wechat: null },
    { id: 'user-aya', name: '阿雅', avatar: 'coral', wechat: null },
  ])
  const currentUser   = ref(users.value[0].id) // 当前登录用户 id
  const pendingNfcUser = ref(users.value[0].id) // 按键面板中选中的、待通过 NFC 碰触生效的身份
  const currentUserProfile = computed(() => users.value.find(user => user.id === currentUser.value) || null)
  const currentUserName = computed(() => currentUserProfile.value?.name || '')

  // ── 模拟时钟（供手控器内所有计时逻辑共享）──────────
  const timeSpeed = ref(1)
  const simulatedTimestamp = ref(Date.now())
  const lastInteractionTimestamp = ref(simulatedTimestamp.value)
  let lastClockRealMs = Date.now()

  const isAwake = computed(() => screenState.value !== 'black')
  const isSettings = computed(() => screenState.value === 'settings')
  const isSettingsDetail = computed(() => screenState.value === 'settingsDetail')
  const isAmbientControl = computed(() => screenState.value === 'ambient')
  const activeAmbientPreset = computed(() => ambientPresets.value.find(item => item.id === ambientPresetId.value) || ambientPresets.value[0])
  const canTriggerObstruction = computed(() => motionMode.value !== 'idle')
  const deskHeight = computed(() => Math.round(deskHeightMm.value / 10))
  const tiltAngle = computed(() => Math.round(tiltAngleRaw.value))
  const isHeightHolding = computed(() => heightDirection.value !== null)
  const heightLimitState = computed(() => {
    if (heightDirection.value === 'up' && deskHeightMm.value >= 1200) return 'max'
    if (heightDirection.value === 'down' && deskHeightMm.value <= 650) return 'min'
    return null
  })
  const isHeightMoving = computed(() => isHeightHolding.value && !heightLimitState.value)
  const isTiltHolding = computed(() => tiltDirection.value !== null)
  const tiltLimitState = computed(() => {
    if (tiltDirection.value === 'up' && tiltAngleRaw.value >= 15) return 'max'
    if (tiltDirection.value === 'down' && tiltAngleRaw.value <= 0) return 'min'
    return null
  })
  const isTiltMoving = computed(() => isTiltHolding.value && !tiltLimitState.value)

  function togglePower() {
    if (screenState.value !== 'black') {
      sleepToHome()
      return true
    }
    markInteraction()
    return sendScreen('WAKE')
  }
  function markInteraction() {
    tickClock()
    lastInteractionTimestamp.value = simulatedTimestamp.value
  }
  function sleepToHome() {
    stopHeightMotion()
    stopTiltMotion()
    settingsPage.value = 0
    settingsDetail.value = null
    navigationStack.value = []
    if (screenState.value !== 'black') screenState.value = 'black'
    markInteraction()
  }
  function navigateScreen(direction) {
    if (!isAwake.value) return false
    markInteraction()
    if (screenState.value === 'main' && direction === 'down') return sendScreen('SETTINGS')
    if (screenState.value === 'main' && direction === 'up') return sendScreen('AMBIENT')
    if (screenState.value === 'ambient' && direction === 'down') return sendScreen('HOME')
    if (screenState.value === 'settingsDetail' && direction === 'up') return goBack()
    if (screenState.value !== 'settings') return false
    if (direction === 'up') return sendScreen('HOME')
    if (direction === 'left') {
      settingsPage.value = (settingsPage.value - 1 + settingsPageCount) % settingsPageCount
      return true
    }
    if (direction === 'right') {
      settingsPage.value = (settingsPage.value + 1) % settingsPageCount
      return true
    }
    return false
  }
  function openSettingsDetail(item) {
    if (screenState.value !== 'settings' || !item) return false
    markInteraction()
    navigationStack.value.push({ screen: screenState.value, settingsPage: settingsPage.value })
    settingsDetail.value = item
    return sendScreen('DETAIL')
  }
  function goBack() {
    const previous = navigationStack.value.pop()
    if (!previous) return false
    settingsPage.value = previous.settingsPage ?? 0
    settingsDetail.value = null
    screenState.value = previous.screen
    markInteraction()
    return true
  }
  function toggleNetwork()  { network.value = !network.value }
  function toggleOverheat() { overheat.value = !overheat.value }
  function toggleReminder() { reminder.value = !reminder.value }
  function toggleAmbient()  { ambientOn.value = !ambientOn.value }
  function applyAmbientPreset(id) {
    if (!ambientPresets.value.some(item => item.id === id)) return false
    ambientPresetId.value = id
    ambientOn.value = true
    markInteraction()
    return true
  }
  function updateAmbientPreset(id, changes) {
    const preset = ambientPresets.value.find(item => item.id === id)
    if (!preset) return false
    if (typeof changes.color === 'string') preset.color = changes.color
    if ([20, 40, 65, 85, 100].includes(changes.brightness)) preset.brightness = changes.brightness
    if (['常亮', '呼吸', '渐变'].includes(changes.effect)) preset.effect = changes.effect
    return true
  }
  function setSceneAmbientPreset(sceneId, presetId) {
    const scene = scenes.value.find(item => item.id === sceneId)
    if (!scene || (presetId !== null && !ambientPresets.value.some(item => item.id === presetId))) return false
    scene.ambientPresetId = presetId
    return true
  }
  function setColorScheme(scheme) {
    if (!['light', 'dark'].includes(scheme)) return false
    colorScheme.value = scheme
    return true
  }
  function setMotionMode(mode) {
    if (!['idle', 'lift', 'tilt'].includes(mode)) return false
    motionMode.value = mode
    obstruction.value = false
    return true
  }
  function toggleObstruction() {
    if (!canTriggerObstruction.value) return false
    obstruction.value = !obstruction.value
    return true
  }
  function toggleFault() {
    fault.value = !fault.value
    return true
  }

  function startHeightMotion(direction) {
    if (!isAwake.value || locked.value || !['up', 'down'].includes(direction)) return false
    markInteraction()
    stopTiltMotion()
    heightDirection.value = direction
    setMotionMode(heightLimitState.value ? 'idle' : 'lift')
    return true
  }

  // deltaMm 为本帧应移动的绝对毫米数；行程固定在 650–1200 mm。
  function advanceHeight(deltaMm) {
    if (!heightDirection.value || !Number.isFinite(deltaMm) || deltaMm <= 0) return false
    const signedDelta = heightDirection.value === 'up' ? deltaMm : -deltaMm
    deskHeightMm.value = Math.min(1200, Math.max(650, deskHeightMm.value + signedDelta))
    const reachedLimit = heightDirection.value === 'up'
      ? deskHeightMm.value >= 1200
      : deskHeightMm.value <= 650
    // 到达极限只停止电机运动，保留按住状态和极限界面直到用户松手。
    if (reachedLimit && motionMode.value === 'lift') setMotionMode('idle')
    return true
  }

  function stopHeightMotion() {
    heightDirection.value = null
    if (motionMode.value === 'lift') setMotionMode('idle')
  }

  function startTiltMotion(direction) {
    if (!isAwake.value || locked.value || !['up', 'down'].includes(direction)) return false
    markInteraction()
    stopHeightMotion()
    tiltDirection.value = direction
    setMotionMode(tiltLimitState.value ? 'idle' : 'tilt')
    return true
  }

  function advanceTilt(deltaDegrees) {
    if (!tiltDirection.value || !Number.isFinite(deltaDegrees) || deltaDegrees <= 0) return false
    const signedDelta = tiltDirection.value === 'up' ? deltaDegrees : -deltaDegrees
    tiltAngleRaw.value = Math.min(15, Math.max(0, tiltAngleRaw.value + signedDelta))
    const reachedLimit = tiltDirection.value === 'up'
      ? tiltAngleRaw.value >= 15
      : tiltAngleRaw.value <= 0
    if (reachedLimit && motionMode.value === 'tilt') setMotionMode('idle')
    return true
  }

  function stopTiltMotion() {
    tiltDirection.value = null
    if (motionMode.value === 'tilt') setMotionMode('idle')
  }
  function setPendingNfcUser(id) {
    if (!users.value.some(user => user.id === id)) return false
    pendingNfcUser.value = id
    return true
  }
  function setCurrentUser(id) {
    if (!users.value.some(user => user.id === id)) return false
    currentUser.value = id
    markInteraction()
    return true
  }
  function addUser({ name, avatar }) {
    if (users.value.length >= 6 || !name?.trim()) return false
    const id = `user-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`
    users.value.push({ id, name: name.trim().slice(0, 8), avatar: avatar || 'sky', wechat: null })
    return id
  }
  function updateUser(id, { name, avatar }) {
    const user = users.value.find(item => item.id === id)
    if (!user || !name?.trim()) return false
    user.name = name.trim().slice(0, 8)
    user.avatar = avatar || user.avatar
    return true
  }
  function deleteUser(id) {
    if (users.value.length <= 1) return false
    const index = users.value.findIndex(user => user.id === id)
    if (index < 0) return false
    users.value.splice(index, 1)
    if (currentUser.value === id) currentUser.value = null
    if (pendingNfcUser.value === id) pendingNfcUser.value = users.value[0]?.id || null
    return true
  }

  // 模拟 NFC 碰触：仅在屏幕唤醒状态下生效
  function triggerNfc() {
    if (!isAwake.value) return false
    markInteraction()
    currentUser.value = pendingNfcUser.value
    return true
  }

  function tickClock(realNow = Date.now()) {
    const elapsedRealMs = Math.max(0, realNow - lastClockRealMs)
    simulatedTimestamp.value += elapsedRealMs * timeSpeed.value
    lastClockRealMs = realNow
  }

  function setTimeSpeed(v) {
    if (![1, 2, 3, 5, 20, 60].includes(v)) return false
    tickClock()
    timeSpeed.value = v
    return true
  }
  function setLocked(value) {
    locked.value = Boolean(value)
    if (locked.value) {
      stopHeightMotion()
      stopTiltMotion()
    }
  }

  function resetAll() {
    stopHeightMotion()
    stopTiltMotion()
    screenState.value = 'black'
    settingsPage.value = 0
    settingsDetail.value = null
    navigationStack.value = []
    network.value = true
    overheat.value = false
    reminder.value = false
    locked.value = false
    motionMode.value = 'idle'
    obstruction.value = false
    fault.value = false
    deskHeightMm.value = 1000
    tiltAngleRaw.value = 15
    ambientOn.value = false
    ambientPresetId.value = 'focus'
    colorScheme.value = 'light'
    users.value = [
      { id: 'user-mizai', name: '米仔', avatar: 'sky', wechat: 'mizai_88' },
      { id: 'user-laowang', name: '老王', avatar: 'moss', wechat: null },
      { id: 'user-aya', name: '阿雅', avatar: 'coral', wechat: null },
    ]
    currentUser.value = users.value[0].id
    pendingNfcUser.value = users.value[0].id
    timeSpeed.value = 1
    simulatedTimestamp.value = Date.now()
    lastClockRealMs = Date.now()
    lastInteractionTimestamp.value = simulatedTimestamp.value
  }

  return {
    screenState, isAwake, isSettings, isSettingsDetail, isAmbientControl, settingsPage, settingsPageCount, settingsDetail, navigationStack, lastInteractionTimestamp,
    network, overheat, reminder, locked,
    motionMode, obstruction, fault, canTriggerObstruction,
    deskHeight, deskHeightMm, tiltAngle, tiltAngleRaw, ambientOn, ambientPresets, ambientPresetId, activeAmbientPreset,
    heightDirection, isHeightHolding, isHeightMoving, heightLimitState, colorScheme,
    tiltDirection, isTiltHolding, isTiltMoving, tiltLimitState,
    users, currentUser, currentUserProfile, currentUserName, pendingNfcUser,
    scenes, boundScenes,
    timeSpeed, simulatedTimestamp,
    togglePower, sleepToHome, markInteraction, navigateScreen, openSettingsDetail, goBack, toggleNetwork, toggleOverheat, toggleReminder, toggleAmbient, applyAmbientPreset, updateAmbientPreset, setSceneAmbientPreset,
    setMotionMode, toggleObstruction, toggleFault, setLocked,
    startHeightMotion, advanceHeight, stopHeightMotion, setColorScheme,
    startTiltMotion, advanceTilt, stopTiltMotion,
    setPendingNfcUser, setCurrentUser, addUser, updateUser, deleteUser, triggerNfc, setTimeSpeed, tickClock, resetAll,
    bindScene, setScenePosture,
  }
})
