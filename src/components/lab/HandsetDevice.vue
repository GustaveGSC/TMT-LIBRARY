<script setup>
// 手控器外壳：外形尺寸 110×44mm，屏幕 40.8×30.6mm / 320×240px
// 两者比例一致（4:3），按 320px/40.8mm 换算得到外壳固定像素尺寸；
// 外壳与屏幕尺寸均为写死常量，不提供可调整入口，仅整体用 CSS transform 缩放显示。
import { Icon } from '@iconify/vue'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Swiper, SwiperSlide } from 'swiper/vue'
import 'swiper/css'
import { useLabHandsetStore } from '@/stores/lab/handset'
import { handsetIcons } from './handsetIconify'
import deskHomeImage from '@/assets/lab/desk-home.png'

const props = defineProps({
  uiScale: { type: Number, default: 1 },
})

const store = useLabHandsetStore()
const swipeDirection = ref('')
const homePage = ref(0)
const customHomeItems = ref([])
const customHomePickerOpen = ref(false)
const fromCustomHome = ref(false)
const settingsSwiper = ref(null)
const userManagerView = ref('list')
const userListPage = ref(0)
const userListSwiper = ref(null)
const sceneListSwiper = ref(null)
const sceneListPage = ref(0)
const sceneManagerView = ref('list')
const selectedSceneId = ref(null)
const ambientManagerView = ref('list')
const selectedAmbientPresetId = ref(null)
let sceneHoldTimer = null
const editingUserId = ref(null)
const selectedUserId = ref(null)
const userForm = ref({ avatar: 'sky', name: '晴朗星' })
const longPressActive = ref(false)
let userHoldTimer = null
const sceneBindingMode = ref(false)
const sceneBindStep = ref('select')
const pendingSceneId = ref(null)
let deskHoldTimer = null
let deskHoldStart = null
let deskLockTimer = null
let deskHoldFrame = null
const deskHoldProgress = ref(0)
const deskHoldActive = ref(false)
const lockFeedbackVisible = ref(false)
const deviceNotice = ref('')
let lockFeedbackTimer = null
let deviceNoticeTimer = null
let quickSceneHoldTimer = null
let sceneTravelFrame = null
const quickSceneLongPress = ref(false)
const AVATAR_OPTIONS = ['sky', 'moss', 'coral', 'violet']
const NAME_PARTS_A = ['晴朗', '轻风', '暖阳', '星河', '森林', '海盐', '晨雾', '云朵']
const NAME_PARTS_B = ['星', '熊', '芽', '月', '兔', '树', '鲸', '石']
const sceneBindingButtons = computed(() => {
  const bound = store.boundScenes.slice(0, 3)
  return [...bound, ...Array(Math.max(0, 3 - bound.length)).fill(null).map((_, index) => ({ id: `add-${index}`, isAdd: true })), { id: 'more', isMore: true }]
})
const unboundScenePages = computed(() => {
  const scenes = store.scenes.filter(scene => !scene.binding)
  return Array.from({ length: Math.max(1, Math.ceil(scenes.length / 3)) }, (_, page) => scenes.slice(page * 3, page * 3 + 3))
})
const userSlots = computed(() => store.users.length < 6 ? [...store.users, { id: 'user-add', isAdd: true }] : [...store.users])
const userListPages = computed(() => Math.max(1, Math.ceil(userSlots.value.length / 3)))
const userPages = computed(() => Array.from({ length: userListPages.value }, (_, page) => userSlots.value.slice(page * 3, page * 3 + 3)))
const scenePages = computed(() => Array.from({ length: Math.ceil(store.scenes.length / 3) }, (_, page) => store.scenes.slice(page * 3, page * 3 + 3)))
const SETTINGS_PAGES = [
  [
    { label: '用户管理', icon: handsetIcons.settingsUsers },
    { label: '场景管理', icon: handsetIcons.settingsScenes },
    { label: '健康管理', icon: handsetIcons.settingsHealth },
  ],
  [
    { label: '氛围灯管理', icon: handsetIcons.settingsLight },
    { label: '提醒管理', icon: handsetIcons.settingsReminder },
    { label: '关于本机', icon: handsetIcons.settingsAbout },
  ],
]
const activeSettingsPage = computed(() => SETTINGS_PAGES[store.settingsPage])
const customHomeOptions = computed(() => SETTINGS_PAGES.flat())
const homePageCount = computed(() => 3 + customHomeItems.value.length)
const activeShortcutItem = computed(() => customHomeItems.value[homePage.value - 2] || null)
const isShortcutDetail = computed(() => store.screenState === 'main' && Boolean(activeShortcutItem.value))
const isDetailScreen = computed(() => store.isSettingsDetail || isShortcutDetail.value)
const activeDetail = computed(() => store.settingsDetail || activeShortcutItem.value)
const weeklyPosture = [42, 36, 58, 31, 47, 61, 33]
function prepareFeatureView(item) {
  if (item?.label === '用户管理') openUserManager()
  if (item?.label === '场景管理') { sceneManagerView.value = 'list'; selectedSceneId.value = null; sceneListPage.value = 0 }
  if (item?.label === '氛围灯管理') { ambientManagerView.value = 'list'; selectedAmbientPresetId.value = null }
}
function pinHomeItem(item) {
  prepareFeatureView(item)
  customHomeItems.value.push(item)
  customHomePickerOpen.value = false
  fromCustomHome.value = true
  homePage.value = 2 + customHomeItems.value.length - 1
}
function deletePinnedHomeItem() {
  const index = homePage.value - 2
  if (!fromCustomHome.value || index < 0 || activeDetail.value?.label !== customHomeItems.value[index]?.label) return
  customHomeItems.value.splice(index, 1)
  fromCustomHome.value = false
  homePage.value = 2 + customHomeItems.value.length
}
const handsetMotionStyle = computed(() => ({
  '--screen-swipe-duration': `${0.4 / store.timeSpeed}s`,
  '--screen-page-duration': `${0.28 / store.timeSpeed}s`,
  '--screen-pulse-duration': `${1 / store.timeSpeed}s`,
  '--screen-travel-duration': `${1.05 / store.timeSpeed}s`,
  '--screen-feedback-duration': `${0.18 / store.timeSpeed}s`,
}))
let swipeTimer = null
let heightFrame = null
let heightFrameTime = 0
let heightHoldTimer = null
let heightHoldStart = null
let tiltHoldTimer = null
let tiltHoldStart = null
const HEIGHT_SPEED_MM_PER_SECOND = 38
const TILT_SPEED_DEGREES_PER_SECOND = 3
const INACTIVITY_TIMEOUT_MS = 30_000
let tiltFrame = null
let tiltFrameTime = 0
let inactivityTimer = null
const screenSwipeStart = ref(null)

const handsetZoomStyle = computed(() => ({ '--ui-scale': props.uiScale }))

watch(() => store.screenState, state => {
  if (state === 'black' || state === 'main') {
    if (state === 'main') homePage.value = 0
    fromCustomHome.value = false
    sceneBindingMode.value = false
    sceneBindStep.value = 'select'
    pendingSceneId.value = null
  }
})

function onScreenClick() {
  store.markInteraction()
  if (store.screenState === 'black') store.togglePower()
}

