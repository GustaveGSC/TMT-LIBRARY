import { createRouter, createWebHashHistory } from 'vue-router'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    {
      path: '/',
      redirect: '/login'
    },
    {
      path: '/login',
      component: () => import('@/views/loginViews/page-login.vue')
    },
    {
      path: '/download',
      component: () => import('@/views/DownloadPage.vue')
    },
    {
      path: '/index',
      component: () => import('@/views/indexViews/page-index.vue')
    },
    {
      // Electron 已停止支持的冻结功能，后端仍是唯一保留的 admin 角色鉴权，未纳入权限重做
      path: '/admin/version-release',
      component: () => import('@/views/adminViews/page-version-release.vue'),
      meta: { adminOnly: true }
    },
    {
      path: '/admin/users',
      component: () => import('@/views/adminViews/page-users.vue'),
      meta: { permission: 'account:users:view' }
    },
    {
      path: '/admin/permissions',
      component: () => import('@/views/adminViews/page-permissions.vue'),
      meta: { permission: 'account:roles:view' }
    },
    {
      path: '/admin/login-logs',
      component: () => import('@/views/adminViews/page-login-logs.vue'),
      meta: { permission: 'developer:analytics:view' }
    },
    {
      path: '/product',
      component: () => import('@/views/productViews/page-product.vue'),
      meta: { permission: 'product:view' }
    },
    {
      path: '/shipping',
      component: () => import('@/views/shippingViews/page-shipping.vue'),
      meta: { permission: 'shipping:view' },
      children: [
        { path: '', component: () => import('@/views/shippingViews/ShippingDashboard.vue') },
        { path: 'orders', component: () => import('@/views/shippingViews/ShippingTable.vue') },
        { path: 'imports', component: () => import('@/views/shippingViews/ShippingImportsPage.vue') },
        { path: 'settings', component: () => import('@/views/shippingViews/ShippingSettingsPage.vue') },
        { path: 'maintenance', component: () => import('@/views/shippingViews/ShippingMaintenancePage.vue') },
      ]
    },
    {
      // 旧数据管理入口迁入发货数据域，兼容跳转保留至少一个发布周期后可移除
      path: '/data-mgmt',
      redirect: '/shipping/imports'
    },
    {
      path: '/aftersale',
      component: () => import('@/views/aftersaleViews/page-aftersale.vue'),
      meta: { permission: 'aftersale:view' }
    },
    {
      path: '/aftersale/cases',
      component: () => import('@/views/aftersaleViews/AftersaleCasesPage.vue'),
      meta: { permission: 'aftersale:view' }
    },
    {
      path: '/rd-tools',
      component: () => import('@/views/rdToolsViews/page-rd-tools.vue'),
      meta: { permission: 'rd:view' }
    },
    {
      path: '/general-tools',
      component: () => import('@/views/generalToolsViews/page-general-tools.vue'),
    },
  ]
})

const SESSION_DURATION = 8 * 60 * 60 * 1000 // 8小时

function isSessionExpired() {
  const loginTime = localStorage.getItem('login_time')
  if (!loginTime) return true
  return Date.now() - Number(loginTime) > SESSION_DURATION
}

function clearSession() {
  localStorage.removeItem('user')
  localStorage.removeItem('login_time')
}

// 路由权限守卫
router.beforeEach((to) => {
  // 非登录页且已有登录态，检查是否过期
  if (to.path !== '/login' && localStorage.getItem('user')) {
    if (isSessionExpired()) {
      clearSession()
      return '/login'
    }
  }

  const user = JSON.parse(localStorage.getItem('user') || '{}')
  const roles = user.roles || []
  const perms = user.permissions || []

  // 冻结的 version-release 页面：Electron 停止支持后未纳入权限重做，后端仍按 admin 角色名鉴权
  if (to.meta?.adminOnly) {
    return roles.includes('admin') ? true : '/index'
  }

  const required = to.meta?.permission
  if (!required) return true
  if (perms.includes(required)) return true
  return '/index'
})

export default router