function onNfcClick() {
  store.markInteraction()
  store.triggerNfc()
}
function showLockFeedback() {
  lockFeedbackVisible.value = false
  requestAnimationFrame(() => { lockFeedbackVisible.value = true })
  clearTimeout(lockFeedbackTimer)
  lockFeedbackTimer = setTimeout(() => { lockFeedbackVisible.value = false }, 760 / store.timeSpeed)
}
function showDeviceNotice(message) {
  deviceNotice.value = message
  clearTimeout(deviceNoticeTimer)
  deviceNoticeTimer = setTimeout(() => { deviceNotice.value = '' }, 1800 / store.timeSpeed)
}
function toggleDeskLock() {
  const nextLocked = !store.locked
  store.setLocked(nextLocked)
  sceneBindingMode.value = false
  showDeviceNotice(nextLocked ? '已锁定桌面操控' : '已解除桌面锁定')
}
function updateDeskHoldProgress(startedAt, duration) {
  const tick = now => {
    deskHoldProgress.value = Math.min(1, (now - startedAt) / duration)
    if (deskHoldProgress.value < 1 && deskHoldStart) deskHoldFrame = requestAnimationFrame(tick)
  }
  deskHoldFrame = requestAnimationFrame(tick)
}
function startDeskHold(event) {
  if (event.pointerType === 'mouse' && event.button !== 0) return
  try { event.currentTarget?.setPointerCapture?.(event.pointerId) } catch { /* 触屏浏览器不支持时仍按正常长按处理 */ }
  deskHoldStart = { x: event.clientX, y: event.clientY }
  deskHoldActive.value = false
  deskHoldProgress.value = 0
  const holdDuration = 3000 / store.timeSpeed
  updateDeskHoldProgress(performance.now(), holdDuration)
  clearTimeout(deskHoldTimer)
  clearTimeout(deskLockTimer)
  deskHoldTimer = setTimeout(() => {
    deskHoldActive.value = true
    if (!store.locked) { sceneBindingMode.value = true; sceneBindStep.value = 'select' }
  }, 500 / store.timeSpeed)
  deskLockTimer = setTimeout(() => { toggleDeskLock(); stopDeskHold() }, holdDuration)
}
function cancelDeskHoldOnMove(event) {
  if (!deskHoldStart) return
  if (Math.hypot(event.clientX - deskHoldStart.x, event.clientY - deskHoldStart.y) > 12) stopDeskHold()
}
function stopDeskHold(event) {
  clearTimeout(deskHoldTimer)
  clearTimeout(deskLockTimer)
  cancelAnimationFrame(deskHoldFrame)
  deskHoldFrame = null
  deskHoldStart = null
  deskHoldActive.value = false
  deskHoldProgress.value = 0
  if (event?.currentTarget?.hasPointerCapture?.(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId)
}
function selectSceneForBinding(scene) {
  pendingSceneId.value = scene.id
  sceneBindStep.value = scene.binding ? 'replace' : 'posture'
}
function recallScene(scene) {
  if (!scene?.binding) return
  if (scene.ambientPresetId) store.applyAmbientPreset(scene.ambientPresetId)
  const startHeight = store.deskHeightMm
  const startTilt = store.tiltAngleRaw
  const targetHeight = scene.binding.height * 10
  const targetTilt = scene.binding.tilt
  const startedAt = performance.now()
  const duration = Math.max(Math.abs(targetHeight - startHeight) / 38 * 1000, Math.abs(targetTilt - startTilt) / 3 * 1000, 260) / store.timeSpeed
  cancelAnimationFrame(sceneTravelFrame)
  const frame = now => {
    const progress = Math.min(1, (now - startedAt) / duration)
    const eased = 1 - (1 - progress) ** 3
    store.deskHeightMm = startHeight + (targetHeight - startHeight) * eased
    store.tiltAngleRaw = startTilt + (targetTilt - startTilt) * eased
    if (progress < 1) sceneTravelFrame = requestAnimationFrame(frame)
  }
  sceneTravelFrame = requestAnimationFrame(frame)
  exitSceneBinding()
}
function startQuickSceneHold(scene) {
  if (!scene?.binding) return
  quickSceneLongPress.value = false
  clearTimeout(quickSceneHoldTimer)
  quickSceneHoldTimer = setTimeout(() => { quickSceneLongPress.value = true; selectSceneForBinding(scene) }, 1000 / store.timeSpeed)
}
function stopQuickSceneHold() { clearTimeout(quickSceneHoldTimer) }
function onQuickSceneClick(scene) {
  if (quickSceneLongPress.value) { quickSceneLongPress.value = false; return }
  recallScene(scene)
}
function confirmSceneBinding() {
  if (sceneBindStep.value === 'confirmAdd') { sceneBindStep.value = 'pick'; return }
  if (sceneBindStep.value === 'replace') sceneBindStep.value = 'posture'
}
function finishSceneBinding(posture) { store.bindScene(pendingSceneId.value, posture); exitSceneBinding() }
function exitSceneBinding() {
  if (!sceneBindingMode.value) return
  sceneBindingMode.value = false
  sceneBindStep.value = 'select'
  pendingSceneId.value = null
}

function simulateSwipe(direction) {
  if (!store.isAwake) return
  store.markInteraction()
  // 设置分页交给 Swiper 的单一轨道处理，避免手写 enter/leave 动画出现相向移动。
  const isSettingsPagination = store.isSettings && ['up', 'down'].includes(direction)
  if (isSettingsPagination && settingsSwiper.value) {
    if (direction === 'up') settingsSwiper.value.slidePrev()
    else settingsSwiper.value.slideNext()
    return
  }
  if (isDetailScreen.value && activeDetail.value?.label === '用户管理' && userManagerView.value === 'list' && ['up', 'down'].includes(direction) && userListSwiper.value) {
    if (direction === 'up') userListSwiper.value.slidePrev()
    else userListSwiper.value.slideNext()
    return
  }
  if (isDetailScreen.value && activeDetail.value?.label === '场景管理' && sceneManagerView.value === 'list' && ['up', 'down'].includes(direction)) {
    sceneListPage.value = (sceneListPage.value + (direction === 'up' ? -1 : 1) + scenePages.value.length) % scenePages.value.length
    return
  }
  if (store.screenState === 'main' && ['left', 'right'].includes(direction)) {
    homePage.value = (homePage.value + (direction === 'left' ? 1 : -1) + homePageCount.value) % homePageCount.value
  } else store.navigateScreen(direction)
  swipeDirection.value = ''
  requestAnimationFrame(() => {
    swipeDirection.value = direction
    clearTimeout(swipeTimer)
    swipeTimer = setTimeout(() => { swipeDirection.value = '' }, 420 / store.timeSpeed)
  })
}

function startScreenSwipe(event) {
  if (sceneBindingMode.value || store.isSettings || (store.isSettingsDetail && store.settingsDetail?.label === '用户管理' && userManagerView.value === 'list')) return
  if (event.pointerType === 'mouse' && event.button !== 0) return
  screenSwipeStart.value = { x: event.clientX, y: event.clientY }
}

function endScreenSwipe(event) {
  if (sceneBindingMode.value || store.isSettings || (store.isSettingsDetail && store.settingsDetail?.label === '用户管理' && userManagerView.value === 'list')) return
  const start = screenSwipeStart.value
  screenSwipeStart.value = null
  if (!start) return
  const x = event.clientX - start.x
  const y = event.clientY - start.y
  if (Math.max(Math.abs(x), Math.abs(y)) < 18) return
  // 快捷根页面中，纵向手势交给内部设置轮播；只有横向才驱动主页轮播。
  if (isShortcutDetail.value && activeDetail.value?.label !== '场景管理' && Math.abs(y) >= Math.abs(x)) return
  simulateSwipe(Math.abs(x) > Math.abs(y) ? (x > 0 ? 'right' : 'left') : (y > 0 ? 'down' : 'up'))
}

function onSettingsSwiper(swiper) {
  settingsSwiper.value = swiper
  swiper.slideToLoop(store.settingsPage, 0)
}

function onSettingsSlideChange(swiper) {
  store.settingsPage = swiper.realIndex
  store.markInteraction()
}

function randomUserName() {
  userForm.value.name = `${NAME_PARTS_A[Math.floor(Math.random() * NAME_PARTS_A.length)]}${NAME_PARTS_B[Math.floor(Math.random() * NAME_PARTS_B.length)]}`
}
function openUserManager() { userManagerView.value = 'list'; selectedUserId.value = null; userListPage.value = 0 }
function openSettingsItem(item) {
  fromCustomHome.value = false
  prepareFeatureView(item)
  store.openSettingsDetail(item)
}
function openUserForm(user = null) {
  editingUserId.value = user?.id || null
  userForm.value = user ? { avatar: user.avatar, name: user.name } : { avatar: AVATAR_OPTIONS[0], name: '' }
  if (!user) randomUserName()
  userManagerView.value = 'form'
}
function saveUser() {
  const createdId = editingUserId.value ? null : store.addUser(userForm.value)
  if (editingUserId.value) store.updateUser(editingUserId.value, userForm.value)
  if (createdId) userListPage.value = Math.floor((store.users.length - 1) / 3)
  userManagerView.value = 'list'
  editingUserId.value = null
}
function selectUser(user) {
  if (longPressActive.value) { longPressActive.value = false; return }
  store.setCurrentUser(user.id)
}
function startUserHold(user, event) {
  if (event.pointerType === 'mouse' && event.button !== 0) return
  clearTimeout(userHoldTimer)
  clearTimeout(quickSceneHoldTimer)
  cancelAnimationFrame(sceneTravelFrame)
  longPressActive.value = false
  userHoldTimer = setTimeout(() => {
    longPressActive.value = true
    selectedUserId.value = user.id
    userManagerView.value = 'actions'
  }, 1000 / store.timeSpeed)
}
function stopUserHold(event) {
  clearTimeout(userHoldTimer)
}
function selectedUser() { return store.users.find(user => user.id === selectedUserId.value) }
function deleteSelectedUser() {
  if (selectedUserId.value) store.deleteUser(selectedUserId.value)
  userManagerView.value = 'list'
  selectedUserId.value = null
}
function onDetailBack() {
  if (store.settingsDetail?.label === '氛围灯管理' && ambientManagerView.value !== 'list') { ambientManagerView.value = 'list'; return }
  if (store.settingsDetail?.label === '场景管理' && sceneManagerView.value !== 'list') { sceneManagerView.value = 'list'; return }
  if (store.settingsDetail?.label === '用户管理' && userManagerView.value !== 'list') {
    userManagerView.value = 'list'
    return
  }
  fromCustomHome.value = false
  store.goBack()
}
function selectAmbientPreset(preset) { selectedAmbientPresetId.value = preset.id; ambientManagerView.value = 'info' }
function selectedAmbientPreset() { return store.ambientPresets.find(item => item.id === selectedAmbientPresetId.value) }
function showUserInfo() { userManagerView.value = 'info' }
function onUserListSwiper(swiper) {
  userListSwiper.value = swiper
  swiper.slideToLoop(userListPage.value, 0)
}
function onUserListSlideChange(swiper) { userListPage.value = swiper.realIndex; store.markInteraction() }
function onSceneListSwiper(swiper) { sceneListSwiper.value = swiper; swiper.slideToLoop(sceneListPage.value, 0) }
function onSceneListSlideChange(swiper) { sceneListPage.value = swiper.realIndex; store.markInteraction() }
function sceneIcon(scene) { return ({ study: handsetIcons.settingsUsers, work: handsetIcons.settingsScenes, series: handsetIcons.settingsLight, game: handsetIcons.settingsHealth })[scene?.icon] || handsetIcons.settingsScenes }
function startSceneHold(scene) { clearTimeout(sceneHoldTimer); sceneHoldTimer = setTimeout(() => { selectedSceneId.value = scene.id; sceneManagerView.value = 'info' }, 1000 / store.timeSpeed) }
function stopSceneHold() { clearTimeout(sceneHoldTimer) }
function selectedScene() { return store.scenes.find(scene => scene.id === selectedSceneId.value) }

function runHeightFrame(now) {
  if (!store.isHeightMoving) {
    heightFrame = null
    return
  }
  const elapsedSeconds = Math.min((now - heightFrameTime) / 1000, 0.05)
  heightFrameTime = now
  store.advanceHeight(HEIGHT_SPEED_MM_PER_SECOND * elapsedSeconds * store.timeSpeed)
  if (store.isHeightMoving) heightFrame = requestAnimationFrame(runHeightFrame)
}

function beginHeightHold(direction, target, pointerId) {
  try { target?.setPointerCapture?.(pointerId) } catch { /* 不支持捕获时仍允许长按 */ }
  if (store.locked) { showLockFeedback(); return }
  if (!store.startHeightMotion(direction)) return
  cancelAnimationFrame(heightFrame)
  heightFrameTime = performance.now()
  heightFrame = requestAnimationFrame(runHeightFrame)
}

function startHeightHold(direction, event) {
  if (event.pointerType === 'mouse' && event.button !== 0) return
  heightHoldStart = { x: event.clientX, y: event.clientY }
  const target = event.currentTarget
  const pointerId = event.pointerId
  clearTimeout(heightHoldTimer)
  heightHoldTimer = setTimeout(() => beginHeightHold(direction, target, pointerId), 90 / store.timeSpeed)
}

function cancelHeightHoldOnMove(event) {
  if (!heightHoldStart || Math.hypot(event.clientX - heightHoldStart.x, event.clientY - heightHoldStart.y) <= 12) return
  stopHeightHold(event)
}

function stopHeightHold(event) {
  clearTimeout(heightHoldTimer)
  heightHoldStart = null
  if (event?.currentTarget?.hasPointerCapture?.(event.pointerId)) {
    event.currentTarget.releasePointerCapture(event.pointerId)
  }
  cancelAnimationFrame(heightFrame)
  heightFrame = null
  store.stopHeightMotion()
}

function startHeightByKeyboard(direction, event) {
  if (event.repeat || !['Enter', ' '].includes(event.key)) return
  if (!store.startHeightMotion(direction)) return
  heightFrameTime = performance.now()
  heightFrame = requestAnimationFrame(runHeightFrame)
}

function stopHeightByKeyboard(event) {
  if (!['Enter', ' '].includes(event.key)) return
  stopHeightHold()
}

function runTiltFrame(now) {
  if (!store.isTiltMoving) {
    tiltFrame = null
    return
  }
  const elapsedSeconds = Math.min((now - tiltFrameTime) / 1000, 0.05)
  tiltFrameTime = now
  store.advanceTilt(TILT_SPEED_DEGREES_PER_SECOND * elapsedSeconds * store.timeSpeed)
  if (store.isTiltMoving) tiltFrame = requestAnimationFrame(runTiltFrame)
}

function beginTiltHold(direction, target, pointerId) {
  try { target?.setPointerCapture?.(pointerId) } catch { /* 不支持捕获时仍允许长按 */ }
  if (store.locked) { showLockFeedback(); return }
  if (!store.startTiltMotion(direction)) return
  cancelAnimationFrame(tiltFrame)
  tiltFrameTime = performance.now()
  tiltFrame = requestAnimationFrame(runTiltFrame)
}

function startTiltHold(direction, event) {
  if (event.pointerType === 'mouse' && event.button !== 0) return
  tiltHoldStart = { x: event.clientX, y: event.clientY }
  const target = event.currentTarget
  const pointerId = event.pointerId
  clearTimeout(tiltHoldTimer)
  tiltHoldTimer = setTimeout(() => beginTiltHold(direction, target, pointerId), 90 / store.timeSpeed)
}

function cancelTiltHoldOnMove(event) {
  if (!tiltHoldStart || Math.hypot(event.clientX - tiltHoldStart.x, event.clientY - tiltHoldStart.y) <= 12) return
  stopTiltHold(event)
}

function stopTiltHold(event) {
  clearTimeout(tiltHoldTimer)
  tiltHoldStart = null
  if (event?.currentTarget?.hasPointerCapture?.(event.pointerId)) {
    event.currentTarget.releasePointerCapture(event.pointerId)
  }
  cancelAnimationFrame(tiltFrame)
  tiltFrame = null
  store.stopTiltMotion()
}

function startTiltByKeyboard(direction, event) {
  if (event.repeat || !['Enter', ' '].includes(event.key)) return
  if (!store.startTiltMotion(direction)) return
  tiltFrameTime = performance.now()
  tiltFrame = requestAnimationFrame(runTiltFrame)
}

function stopTiltByKeyboard(event) {
  if (!['Enter', ' '].includes(event.key)) return
  stopTiltHold()
}

function registerInteraction() {
  store.markInteraction()
}

onMounted(() => {
  // 捕获阶段记录整个模拟界面的操作，即使内部按键使用 .stop 也不会漏记。
  window.addEventListener('pointerdown', registerInteraction, true)
  window.addEventListener('keydown', registerInteraction, true)
  inactivityTimer = setInterval(() => {
    store.tickClock()
    if (store.isAwake && store.simulatedTimestamp - store.lastInteractionTimestamp >= INACTIVITY_TIMEOUT_MS) store.sleepToHome()
  }, 1000)
})

onBeforeUnmount(() => {
  clearTimeout(swipeTimer)
  clearTimeout(userHoldTimer)
  clearTimeout(deskHoldTimer)
  clearTimeout(deskLockTimer)
  clearTimeout(lockFeedbackTimer)
  clearTimeout(deviceNoticeTimer)
  cancelAnimationFrame(deskHoldFrame)
  clearTimeout(heightHoldTimer)
  clearTimeout(tiltHoldTimer)
  cancelAnimationFrame(heightFrame)
  cancelAnimationFrame(tiltFrame)
  clearInterval(inactivityTimer)
  window.removeEventListener('pointerdown', registerInteraction, true)
  window.removeEventListener('keydown', registerInteraction, true)
  store.stopHeightMotion()
  store.stopTiltMotion()
})
</script>

<template>
  <div class="handset-wrapper" :style="handsetZoomStyle" @contextmenu.prevent>
    <div class="handset-scale-box">
    <div class="navigation-pad" aria-label="屏幕滑动模拟按键">
      <button class="direction-key key-up" type="button" aria-label="模拟向上滑动" :disabled="!store.isAwake" @click="simulateSwipe('up')">
        <Icon :icon="handsetIcons.chevronUp" />
      </button>
      <button class="direction-key key-left" type="button" aria-label="模拟向左滑动" :disabled="!store.isAwake" @click="simulateSwipe('left')">
        <Icon :icon="handsetIcons.chevronLeft" />
      </button>
      <button class="direction-key key-right" type="button" aria-label="模拟向右滑动" :disabled="!store.isAwake" @click="simulateSwipe('right')">
        <Icon :icon="handsetIcons.chevronRight" />
      </button>
      <button class="direction-key key-down" type="button" aria-label="模拟向下滑动" :disabled="!store.isAwake" @click="simulateSwipe('down')">
        <Icon :icon="handsetIcons.chevronDown" />
      </button>
    </div>
    <div class="handset-shell">
      <!-- 壳体表面层：边缘反光、磨砂纹理与玻璃面柔光均不参与交互 -->
      <div class="shell-rim" />
      <div class="shell-texture" />
      <div class="shell-reflection" />

      <!-- 屏幕：320×240px，唤醒前纯黑，点击唤醒 -->
      <div
        class="handset-screen"
        :class="[
          { awake: store.isAwake, 'height-moving': store.isHeightHolding, 'tilt-moving': store.isTiltHolding },
          `theme-${store.colorScheme}`,
          swipeDirection && `swipe-${swipeDirection}`,
        ]"
        :style="handsetMotionStyle"
        @click="onScreenClick"
        @pointerdown="startScreenSwipe"
        @pointerup="endScreenSwipe"
        @pointercancel="screenSwipeStart = null"
      >
        <template v-if="store.isAwake">
          <div class="status-bar">
            <div class="status-left">
              <Icon :class="['avatar-icon', `avatar-${store.currentUserProfile?.avatar || 'sky'}`]" :icon="handsetIcons.account" />
              <span class="username">{{ store.currentUserName || '米仔' }}</span>
            </div>
            <div class="status-right">
              <Icon v-if="store.locked" class="status-icon lock-status-icon" :icon="handsetIcons.lock" aria-label="桌面已锁定" />
              <span v-if="store.overheat" class="hot-badge">HOT</span>
              <Icon v-if="store.reminder" class="status-icon bell-icon active" :icon="handsetIcons.bell" />
              <Icon
                :class="['status-icon', 'network-icon', { offline: !store.network }]"
                :icon="store.network ? handsetIcons.wifi : handsetIcons.wifiOff"
                aria-label="网络状态"
              />
            </div>
          </div>

          <div
            class="screen-body"
            :class="{
              'motion-active': store.isHeightHolding || store.isTiltHolding,
              'height-active': store.isHeightHolding,
              'tilt-active': store.isTiltHolding,
            }"
          >
            <transition name="device-notice"><div v-if="deviceNotice" class="device-notice"><Icon :icon="handsetIcons.lock" />{{ deviceNotice }}</div></transition>
            <div v-if="lockFeedbackVisible" class="lock-action-feedback"><Icon :icon="handsetIcons.lock" /></div>
            <template v-if="store.isSettings">
              <div class="settings-screen">
                <div class="settings-heading">
                  <button class="settings-back" type="button" aria-label="返回主页" @click="store.navigateScreen('up')">
                    <Icon :icon="handsetIcons.chevronLeft" />
                  </button>
                  <span>设置</span>
                </div>
                <div class="settings-pages">
                  <Swiper
                    class="settings-carousel"
                    direction="vertical"
                    :slides-per-view="1"
                    :speed="Math.max(160, 280 / store.timeSpeed)"
                    :loop="true"
                    :threshold="8"
                    @swiper="onSettingsSwiper"
                    @slide-change="onSettingsSlideChange"
                  >
                    <SwiperSlide v-for="(page, pageIndex) in SETTINGS_PAGES" :key="pageIndex" class="settings-slide">
                    <div class="settings-grid">
                      <button
                        v-for="item in page"
                        :key="item.label"
                        class="settings-tile"
                        type="button"
                        :aria-label="item.label"
                        @click="openSettingsItem(item)"
                      >
                        <Icon :icon="item.icon" />
                        <span>{{ item.label }}</span>
                      </button>
                    </div>
                    </SwiperSlide>
                  </Swiper>
                </div>
                <div class="settings-dots" aria-label="设置页数">
                  <i v-for="page in store.settingsPageCount" :key="page" :class="{ active: page - 1 === store.settingsPage }" />
                </div>
              </div>
            </template>

            <template v-else-if="isDetailScreen">
              <div class="settings-detail-screen" :key="isShortcutDetail ? `shortcut-${homePage}` : `settings-${activeDetail?.label}`">
                <div class="settings-heading settings-detail-heading">
                  <button v-if="!isShortcutDetail" class="settings-back" type="button" aria-label="返回上一页" @click="onDetailBack">
                    <Icon :icon="handsetIcons.chevronLeft" />
                  </button>
                  <span>{{ activeDetail?.label === '用户管理' && userManagerView === 'form' ? (editingUserId ? '编辑用户' : '新增用户') : activeDetail?.label }}</span>
                  <div v-if="activeDetail?.label === '用户管理' && userManagerView === 'form'" class="user-header-actions">
                    <button type="button" aria-label="保存用户" @click="saveUser"><Icon :icon="handsetIcons.check" /></button>
                  </div>
                  <button v-if="isShortcutDetail && activeShortcutItem?.label === activeDetail?.label" class="custom-home-delete" type="button" aria-label="删除快捷页面" @click="deletePinnedHomeItem">−</button>
                </div>
                <template v-if="activeDetail?.label === '用户管理'">
                  <div v-if="userManagerView === 'list'" class="user-manager-list">
                    <Swiper
                      :key="`user-list-${store.users.length}`"
                      class="user-list-carousel"
                      direction="vertical"
                      :slides-per-view="1"
                      :speed="Math.max(160, 280 / store.timeSpeed)"
                      :loop="userListPages > 1"
                      :allow-touch-move="userListPages > 1"
                      :threshold="8"
                      @swiper="onUserListSwiper"
                      @slide-change="onUserListSlideChange"
                    >
                    <SwiperSlide v-for="(page, pageIndex) in userPages" :key="pageIndex" class="user-list-slide">
                    <div class="user-profile-grid">
                    <button
                      v-for="user in page.filter(item => !item.isAdd)"
                      :key="user.id"
                      class="user-profile-card"
                      :class="[{ selected: store.currentUser === user.id }, `avatar-${user.avatar}`]"
                      type="button"
                      @pointerdown="startUserHold(user, $event)"
                      @pointerup="stopUserHold($event)"
                      @pointercancel="stopUserHold($event)"
                      @click="selectUser(user)"
                    >
                      <span class="user-avatar"><Icon :icon="handsetIcons.account" /></span>
                      <span>{{ user.name }}</span>
                    </button>
                    <button v-if="page.some(item => item.isAdd)" class="user-profile-card user-add-card" type="button" aria-label="新增用户" @click="openUserForm()"><span class="user-add-icon">+</span><span>新增</span></button>
                    </div>
                    </SwiperSlide>
                    </Swiper>
                    <div v-if="userListPages > 1" class="user-list-dots" aria-label="用户列表页数"><i v-for="page in userListPages" :key="page" :class="{ active: page - 1 === userListPage }" /></div>
                  </div>

                  <div v-else-if="userManagerView === 'form'" class="user-form-screen">
                    <p class="user-form-label">选择头像</p>
                    <div class="avatar-picker">
                      <button v-for="avatar in AVATAR_OPTIONS" :key="avatar" type="button" :class="['avatar-choice', `avatar-${avatar}`, { selected: userForm.avatar === avatar }]" @click="userForm.avatar = avatar"><Icon :icon="handsetIcons.account" /></button>
                    </div>
                    <p class="user-form-label">用户名</p>
                    <button class="generated-name" type="button" @click="randomUserName"><strong>{{ userForm.name }}</strong><span>点击换一个</span></button>
                  </div>

                  <div v-else-if="userManagerView === 'actions'" class="user-action-sheet">
                    <span :class="['action-avatar', `avatar-${selectedUser()?.avatar || 'sky'}`]"><Icon :icon="handsetIcons.account" /></span>
                    <strong>{{ selectedUser()?.name }}</strong>
                    <p>选择操作</p>
                    <div><button type="button" @click="showUserInfo">信息</button><button type="button" @click="openUserForm(selectedUser())">编辑</button><button class="danger" type="button" :disabled="store.users.length <= 1" @click="deleteSelectedUser">删除</button></div>
                    <button class="sheet-cancel" type="button" @click="userManagerView = 'list'">取消</button>
                  </div>

                  <div v-else-if="userManagerView === 'info'" class="user-info-screen">
                    <template v-if="selectedUser()?.wechat">
                      <span :class="['action-avatar', `avatar-${selectedUser()?.avatar || 'sky'}`]"><Icon :icon="handsetIcons.account" /></span>
                      <strong>已绑定微信号</strong><b>{{ selectedUser()?.wechat }}</b>
                    </template>
                    <template v-else>
                      <span :class="['action-avatar', `avatar-${selectedUser()?.avatar || 'sky'}`]"><Icon :icon="handsetIcons.account" /></span>
                      <strong>还未绑定微信号</strong>
                      <button class="bind-link" type="button" @click="userManagerView = 'bind'">现在去绑定</button>
                    </template>
                  </div>

                  <div v-else class="user-bind-screen">
                    <div class="qr-code" aria-label="绑定微信二维码"><i /><i /><i /></div>
                    <div class="bind-methods"><strong>微信扫一扫</strong><span>扫码跳转小程序</span><em>或</em><b>手机靠近 NFC 跳转</b></div>
                  </div>
                </template>
                <div v-else-if="activeDetail?.label === '场景管理' && sceneManagerView === 'list'" class="scene-manager-list">
                  <div class="scene-profile-grid">
                    <button v-for="scene in scenePages[sceneListPage]" :key="scene.id" class="scene-profile" type="button" @click="selectedSceneId = scene.id; sceneManagerView = 'info'"><span class="scene-profile-icon"><Icon :icon="sceneIcon(scene)" /></span><strong>{{ scene.name }}</strong></button>
                  </div>
                  <div v-if="scenePages.length > 1" class="user-list-dots"><i v-for="(_, page) in scenePages" :key="page" :class="{ active: page === sceneListPage }" /></div>
                </div>
                <div v-else-if="activeDetail?.label === '场景管理'" class="scene-info-screen">
                  <div class="scene-info-identity"><span class="scene-profile-icon"><Icon :icon="sceneIcon(selectedScene())" /></span><strong>{{ selectedScene()?.name }}</strong></div>
                  <div class="scene-info-values"><template v-if="selectedScene()?.binding"><div><span>桌高</span><b>{{ selectedScene().binding.height }}<em>cm</em></b></div><div><span>倾斜</span><b>{{ selectedScene().binding.tilt }}<em>°</em></b></div><div><span>状态</span><b class="scene-info-status">{{ selectedScene().posture === 'stand' ? '站立' : selectedScene().posture === 'sit' ? '坐着' : '未设置' }}</b></div></template><p v-else>当前场景无绑定数据</p><div class="scene-light-choice"><span>灯效</span><button v-for="preset in store.ambientPresets" :key="preset.id" type="button" :class="{ active: selectedScene()?.ambientPresetId === preset.id }" :style="{ '--preset-color': preset.color }" @click="store.setSceneAmbientPreset(selectedScene()?.id, preset.id)" /></div></div>
                </div>
                <div v-else-if="activeDetail?.label === '氛围灯管理' && ambientManagerView === 'list'" class="ambient-manager-list">
                  <button v-for="preset in store.ambientPresets" :key="preset.id" class="ambient-preset-card" type="button" @click="selectAmbientPreset(preset)"><span class="ambient-preset-orb" :style="{ '--preset-color': preset.color }"><Icon :icon="handsetIcons.settingsLight" /></span><strong>{{ preset.name }}</strong></button>
                </div>
                <div v-else-if="activeDetail?.label === '氛围灯管理'" class="ambient-preset-info">
                  <span class="ambient-preset-orb large" :style="{ '--preset-color': selectedAmbientPreset()?.color }"><Icon :icon="handsetIcons.settingsLight" /></span>
                  <div class="ambient-edit-row"><span>颜色</span><aside><button v-for="color in ['#f4d6a1', '#ffae78', '#798cff']" :key="color" type="button" :class="{ active: selectedAmbientPreset()?.color === color }" :style="{ '--preset-color': color }" @click="store.updateAmbientPreset(selectedAmbientPreset()?.id, { color })" /></aside></div>
                  <div class="ambient-edit-row"><span>亮度</span><aside><button v-for="brightness in [20, 40, 65, 85, 100]" :key="brightness" type="button" :class="{ active: selectedAmbientPreset()?.brightness === brightness }" @click="store.updateAmbientPreset(selectedAmbientPreset()?.id, { brightness })">{{ brightness }}</button></aside></div>
                  <div class="ambient-edit-row ambient-effect-row"><span>效果</span><aside><button v-for="effect in ['常亮', '呼吸', '渐变']" :key="effect" type="button" :class="{ active: selectedAmbientPreset()?.effect === effect }" @click="store.updateAmbientPreset(selectedAmbientPreset()?.id, { effect })">{{ effect }}</button></aside></div>
                  <button type="button" @click="store.applyAmbientPreset(selectedAmbientPreset()?.id)">应用此预设</button>
                </div>
                <div v-else class="settings-detail-content">
                  <Icon :icon="activeDetail?.icon" />
                  <strong>{{ activeDetail?.label }}</strong>
                  <span>功能配置将在后续接入</span>
                </div>
              </div>
            </template>

            <template v-else-if="store.isAmbientControl">
              <div class="ambient-control-screen">
                <div class="ambient-control-top"><span>氛围灯</span><button type="button" :class="{ on: store.ambientOn }" @click="store.toggleAmbient()"><i />{{ store.ambientOn ? '开启' : '关闭' }}</button></div>
                <div class="ambient-preview" :class="{ on: store.ambientOn }" :style="{ '--preset-color': store.activeAmbientPreset?.color }"><i /><span>{{ store.activeAmbientPreset?.name }}</span></div>
                <div class="ambient-quick-grid"><button v-for="preset in store.ambientPresets" :key="preset.id" type="button" :class="{ active: preset.id === store.ambientPresetId }" @click="store.applyAmbientPreset(preset.id)"><span :style="{ '--preset-color': preset.color }"><Icon :icon="handsetIcons.settingsLight" /></span><b>{{ preset.name }}</b></button></div>
                <small>下滑返回主页</small>
              </div>
            </template>

            <template v-else>
            <template v-if="homePage === 0">
            <div v-if="!store.isTiltHolding && !sceneBindingMode" class="control-col control-height">
              <button
                class="screen-action height-action height-up"
                type="button"
                aria-label="长按升高桌面"
                @pointerdown="startHeightHold('up', $event)"
                @pointermove="cancelHeightHoldOnMove"
                @pointerup="stopHeightHold($event)"
                @pointercancel="stopHeightHold($event)"
                @lostpointercapture="stopHeightHold"
                @keydown="startHeightByKeyboard('up', $event)"
                @keyup="stopHeightByKeyboard"
              ><Icon class="chevron" :icon="handsetIcons.chevronUp" /></button>

              <template v-if="!store.isHeightHolding">
                <div class="value-label">桌高</div>
                <div class="value-block">
                  <div class="value-num">{{ store.deskHeight }}</div>
                  <div class="unit">cm</div>
                </div>
              </template>
              <div v-else class="hold-feedback" aria-hidden="true">
                <span class="hold-pulse"><i /></span>
                <small>长按中</small>
              </div>

              <button
                class="screen-action height-action height-down"
                type="button"
                aria-label="长按降低桌面"
                @pointerdown="startHeightHold('down', $event)"
                @pointermove="cancelHeightHoldOnMove"
                @pointerup="stopHeightHold($event)"
                @pointercancel="stopHeightHold($event)"
                @lostpointercapture="stopHeightHold"
                @keydown="startHeightByKeyboard('down', $event)"
                @keyup="stopHeightByKeyboard"
              ><Icon class="chevron" :icon="handsetIcons.chevronDown" /></button>
            </div>

            <template v-if="!store.isHeightHolding && !store.isTiltHolding">
              <div class="desk-illustration">
                <img :src="deskHomeImage" alt="电动升降桌" draggable="false" />
                <button class="desk-scene-hotspot" type="button" aria-label="场景选择热区" @pointerdown="startDeskHold" @pointermove="cancelDeskHoldOnMove" @pointerup="stopDeskHold" @pointercancel="stopDeskHold" @click.stop="exitSceneBinding" />
                <div v-if="deskHoldActive" class="lock-hold-progress" aria-hidden="true"><svg viewBox="0 0 166 166"><circle class="lock-progress-track" cx="83" cy="83" r="80" /><circle class="lock-progress-value" cx="83" cy="83" r="80" pathLength="1" :style="{ strokeDashoffset: 1 - deskHoldProgress }" /></svg></div>
              </div>
              <div v-if="sceneBindingMode" class="scene-bind-grid">
                <button v-for="scene in sceneBindingButtons" :key="scene.id" type="button" :aria-label="scene.isAdd ? '添加场景' : scene.isMore ? '更多场景' : scene.name" @pointerdown="startQuickSceneHold(scene)" @pointerup="stopQuickSceneHold" @pointercancel="stopQuickSceneHold" @click="scene.isAdd ? (sceneBindStep = 'confirmAdd') : scene.isMore ? (sceneBindingMode = false) : onQuickSceneClick(scene)"><Icon v-if="!scene.isAdd && !scene.isMore" :icon="sceneIcon(scene)" /><span v-else class="scene-more">{{ scene.isAdd ? '+' : '···' }}</span></button>
                <div v-if="sceneBindStep !== 'select'" class="scene-bind-backdrop" />
                <div v-if="sceneBindStep !== 'select'" class="scene-bind-dialog">
                  <strong>{{ sceneBindStep === 'confirmAdd' ? '是否记录当前数据？' : sceneBindStep === 'replace' ? '替换当前绑定？' : sceneBindStep === 'pick' ? '选择需要记录的场景' : '选择状态' }}</strong>
                  <Swiper v-if="sceneBindStep === 'pick'" class="scene-pick-carousel" :slides-per-view="1" :speed="Math.max(160, 280 / store.timeSpeed)" :allow-touch-move="unboundScenePages.length > 1"><SwiperSlide v-for="(page, pageIndex) in unboundScenePages" :key="pageIndex"><div class="scene-pick-grid"><button v-for="scene in page" :key="scene.id" @click="selectSceneForBinding(scene)"><span class="scene-pick-icon"><Icon :icon="sceneIcon(scene)" /></span><span>{{ scene.name }}</span></button><span v-if="!page.length" class="scene-pick-empty">暂无可新增场景</span></div></SwiperSlide></Swiper>
                  <div v-if="sceneBindStep !== 'posture' && sceneBindStep !== 'pick'"><button @click="sceneBindStep = 'select'">取消</button><button @click="confirmSceneBinding">确认</button></div>
                  <div v-else-if="sceneBindStep === 'posture'" class="scene-posture-actions"><button @click="finishSceneBinding('sit')">坐姿</button><button @click="finishSceneBinding('stand')">站立</button><button @click="finishSceneBinding('none')">不选择</button></div>
                </div>
              </div>
            </template>

            <div v-if="!store.isHeightHolding && !sceneBindingMode" class="control-col control-tilt">
              <button
                class="screen-action tilt-action tilt-up"
                type="button"
                aria-label="长按增大倾斜角度"
                @pointerdown="startTiltHold('up', $event)"
                @pointermove="cancelTiltHoldOnMove"
                @pointerup="stopTiltHold($event)"
                @pointercancel="stopTiltHold($event)"
                @lostpointercapture="stopTiltHold"
                @keydown="startTiltByKeyboard('up', $event)"
                @keyup="stopTiltByKeyboard"
              ><Icon class="chevron" :icon="handsetIcons.chevronUp" /></button>

              <template v-if="!store.isTiltHolding">
                <div class="value-label">倾斜角度</div>
                <div class="value-block value-block-angle">
                  <div class="value-num">{{ store.tiltAngle }}°</div>
                </div>
              </template>
              <div v-else class="hold-feedback" aria-hidden="true">
                <span class="hold-pulse"><i /></span>
                <small>长按中</small>
              </div>

              <button
                class="screen-action tilt-action tilt-down"
                type="button"
                aria-label="长按减小倾斜角度"
                @pointerdown="startTiltHold('down', $event)"
                @pointermove="cancelTiltHoldOnMove"
                @pointerup="stopTiltHold($event)"
                @pointercancel="stopTiltHold($event)"
                @lostpointercapture="stopTiltHold"
                @keydown="startTiltByKeyboard('down', $event)"
                @keyup="stopTiltByKeyboard"
              ><Icon class="chevron" :icon="handsetIcons.chevronDown" /></button>
            </div>

            <div v-if="store.isHeightHolding" :class="['motion-readout', 'height-readout', `direction-${store.heightDirection}`]">
              <div :class="['travel-graphic', { 'at-limit': store.heightLimitState }]" aria-hidden="true">
                <span v-for="i in 3" :key="i" class="travel-chevron">
                  <Icon :icon="store.heightDirection === 'up' ? handsetIcons.chevronUp : handsetIcons.chevronDown" />
                </span>
              </div>
              <div class="height-data">
                <span class="height-caption">当前桌高</span>
                <div class="height-number"><strong>{{ store.deskHeight }}</strong><span>cm</span></div>
              </div>
            </div>

            <div v-if="store.isTiltHolding" :class="['motion-readout', 'tilt-readout', `direction-${store.tiltDirection}`]">
              <div :class="['travel-graphic', { 'at-limit': store.tiltLimitState }]" aria-hidden="true">
                <span v-for="i in 3" :key="i" class="travel-chevron">
                  <Icon :icon="store.tiltDirection === 'up' ? handsetIcons.chevronUp : handsetIcons.chevronDown" />
                </span>
              </div>
              <div class="height-data">
                <span class="height-caption">当前倾角</span>
                <div class="height-number tilt-number"><strong>{{ store.tiltAngle }}</strong><span>°</span></div>
              </div>
            </div>

            <Transition name="limit-card">
              <div v-if="store.heightLimitState || store.tiltLimitState" class="limit-overlay" role="status" aria-live="polite">
                <div class="limit-card">
                  <span class="limit-marker" aria-hidden="true"><i /></span>
                  <strong v-if="store.heightLimitState">{{ store.heightLimitState === 'max' ? '已到最高点' : '已到最低点' }}</strong>
                  <strong v-else>{{ store.tiltLimitState === 'max' ? '已到最大角度' : '已到最小角度' }}</strong>
                </div>
              </div>
            </Transition>
            </template>
            <div v-else-if="homePage === 1" class="posture-dashboard">
              <div class="dashboard-heading"><span>近 7 天站坐</span><small>站立占比</small></div>
              <div class="weekly-chart"><div v-for="(stand, index) in weeklyPosture" :key="index" class="weekly-bar"><i :style="{ height: `${stand}%` }" /><b>{{ ['一','二','三','四','五','六','日'][index] }}</b></div></div>
              <div class="posture-summary"><span>平均站立 <b>44%</b></span><span>本周总时长 <b>47h</b></span></div>
              <div class="home-page-dots"><i /><i class="active" /><i /></div>
            </div>
            <div v-else class="home-custom-page">
              <button class="home-add-button" type="button" aria-label="添加快捷功能" @click="customHomePickerOpen = true">+</button><span class="home-add-caption">添加快捷页面</span>
              <div v-if="customHomePickerOpen" class="home-picker-backdrop" />
              <div v-if="customHomePickerOpen" class="home-picker"><strong>添加快捷功能</strong><div><button v-for="item in customHomeOptions" :key="item.label" type="button" @click="pinHomeItem(item)"><Icon :icon="item.icon" /><span>{{ item.label }}</span></button></div><button class="picker-close" type="button" @click="customHomePickerOpen = false">取消</button></div>
              <div class="home-page-dots"><i /><i /><i v-for="(_, index) in customHomeItems" :key="index" /><i class="active" /></div>
            </div>
            </template>
          </div>
        </template>
        <div class="screen-glass" />
      </div>

      <!-- NFC 感应区：独立于屏幕，可交互 -->
      <button class="nfc-zone" type="button" title="NFC 感应区" aria-label="模拟 NFC 感应" @click="onNfcClick">
        <Icon class="nfc-symbol" :icon="handsetIcons.nfc" aria-hidden="true" />
      </button>
    </div>
    </div>
  </div>
</template>

<style scoped>
.handset-wrapper {
  display: flex;
  justify-content: center;
  width: 100%;
  user-select: none;
  -webkit-user-select: none;
  -webkit-touch-callout: none;
  height: calc(190px * var(--ui-scale));
}
.handset-wrapper * {
  user-select: none;
  -webkit-user-select: none;
  -webkit-touch-callout: none;
}

/* 缩放容器：按外壳固定尺寸 × 0.55 预留布局空间，仅做整体视觉缩放，不改变内部固定布局 */
.handset-scale-box {
  position: relative;
  width: calc(863px * 0.55 + 86px);
  height: calc(345px * 0.55);
  flex-shrink: 0;
  transform: scale(var(--ui-scale));
  transform-origin: center top;
}

/* 左侧实体四向键：独立底座、磨砂键帽和机械按压反馈。 */
.navigation-pad {
  position: absolute;
  /* 174×0.55 = 95.7px，与 345×0.55 = 189.75px 的手控器严格垂直居中。 */
  top: 47px;
  left: 0;
  width: 134px;
  height: 174px;
  transform: scale(0.55);
  transform-origin: top left;
}
.direction-key {
  position: absolute;
  z-index: 2;
  width: 46px;
  height: 46px;
  display: grid;
  place-items: center;
  padding: 0;
  border: 1px solid rgba(214,220,218,0.3);
  border-radius: 14px;
  background: linear-gradient(150deg, #3a3e3d 0%, #191c1b 46%, #080a09 100%);
  color: #d8dddb;
  box-shadow:
    0 5px 7px rgba(0,0,0,0.58),
    inset 0 2px 2px rgba(255,255,255,0.13),
    inset 0 -3px 4px rgba(0,0,0,0.68);
  cursor: pointer;
  transition: transform 0.1s ease, color 0.14s ease, box-shadow 0.1s ease;
}
.direction-key svg { width: 30px; height: 30px; }
.direction-key:hover:not(:disabled) { color: #fff; }
.direction-key:active:not(:disabled) {
  transform: translateY(3px) scale(0.97);
  box-shadow: 0 1px 2px rgba(0,0,0,0.7), inset 0 3px 5px rgba(0,0,0,0.62);
}
.direction-key:focus-visible { outline: 3px solid #579df4; outline-offset: 3px; }
.direction-key:disabled { color: #626765; cursor: default; opacity: 0.72; }
.key-up { top: 0; left: 44px; }
.key-left { top: 64px; left: 0; }
.key-right { top: 64px; right: 0; }
.key-down { top: 128px; left: 44px; }

/* 外壳 863×345px（110×44mm，7.843px/mm），固定不可调整 */
.handset-shell {
  --screen-width: 320px;
  --screen-height: 240px;
  position: absolute;
  top: 0;
  left: 86px;
  width: 863px;
  height: 345px;
  isolation: isolate;
  background:
    radial-gradient(115% 95% at 50% 112%, rgba(39, 43, 42, 0.52) 0%, transparent 56%),
    radial-gradient(92% 80% at 51% -13%, rgba(93, 98, 96, 0.42) 0%, rgba(44, 48, 47, 0.14) 37%, transparent 68%),
    linear-gradient(180deg, #292c2b 0%, #171a19 15%, #111413 52%, #151817 84%, #090b0b 100%);
  border-radius: 172px;
  border: 1px solid rgba(228, 234, 232, 0.62);
  box-shadow:
    0 3px 0 rgba(255, 255, 255, 0.72),
    0 13px 18px rgba(0, 0, 0, 0.52),
    0 35px 70px rgba(0, 0, 0, 0.34),
    inset 0 11px 16px rgba(255, 255, 255, 0.14),
    inset 0 -13px 22px rgba(0, 0, 0, 0.78),
    inset 12px 0 18px rgba(255, 255, 255, 0.035),
    inset -12px 0 18px rgba(0, 0, 0, 0.34);
  transform: scale(0.55);
  transform-origin: top left;
  overflow: hidden;
}

/* 靠近实物轮廓的第二道压铸边，顶部亮、底部收暗。 */
.shell-rim {
  position: absolute;
  z-index: 0;
  inset: 8px 9px 10px;
  border-radius: 164px;
  border: 2px solid rgba(211, 216, 214, 0.36);
  box-shadow:
    inset 0 5px 7px rgba(255, 255, 255, 0.16),
    inset 0 -5px 8px rgba(0, 0, 0, 0.76),
    0 1px 2px rgba(0, 0, 0, 0.8);
  pointer-events: none;
}

/* 极细颗粒打散大面积渐变，模拟细磨砂注塑表面。 */
.shell-texture {
  position: absolute;
  z-index: 0;
  inset: 12px;
  border-radius: 160px;
  opacity: 0.17;
  background-image:
    repeating-radial-gradient(circle at 27% 31%, rgba(255,255,255,0.19) 0 0.45px, transparent 0.6px 3px),
    repeating-radial-gradient(circle at 73% 67%, rgba(0,0,0,0.28) 0 0.5px, transparent 0.7px 4px);
  mix-blend-mode: soft-light;
  pointer-events: none;
}

/* 参考图只有沿上沿铺开的柔和反射，不使用突兀的斜向高光带。 */
.shell-reflection {
  position: absolute;
  z-index: 0;
  top: 12px;
  left: 90px;
  width: 683px;
  height: 94px;
  border-radius: 50%;
  background: radial-gradient(ellipse at center top, rgba(255,255,255,0.13), rgba(255,255,255,0.035) 44%, transparent 72%);
  filter: blur(6px);
  pointer-events: none;
}

/*
 * TFT 模拟画布严格固定为 320×240 CSS px。
 * 外壳的 transform 只改变最终展示比例，不参与内部布局计算；outline 也不占盒模型尺寸。
 */
.handset-screen {
  --screen-bg: #fafafa;
  --screen-surface: #ffffff;
  --screen-surface-soft: #f3f3f3;
  --screen-bar: #f1f1f1;
  --screen-border: #dedede;
  --screen-text: #111111;
  --screen-muted: #777777;
  --screen-accent: #4596f7;
  position: absolute;
  z-index: 2;
  /* 参考图 2048×813：屏幕左上约 (405,127)，换算到 863×345 外壳坐标。 */
  left: 171px;
  top: 54px;
  box-sizing: border-box;
  width: var(--screen-width);
  height: var(--screen-height);
  min-width: var(--screen-width);
  min-height: var(--screen-height);
  max-width: var(--screen-width);
  max-height: var(--screen-height);
  background: #000;
  border-radius: 4px;
  border: 0;
  outline: 2px solid #090b0b;
  box-shadow:
    0 2px 3px rgba(255,255,255,0.08),
    0 5px 10px rgba(0,0,0,0.62),
    inset 0 0 0 1px rgba(255,255,255,0.05);
  cursor: pointer;
  touch-action: none;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.handset-screen.theme-dark {
  --screen-bg: #111514;
  --screen-surface: #1b201f;
  --screen-surface-soft: #252b29;
  --screen-bar: #181c1b;
  --screen-border: #303735;
  --screen-text: #f2f5f4;
  --screen-muted: #9ca6a3;
  --screen-accent: #62a8ff;
}
.handset-screen.awake { background: var(--screen-bg); }

@media (max-width: 760px), (orientation: landscape) and (max-height: 600px) {
  /* 触屏可直接滑动，手机端不再占用外壳左侧空间放置模拟方向键。 */
  .navigation-pad { display: none; }
  .handset-scale-box { width: calc(863px * 0.55); }
  .handset-shell { left: 0; }
}

/* 屏幕表面玻璃反光，覆盖在内容之上但不拦截点击（点击仍需生效，用 pointer-events:none） */
.screen-glass {
  position: absolute;
  inset: 0;
  pointer-events: none;
  background: linear-gradient(
    115deg,
    rgba(255,255,255,0.16) 0%,
    rgba(255,255,255,0.05) 22%,
    transparent 45%,
    transparent 100%
  );
}

.status-bar {
  position: relative;
  z-index: 1;
  height: 40px;
  box-sizing: border-box;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 17px 0 9px;
  background: var(--screen-bar);
  border-bottom: 1px solid var(--screen-border);
}
.status-left { display: flex; align-items: center; gap: 7px; }
.avatar-icon {
  width: 28px;
  height: 28px;
  color: var(--screen-text);
}
.avatar-icon.avatar-sky { color: #5799d4; }
.avatar-icon.avatar-moss { color: #5e9c7b; }
.avatar-icon.avatar-coral { color: #d87968; }
.avatar-icon.avatar-violet { color: #8a72c7; }
.username { font-size: 15px; font-weight: 600; color: var(--screen-text); }
.status-right { display: flex; align-items: center; gap: 12px; }
.hot-badge { font-size: 15px; line-height: 1; font-weight: 800; color: #ee4162; }
.status-icon { font-size: 23px; color: #4b95f4; }
.bell-icon { color: var(--screen-text); }
.lock-status-icon { color: #e44754; font-size: 20px; }
.network-icon { color: var(--screen-text); }
.network-icon.offline { color: #999; }

.screen-body {
  position: relative;
  flex: 1;
  background: var(--screen-bg);
}
.posture-dashboard,.home-custom-page { height:100%; padding:14px 20px 8px; display:flex; flex-direction:column; align-items:center; }.dashboard-heading { width:100%; display:flex; align-items:baseline; justify-content:space-between; font-size:16px; font-weight:700; }.dashboard-heading small { color:var(--screen-muted); font-size:10px; font-weight:500; }.posture-chart { position:relative; width:104px; height:104px; margin:4px 0 -1px; }.posture-chart svg { width:100%; height:100%; }.posture-chart circle { fill:none; stroke-width:13; }.posture-chart-track { stroke:color-mix(in srgb,var(--screen-border) 76%,transparent); }.posture-chart-stand { stroke:#5ba3e9; stroke-linecap:round; }.posture-chart div { position:absolute; inset:0; display:flex; flex-direction:column; align-items:center; justify-content:center; }.posture-chart b { font-size:23px; line-height:1; }.posture-chart span { margin-top:3px; color:var(--screen-muted); font-size:10px; }.posture-legend { display:flex; width:100%; justify-content:center; gap:16px; font-size:10px; }.posture-legend span { display:flex; align-items:center; gap:4px; }.posture-legend i { width:7px; height:7px; border-radius:50%; }.posture-legend .stand { background:#5ba3e9; }.posture-legend .sit { background:#cbd4dd; }.posture-legend b { font-size:11px; }.home-page-dots { margin-top:auto; display:flex; gap:5px; }.home-page-dots i { width:4px; height:4px; border-radius:50%; background:color-mix(in srgb,var(--screen-muted) 45%,transparent); }.home-page-dots i.active { width:12px; border-radius:9px; background:var(--screen-accent); }.custom-light-preview { position:relative; width:205px; height:46px; margin:20px 0 17px; overflow:hidden; border-radius:12px; background:#171a1b; }.custom-light-preview::before { content:''; position:absolute; inset:-20px; background:var(--preset-color); opacity:.1; filter:blur(15px); }.custom-light-preview.on::before { opacity:.72; }.custom-light-preview i { position:absolute; z-index:1; left:12px; right:12px; top:22px; height:4px; border-radius:5px; background:#303333; }.custom-light-preview.on i { background:var(--preset-color); box-shadow:0 0 8px var(--preset-color); }.custom-light-preview span { position:absolute; z-index:2; inset:0; display:grid; place-items:center; color:#fff; font-size:12px; font-weight:700; text-shadow:0 1px 3px #000; }.custom-light-actions { display:grid; grid-template-columns:repeat(4,1fr); width:100%; gap:5px; }.custom-light-actions button { display:flex; flex-direction:column; align-items:center; gap:3px; padding:4px 0; border:0; color:var(--screen-muted); background:transparent; font-size:9px; }.custom-light-actions button svg,.custom-light-actions button i { width:19px; height:19px; border-radius:50%; color:var(--preset-color); background:var(--preset-color); }.custom-light-actions button:first-child svg { color:var(--screen-text); background:transparent; }.custom-light-actions button.active { color:var(--screen-accent); }
.weekly-chart { display:flex; align-items:end; justify-content:space-between; width:100%; height:106px; margin:14px 0 8px; padding:0 5px; border-bottom:1px solid var(--screen-border); }.weekly-bar { position:relative; display:flex; flex-direction:column; justify-content:flex-end; align-items:center; width:18px; height:100%; }.weekly-bar i { width:11px; min-height:9px; border-radius:6px 6px 2px 2px; background:linear-gradient(#7cb4ed,#4d91d8); transition:height .25s ease; }.weekly-bar b { position:absolute; bottom:-16px; color:var(--screen-muted); font-size:9px; font-weight:600; }.posture-summary { display:flex; width:100%; justify-content:space-around; margin-top:13px; color:var(--screen-muted); font-size:10px; }.posture-summary b { margin-left:3px; color:var(--screen-text); font-size:13px; }.home-custom-page { position:relative; justify-content:center; }.home-add-button { width:72px; height:72px; padding:0; border:1px solid var(--screen-border); border-radius:50%; color:var(--screen-text); background:var(--screen-surface); box-shadow:0 3px 9px rgba(0,0,0,.12); font-size:46px; font-weight:300; line-height:1; }.home-add-caption { margin-top:7px; color:var(--screen-muted); font-size:11px; }.pinned-home-item { display:flex; flex-direction:column; align-items:center; gap:7px; padding:0; border:0; color:var(--screen-text); background:transparent; }.pinned-home-item svg { width:58px; height:58px; padding:13px; box-sizing:border-box; border-radius:50%; color:#fff; background:linear-gradient(145deg,#7aaee0,#4f91d8); }.pinned-home-item strong { font-size:14px; }.pinned-home-item small { color:var(--screen-muted); font-size:10px; }.home-item-change { margin-top:12px; padding:3px 8px; border:0; color:var(--screen-accent); background:transparent; font-size:10px; }.home-picker-backdrop { position:absolute; z-index:3; inset:0; background:rgba(0,0,0,.07); }.home-picker { position:absolute; z-index:4; left:16px; right:16px; top:13px; bottom:13px; display:flex; flex-direction:column; align-items:center; padding:10px; border:1px solid var(--screen-border); border-radius:12px; background:var(--screen-surface); box-shadow:0 8px 20px rgba(0,0,0,.16); }.home-picker > strong { margin-bottom:8px; font-size:13px; }.home-picker > div { display:grid; grid-template-columns:repeat(3,1fr); gap:8px; }.home-picker > div button { display:flex; flex-direction:column; align-items:center; gap:3px; padding:0; border:0; color:var(--screen-text); background:transparent; font-size:8px; }.home-picker svg { width:27px; height:27px; padding:7px; border-radius:50%; color:#fff; background:#639de0; }.picker-close { margin-top:auto; border:0; color:var(--screen-muted); background:transparent; font-size:10px; }
.posture-dashboard { padding:11px 24px 8px; }.posture-dashboard .dashboard-heading { font-size:15px; }.weekly-chart { height:76px; margin:11px 0 8px; }.weekly-bar { width:16px; }.weekly-bar i { width:10px; }.posture-summary { margin-top:12px; padding-top:9px; border-top:1px solid var(--screen-border); }.home-add-button { width:auto; height:auto; border:0; border-radius:0; background:transparent; box-shadow:none; font-size:62px; line-height:.8; }.home-add-caption { margin-top:13px; font-size:12px; }.custom-home-delete { margin-left:auto; width:25px; height:25px; padding:0; border:0; border-radius:50%; color:var(--screen-muted); background:transparent; font-size:23px; line-height:1; }
.device-notice { position:absolute; z-index:10; top:12px; left:50%; display:flex; align-items:center; gap:6px; width:max-content; max-width:220px; padding:8px 12px; border-radius:10px; color:#fff; background:rgba(29,31,34,.9); box-shadow:0 5px 14px rgba(0,0,0,.22); font-size:12px; font-weight:700; transform:translateX(-50%); pointer-events:none; }.device-notice svg { width:16px; height:16px; color:#f0616d; }.device-notice-enter-active,.device-notice-leave-active { transition:opacity .18s ease, transform .18s ease; }.device-notice-enter-from,.device-notice-leave-to { opacity:0; transform:translate(-50%,-8px); }
.lock-action-feedback { position:absolute; z-index:9; inset:0; display:grid; place-items:center; color:#e44754; background:color-mix(in srgb,#e44754 8%,transparent); pointer-events:none; animation:lock-action-flash .72s ease-out both; }.lock-action-feedback svg { width:54px; height:54px; filter:drop-shadow(0 3px 6px rgba(228,71,84,.22)); }@keyframes lock-action-flash { 0%{opacity:0;transform:scale(.82)} 22%{opacity:1;transform:scale(1)} 100%{opacity:0;transform:scale(1.12)} }
.handset-screen.swipe-up .screen-body { animation: swipe-up-feedback var(--screen-swipe-duration) ease-out; }
.handset-screen.swipe-down .screen-body { animation: swipe-down-feedback var(--screen-swipe-duration) ease-out; }
.handset-screen.swipe-left .screen-body { animation: swipe-left-feedback var(--screen-swipe-duration) ease-out; }
.handset-screen.swipe-right .screen-body { animation: swipe-right-feedback var(--screen-swipe-duration) ease-out; }

@keyframes swipe-up-feedback {
  45% { transform: translateY(-13px); opacity: 0.7; }
}
@keyframes swipe-down-feedback {
  45% { transform: translateY(13px); opacity: 0.7; }
}
@keyframes swipe-left-feedback {
  45% { transform: translateX(-18px); opacity: 0.7; }
}
@keyframes swipe-right-feedback {
  45% { transform: translateX(18px); opacity: 0.7; }
}

.settings-screen {
  height: 100%;
  box-sizing: border-box;
  display: grid;
  grid-template-rows: 38px 1fr 15px;
  padding: 7px 14px 8px;
  color: var(--screen-text);
}
.settings-heading {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 1px;
  padding: 0;
}
.settings-heading > span { font-size: 16px; line-height: 18px; font-weight: 800; letter-spacing: 0.3px; }
.settings-pages { position: relative; height:132px; min-height:132px; overflow: hidden; }
.settings-carousel, .settings-carousel :deep(.swiper), .settings-carousel :deep(.swiper-wrapper), .settings-carousel :deep(.swiper-slide) { width:100%; height:100% !important; }
.settings-slide { height: 100% !important; }
.settings-grid {
  height: 100%;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  align-items: center;
  gap: 8px;
}
.settings-tile {
  aspect-ratio: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 5px 3px;
  border: 1px solid var(--screen-border);
  border-radius: 13px;
  color: var(--screen-text);
  background:
    linear-gradient(145deg, color-mix(in srgb, var(--screen-accent) 7%, var(--screen-surface)), var(--screen-surface));
  box-shadow: 0 2px 5px rgba(0,0,0,0.09), inset 0 1px 0 color-mix(in srgb, white 50%, transparent);
  cursor: pointer;
  transition: transform 0.14s ease, background-color 0.14s ease, box-shadow 0.14s ease;
}
.settings-tile svg { width: 30px; height: 30px; color: var(--screen-accent); }
.settings-tile span { max-width: 100%; font-size: 10px; line-height: 13px; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.settings-tile:hover { background: color-mix(in srgb, var(--screen-accent) 13%, var(--screen-surface)); }
.settings-tile:active { transform: scale(0.95); box-shadow: inset 0 2px 5px rgba(0,0,0,0.1); }
.settings-tile:focus-visible { outline: 2px solid var(--screen-accent); outline-offset: 2px; }
.settings-dots { display: flex; align-items: center; justify-content: center; gap: 6px; }
.settings-dots i { width: 5px; height: 5px; border-radius: 50%; background: color-mix(in srgb, var(--screen-muted) 42%, transparent); transition: width 0.18s ease, background-color 0.18s ease; }
.settings-dots i.active { width: 16px; background: var(--screen-accent); }

.settings-detail-screen {
  height: 100%;
  box-sizing: border-box;
  display: grid;
  grid-template-rows: 40px minmax(0, 1fr);
  padding: 6px 14px 12px;
  color: var(--screen-text);
}
.settings-detail-screen > :not(.settings-heading) { min-height:0; overflow:hidden; }
.settings-detail-heading { border-bottom: 1px solid var(--screen-border); }
.user-header-add {
  width: 25px;
  height: 25px;
  display: grid;
  place-items: center;
  margin-left: auto;
  padding: 0;
  border: 1px solid var(--screen-accent);
  border-radius: 50%;
  color: var(--screen-accent);
  background: transparent;
  font-size: 21px;
  font-weight: 300;
  line-height: 1;
}
.user-manager-list {
  position: relative;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  padding-top: 9px;
}
.user-list-carousel, .user-list-slide, .user-list-carousel :deep(.swiper-slide) { width: 100%; height: 100% !important; }
.user-list-carousel :deep(.swiper-wrapper) { height: 100%; }
.user-profile-grid { height: 100%; display: grid; grid-template-columns: repeat(3, 1fr); align-content: center; gap: 12px 10px; }
.user-profile-card {
  min-width: 0;
  aspect-ratio: auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 0;
  border: 0;
  border-radius: 0;
  color: var(--screen-text);
  background: transparent;
  font-size: 10px;
  font-weight: 700;
  overflow: hidden;
}
.user-profile-card.selected .user-avatar {
  box-sizing: border-box;
  border: 3px solid var(--screen-accent);
  box-shadow: inset 0 0 0 2px var(--screen-surface);
}
.user-avatar, .avatar-choice, .action-avatar {
  display: grid;
  place-items: center;
  border-radius: 50%;
  color: #fff;
  background: #78a8d8;
}
.user-avatar { width: 64px; height: 64px; }
.user-avatar svg { width: 42px; height: 42px; }
.avatar-sky .user-avatar, .avatar-choice.avatar-sky, .action-avatar.avatar-sky { background: #6ca8dc; }
.avatar-moss .user-avatar, .avatar-choice.avatar-moss, .action-avatar.avatar-moss { background: #70aa8d; }
.avatar-coral .user-avatar, .avatar-choice.avatar-coral, .action-avatar.avatar-coral { background: #dc8879; }
.avatar-violet .user-avatar, .avatar-choice.avatar-violet, .action-avatar.avatar-violet { background: #9a86d4; }
.user-add-card { color: var(--screen-muted); }
.user-add-icon { width: 64px; height: 64px; display: grid; place-items: center; border: 1.5px dashed currentColor; border-radius: 50%; font-size: 42px; font-weight: 300; line-height: 1; }
.user-list-dots { position: absolute; z-index: 2; bottom: 1px; left: 0; right: 0; display: flex; justify-content: center; gap: 5px; }.user-list-dots i { width: 4px; height: 4px; border-radius: 50%; background: color-mix(in srgb, var(--screen-muted) 45%, transparent); }.user-list-dots i.active { width: 12px; border-radius: 8px; background: var(--screen-accent); }
.scene-manager-list { position: relative; height: 100%; min-height: 0; overflow: hidden; padding-top: 9px; }.scene-list-carousel, .scene-list-slide, .scene-list-carousel :deep(.swiper-wrapper) { width: 100%; height: 100%; }.scene-profile-grid { height: 100%; display: grid; grid-template-columns: repeat(3, 1fr); align-content: center; gap: 10px; }.scene-profile { display: flex; flex-direction: column; align-items: center; gap: 4px; padding:0; border:0; color: var(--screen-text); background:transparent; }.scene-profile-icon { width: 64px; height: 64px; display: grid; place-items: center; border-radius: 50%; color: #fff; background: linear-gradient(145deg, #7aaee0, #4f91d8); }.scene-profile:nth-child(2) .scene-profile-icon { background: linear-gradient(145deg, #7daa91, #4f886c); }.scene-profile:nth-child(3) .scene-profile-icon { background: linear-gradient(145deg, #d79888, #bd6f61); }.scene-profile-icon svg { width: 38px; height: 38px; }.scene-profile strong { font-size: 11px; }.scene-profile small { font-size: 9px; color: var(--screen-muted); }
.scene-info-screen { display:grid; grid-template-columns:66px minmax(0,1fr); align-items:center; gap:12px; height:100%; padding:0 12px; }.scene-info-identity { display:flex; flex-direction:column; align-items:center; gap:6px; min-width:0; }.scene-info-identity .scene-profile-icon { width:56px; height:56px; }.scene-info-identity .scene-profile-icon svg { width:34px; height:34px; }.scene-info-identity strong { max-width:66px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:12px; }.scene-info-values { display:flex; flex-direction:column; gap:5px; min-width:0; }.scene-info-values > div { display:grid; grid-template-columns:34px minmax(0,1fr); align-items:baseline; padding:5px 0; border-bottom:1px solid var(--screen-border); }.scene-info-values span { color:var(--screen-muted); font-size:11px; }.scene-info-values b { color:var(--screen-text); font-size:21px; line-height:1; font-variant-numeric:tabular-nums; white-space:nowrap; }.scene-info-values b em { margin-left:2px; font-size:12px; font-style:normal; }.scene-info-values .scene-info-status { font-size:16px; }.scene-info-values p { margin:0; color:var(--screen-muted); font-size:12px; line-height:1.5; }
.ambient-control-screen { height:100%; padding:12px 17px 8px; display:flex; flex-direction:column; align-items:center; }.ambient-control-top { width:100%; display:flex; align-items:center; justify-content:space-between; font-size:16px; font-weight:700; }.ambient-control-top button { display:flex; align-items:center; gap:5px; padding:4px 7px; border:1px solid var(--screen-border); border-radius:999px; color:var(--screen-muted); background:var(--screen-surface); font-size:10px; }.ambient-control-top button i { width:7px; height:7px; border-radius:50%; background:currentColor; }.ambient-control-top button.on { color:#4f9bf2; }.ambient-preview { position:relative; width:192px; height:28px; margin:19px 0 14px; overflow:hidden; border-radius:999px; background:#171a1b; box-shadow:inset 0 1px 2px rgba(0,0,0,.6); }.ambient-preview::before { content:''; position:absolute; inset:-15px 4px; border-radius:50%; opacity:.12; background:var(--preset-color); filter:blur(10px); }.ambient-preview.on::before { opacity:.9; }.ambient-preview i { position:absolute; z-index:1; left:8px; right:8px; top:12px; height:4px; border-radius:999px; background:#333; }.ambient-preview.on i { background:var(--preset-color); box-shadow:0 0 7px var(--preset-color); }.ambient-preview span { position:absolute; z-index:2; inset:0; display:grid; place-items:center; color:#fff; font-size:10px; font-weight:700; text-shadow:0 1px 3px #000; }.ambient-quick-grid { display:grid; grid-template-columns:repeat(3,1fr); width:100%; gap:13px; }.ambient-quick-grid button,.ambient-preset-card { display:flex; flex-direction:column; align-items:center; gap:5px; padding:0; border:0; color:var(--screen-text); background:transparent; font-size:10px; }.ambient-quick-grid button > span,.ambient-preset-orb { display:grid; place-items:center; width:50px; height:50px; border-radius:50%; color:#fff; background:var(--preset-color); box-shadow:0 3px 8px color-mix(in srgb,var(--preset-color) 42%,transparent); }.ambient-quick-grid svg,.ambient-preset-orb svg { width:28px; height:28px; }.ambient-quick-grid button.active > span { outline:2px solid var(--screen-accent); outline-offset:3px; }.ambient-control-screen > small { margin-top:auto; color:var(--screen-muted); font-size:9px; }.ambient-manager-list { height:100%; display:grid; grid-template-columns:repeat(3,1fr); align-content:center; gap:12px; }.ambient-preset-card strong { font-size:11px; }.ambient-preset-info { height:100%; display:grid; grid-template-columns:68px 1fr; align-content:center; align-items:center; gap:9px 12px; padding:0 12px; }.ambient-preset-info .large { width:58px; height:58px; grid-row:span 2; }.ambient-preset-info > div { display:flex; justify-content:space-between; padding:4px 0; border-bottom:1px solid var(--screen-border); font-size:11px; }.ambient-preset-info > div span { color:var(--screen-muted); }.ambient-preset-info > div b { font-size:16px; }.ambient-preset-info > button { grid-column:1 / -1; padding:7px; border:0; border-radius:8px; color:#fff; background:var(--screen-accent); font-size:11px; }
.ambient-preset-info { grid-template-columns:54px 1fr; gap:5px 10px; padding:3px 12px; }.ambient-preset-info .large { width:46px; height:46px; grid-row:span 3; }.ambient-edit-row { min-height:25px; align-items:center; }.ambient-edit-row aside { display:flex; justify-content:flex-end; gap:4px; }.ambient-edit-row aside button { min-width:21px; height:18px; padding:0 3px; border:1px solid var(--screen-border); border-radius:5px; color:var(--screen-muted); background:var(--screen-surface); font-size:8px; }.ambient-edit-row:first-of-type aside button { width:16px; min-width:16px; padding:0; border-radius:50%; background:var(--preset-color); }.ambient-edit-row aside button.active { outline:1.5px solid var(--screen-accent); outline-offset:1px; color:var(--screen-text); }.ambient-effect-row aside button { min-width:28px; }.ambient-preset-info > button { margin-top:3px; padding:6px; }.scene-light-choice { display:flex !important; align-items:center; gap:7px; padding-top:5px !important; border-bottom:0 !important; }.scene-light-choice > span { margin-right:auto; }.scene-light-choice button { width:14px; height:14px; padding:0; border:1px solid transparent; border-radius:50%; background:var(--preset-color); }.scene-light-choice button.active { outline:1.5px solid var(--screen-accent); outline-offset:2px; }
.user-form-screen { padding: 8px 1px 0; }
.user-form-label { margin: 0 0 5px; color: var(--screen-muted); font-size: 10px; }
.avatar-picker { display: flex; justify-content: space-between; margin-bottom: 10px; }
.avatar-choice { width: 34px; height: 34px; padding: 0; border: 2px solid transparent; }
.avatar-choice svg { width: 23px; height: 23px; }
.avatar-choice.selected { border-color: var(--screen-text); transform: scale(1.08); }
.generated-name { width: 100%; display: flex; align-items: center; justify-content: space-between; padding: 8px 9px; border: 1px solid var(--screen-border); border-radius: 9px; color: var(--screen-text); background: var(--screen-surface); }
.generated-name strong { font-size: 14px; }.generated-name span { color: var(--screen-muted); font-size: 9px; }
.user-form-actions, .user-action-sheet > div { display: flex; gap: 8px; margin-top: 11px; }
.user-form-actions button, .user-action-sheet button { flex: 1; padding: 7px 4px; border: 1px solid var(--screen-border); border-radius: 8px; color: var(--screen-text); background: var(--screen-surface); font-size: 11px; font-weight: 700; }
.user-form-actions .primary { border-color: var(--screen-accent); color: #fff; background: var(--screen-accent); }
.user-action-sheet { display: flex; flex-direction: column; align-items: center; padding-top: 13px; text-align: center; }
.action-avatar { width: 45px; height: 45px; }.action-avatar svg { width: 31px; height: 31px; }
.user-action-sheet strong { margin-top: 5px; font-size: 15px; }.user-action-sheet p { margin: 2px 0 0; color: var(--screen-muted); font-size: 10px; }
.user-action-sheet > div { width: 100%; }.user-action-sheet .danger { border-color: #e69a91; color: #d8564a; }.user-action-sheet button:disabled { opacity: 0.4; }
.user-action-sheet .sheet-cancel { flex: none; width: 100%; margin-top: 7px; color: var(--screen-muted); }
.user-header-actions { display: flex; gap: 4px; margin-left: auto; }
.user-header-actions button { width: 25px; height: 25px; display: grid; place-items: center; padding: 0; border: 0; border-radius: 50%; color: var(--screen-accent); background: color-mix(in srgb, var(--screen-accent) 10%, transparent); font-size: 16px; font-weight: 700; }
.user-info-screen { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 5px; height: calc(100% - 40px); text-align: center; }.user-info-screen strong { font-size: 14px; }.user-info-screen b { color: var(--screen-muted); font-size: 12px; }.bind-link { padding: 0; border: 0; color: var(--screen-accent); background: transparent; font-size: 12px; font-weight: 700; }
.user-bind-screen { display: flex; align-items: center; justify-content: center; gap: 12px; height: calc(100% - 40px); }.qr-code { position: relative; width: 70px; height: 70px; overflow: hidden; border: 4px solid #fff; background: repeating-linear-gradient(90deg, #1c2421 0 5px, #fff 5px 9px), repeating-linear-gradient(#1c2421 0 4px, #fff 4px 8px); box-shadow: 0 0 0 1px var(--screen-border); }.qr-code i { position: absolute; width: 17px; height: 17px; border: 4px solid #1c2421; background: #fff; }.qr-code i:nth-child(1) { top: 2px; left: 2px; }.qr-code i:nth-child(2) { top: 2px; right: 2px; }.qr-code i:nth-child(3) { bottom: 2px; left: 2px; }.bind-methods { width: 98px; display: flex; flex-direction: column; gap: 4px; color: var(--screen-text); font-size: 10px; }.bind-methods strong { font-size: 13px; }.bind-methods span { color: var(--screen-muted); }.bind-methods em { margin-top: 3px; color: var(--screen-muted); font-style: normal; }.bind-methods b { line-height: 1.35; color: var(--screen-accent); font-size: 10px; }
.settings-back {
  width: 38px;
  height: 38px;
  display: inline-grid;
  place-items: center;
  padding: 0;
  border: 0;
  border-radius: 50%;
  color: var(--screen-accent);
  background: transparent;
  cursor: pointer;
}
.settings-back svg { width: 23px; height: 23px; }
.settings-back:hover { color: color-mix(in srgb, var(--screen-accent) 78%, var(--screen-text)); }
.settings-back:active { transform: scale(0.94); }
.settings-back:focus-visible { outline: 2px solid var(--screen-accent); outline-offset: 1px; }
.settings-detail-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 7px;
  text-align: center;
  color: var(--screen-text);
}
.settings-detail-content svg { width: 42px; height: 42px; color: var(--screen-accent); }
.settings-detail-content strong { font-size: 15px; }
.settings-detail-content span { font-size: 10px; color: var(--screen-muted); }

.control-col {
  position: absolute;
  top: 21px;
  width: 80px;
  height: 160px;
  box-sizing: border-box;
  display: grid;
  grid-template-rows: 44px 23px 52px 41px;
  justify-items: center;
  align-items: center;
  background: linear-gradient(180deg, var(--screen-surface) 0%, var(--screen-surface) 88%, var(--screen-surface-soft) 100%);
  border: 1px solid var(--screen-border);
  border-radius: 11px;
  box-shadow: 0 1px 2px rgba(0,0,0,0.12), inset 0 0 0 1px rgba(255,255,255,0.7);
}
.control-height { left: 17px; }
.control-tilt { right: 17px; }
.chevron { font-size: 25px; color: var(--screen-accent); stroke-width: 7; }
.value-label { align-self: end; font-size: 12px; line-height: 18px; font-weight: 600; color: var(--screen-text); }
.value-block { align-self: center; text-align: center; }
.value-num { font-size: 25px; line-height: 27px; font-weight: 800; color: var(--screen-text); letter-spacing: -0.6px; }
.unit { font-size: 11px; line-height: 12px; font-weight: 600; color: var(--screen-text); }
.value-block-angle .value-num { font-size: 23px; letter-spacing: -1px; }

.screen-action {
  display: grid;
  place-items: center;
  width: 58px;
  height: 38px;
  padding: 0;
  border: 0;
  border-radius: 8px;
  background: transparent;
  touch-action: none;
  cursor: pointer;
  transition: background-color 0.12s ease, transform 0.12s ease;
}
.screen-action:hover { background: color-mix(in srgb, var(--screen-accent) 10%, transparent); }
.screen-action:active { transform: scale(0.94); background: color-mix(in srgb, var(--screen-accent) 16%, transparent); }
.screen-action:focus-visible { outline: 2px solid var(--screen-accent); outline-offset: 0; }

.height-active .control-height,
.tilt-active .control-tilt {
  grid-template-rows: 40px 80px 40px;
  border-color: color-mix(in srgb, var(--screen-accent) 45%, var(--screen-border));
  box-shadow: 0 4px 12px color-mix(in srgb, var(--screen-accent) 16%, transparent), inset 0 0 0 1px color-mix(in srgb, var(--screen-accent) 8%, transparent);
}
.hold-feedback {
  align-self: stretch;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
}
.hold-feedback small { font-size: 8px; font-weight: 600; color: var(--screen-muted); }
.hold-pulse {
  position: relative;
  width: 24px;
  height: 24px;
  display: grid;
  place-items: center;
  border: 1px solid color-mix(in srgb, var(--screen-accent) 34%, var(--screen-border));
  border-radius: 50%;
  animation: motion-pulse var(--screen-pulse-duration) ease-in-out infinite;
}
.hold-pulse::before,
.hold-pulse i {
  content: '';
  display: block;
  border-radius: 50%;
  background: var(--screen-accent);
}
.hold-pulse::before { width: 10px; height: 10px; opacity: 0.26; }
.hold-pulse i { position: absolute; width: 4px; height: 4px; }

.motion-readout {
  position: absolute;
  top: 21px;
  width: 198px;
  height: 160px;
  box-sizing: border-box;
  display: grid;
  grid-template-columns: 52px 1fr;
  align-items: center;
  padding: 13px 13px 12px 9px;
  border: 1px solid var(--screen-border);
  border-radius: 11px;
  overflow: hidden;
  color: var(--screen-text);
  background:
    linear-gradient(135deg, color-mix(in srgb, var(--screen-accent) 12%, var(--screen-surface)) 0%, var(--screen-surface) 58%);
  box-shadow: 0 1px 2px rgba(0,0,0,0.11), inset 0 0 0 1px color-mix(in srgb, white 48%, transparent);
}
.height-readout { left: 105px; }
.tilt-readout { left: 17px; }
.motion-readout::after {
  content: '';
  position: absolute;
  right: -30px;
  top: -42px;
  width: 105px;
  height: 105px;
  border: 18px solid color-mix(in srgb, var(--screen-accent) 7%, transparent);
  border-radius: 50%;
}
.travel-graphic {
  height: 108px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  color: var(--screen-accent);
}
.travel-chevron {
  width: 30px;
  height: 24px;
  margin-top: -5px;
  opacity: 0.22;
  animation: travel-up var(--screen-travel-duration) ease-in-out infinite;
}
.travel-chevron svg { width: 30px; height: 30px; }
.travel-chevron:nth-child(2) { animation-delay: 0.15s; }
.travel-chevron:nth-child(3) { animation-delay: 0.3s; }
.direction-down .travel-chevron { animation-name: travel-down; }
.travel-graphic.at-limit .travel-chevron {
  animation-play-state: paused;
  opacity: 0.22;
}
.height-data { position: relative; z-index: 1; min-width: 0; }
.height-caption { display: block; margin-bottom: -2px; font-size: 11px; font-weight: 700; color: var(--screen-muted); }
.height-number { display: flex; align-items: baseline; gap: 4px; white-space: nowrap; }
.height-number strong { font-size: 59px; line-height: 66px; letter-spacing: -3px; font-variant-numeric: tabular-nums; }
.height-number span { font-size: 13px; font-weight: 700; }
.tilt-number { align-items: flex-start; gap: 1px; }
.tilt-number strong { min-width: 60px; }
.tilt-number span {
  align-self: flex-start;
  margin-top: 5px;
  font-size: 32px;
  line-height: 32px;
  letter-spacing: -0.5px;
}

.limit-overlay {
  position: absolute;
  z-index: 5;
  inset: 0;
  box-sizing: border-box;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  padding: 0 13px 10px;
  pointer-events: none;
  background: linear-gradient(0deg, color-mix(in srgb, var(--screen-bg) 92%, transparent) 0 28%, transparent 58%);
}
.limit-card {
  width: 100%;
  height: 43px;
  box-sizing: border-box;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  border: 1px solid color-mix(in srgb, var(--screen-accent) 34%, var(--screen-border));
  border-radius: 10px;
  color: var(--screen-text);
  background: color-mix(in srgb, var(--screen-surface) 94%, var(--screen-accent));
  box-shadow: 0 8px 20px rgba(0,0,0,0.18), inset 0 1px 0 color-mix(in srgb, white 55%, transparent);
}
.limit-card strong { font-size: 17px; line-height: 1; letter-spacing: 0.5px; }
.limit-marker {
  position: relative;
  width: 25px;
  height: 25px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: color-mix(in srgb, var(--screen-accent) 14%, var(--screen-surface));
}
.limit-marker::before,
.limit-marker::after,
.limit-marker i {
  content: '';
  position: absolute;
  display: block;
  background: var(--screen-accent);
  border-radius: 2px;
}
.limit-marker::before { width: 12px; height: 2px; top: 7px; }
.limit-marker::after { width: 8px; height: 2px; top: 12px; opacity: 0.65; }
.limit-marker i { width: 4px; height: 2px; top: 17px; opacity: 0.35; }
.limit-card-enter-active,
.limit-card-leave-active { transition: opacity var(--screen-feedback-duration) ease, transform var(--screen-feedback-duration) ease; }
.limit-card-enter-from,
.limit-card-leave-to { opacity: 0; transform: translateY(7px); }

@keyframes motion-pulse {
  50% { transform: scale(0.82); opacity: 0.58; }
}
@keyframes travel-up {
  0% { transform: translateY(8px); opacity: 0; }
  45% { opacity: 0.9; }
  100% { transform: translateY(-7px); opacity: 0; }
}
@keyframes travel-down {
  0% { transform: translateY(-8px); opacity: 0; }
  45% { opacity: 0.9; }
  100% { transform: translateY(7px); opacity: 0; }
}

.desk-illustration {
  position: absolute;
  left: 102px;
  top: 55px;
  width: 116px;
  height: 92px;
  display: grid;
  place-items: center;
}
.lock-hold-progress { position:absolute; z-index:2; left:50%; top:50%; width:166px; height:166px; transform:translate(-50%,-50%); pointer-events:none; }.lock-hold-progress svg { width:100%; height:100%; overflow:visible; transform:rotate(-90deg); }.lock-hold-progress circle { fill:none; stroke-width:5px; }.lock-progress-track { stroke:color-mix(in srgb,var(--screen-text) 16%,transparent); }.lock-progress-value { stroke:var(--screen-accent); stroke-linecap:round; stroke-dasharray:1; transition:stroke-dashoffset .05s linear; }.handset-screen:has(.lock-status-icon) .lock-progress-value { stroke:#e44754; }
.scene-bind-grid { position: absolute; inset: 4px 20px; z-index: 3; display: grid; grid-template-columns: 82px 1fr 82px; grid-template-rows: 1fr 1fr; pointer-events: none; }.scene-bind-grid > button { width: 78px; height: 78px; align-self: center; justify-self: center; display: grid; place-items: center; padding: 0; border: 1px solid var(--screen-border); border-radius: 50%; color: var(--screen-text); background: var(--screen-surface); pointer-events: auto; box-shadow: 0 3px 7px rgba(0,0,0,.13); }.scene-bind-grid > button:nth-child(1){grid-column:1;grid-row:1}.scene-bind-grid > button:nth-child(2){grid-column:1;grid-row:2}.scene-bind-grid > button:nth-child(3){grid-column:3;grid-row:1}.scene-bind-grid > button:nth-child(4){grid-column:3;grid-row:2}.scene-bind-grid > button svg { width: 33px; height: 33px; color: var(--screen-accent); }.scene-more { display:grid; place-items:center; width:100%; height:100%; font-size:46px; line-height:1; letter-spacing:0; transform:translateY(-2px); }.scene-bind-dialog { position: absolute; inset: 20px 35px; z-index: 4; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 11px; padding: 12px; border: 1px solid var(--screen-border); border-radius: 12px; background: var(--screen-surface); box-shadow: 0 8px 20px rgba(0,0,0,.16); text-align: center; pointer-events:auto; }.scene-bind-dialog strong { font-size: 14px; }.scene-bind-dialog div { display:flex; gap:6px; }.scene-bind-dialog button { padding: 6px 8px; border:1px solid var(--screen-border); border-radius:7px; color:var(--screen-text); background:var(--screen-bg); font-size:10px; }.scene-bind-dialog .scene-posture-actions { flex-wrap:wrap; justify-content:center; gap:7px; }.scene-bind-dialog .scene-posture-actions button { min-width:44px; font-size:11px; }
.scene-bind-backdrop { position:absolute; z-index:3; inset:0; pointer-events:auto; }.scene-pick-carousel { width: 100%; }.scene-pick-grid { display:grid; grid-template-columns:repeat(3,1fr); justify-items:center; align-items:start; gap:8px; width:100%; }.scene-bind-dialog .scene-pick-grid button { display:flex; flex-direction:column; align-items:center; gap:4px; min-width:0; padding:0; border:0; color:var(--screen-text); background:transparent; font-size:9px; }.scene-pick-icon { width:44px; height:44px; display:grid; place-items:center; border-radius:50%; color:#fff; background:linear-gradient(145deg,#7aaee0,#4f91d8); }.scene-pick-grid button:nth-child(2) .scene-pick-icon { background:linear-gradient(145deg,#7daa91,#4f886c); }.scene-pick-grid button:nth-child(3) .scene-pick-icon { background:linear-gradient(145deg,#d79888,#bd6f61); }.scene-pick-grid svg { width:26px; height:26px; }.scene-pick-empty { grid-column:1/-1; color:var(--screen-muted); font-size:10px; }
.desk-illustration img {
  display: block;
  width: 112px;
  height: 81px;
  object-fit: contain;
  user-select: none;
  filter: saturate(0.96) contrast(1.02);
}
.desk-scene-hotspot { position: absolute; z-index: 1; inset: 0; padding: 0; border: 0; background: transparent; cursor: pointer; }

/* NFC 感应区 */
.nfc-zone {
  position: absolute;
  z-index: 2;
  /* 参考图 NFC 图形中心约 (1550,406)，换算后为外壳内 (653,172)。 */
  left: 599px;
  top: 112px;
  width: 108px;
  height: 120px;
  display: grid;
  place-items: center;
  padding: 0;
  border: 0;
  border-radius: 34px;
  background: transparent;
  cursor: pointer;
  color: rgba(213, 216, 215, 0.82);
  user-select: none;
  transition: color 0.18s ease, background-color 0.18s ease, filter 0.18s ease;
}
.nfc-zone:hover {
  color: rgba(242, 244, 243, 0.96);
  background: rgba(255,255,255,0.025);
  filter: drop-shadow(0 0 5px rgba(255,255,255,0.12));
}
.nfc-zone:focus-visible {
  outline: 3px solid rgba(91, 155, 255, 0.78);
  outline-offset: 4px;
}
.nfc-symbol {
  width: 92px;
  height: 92px;
}
</style>
