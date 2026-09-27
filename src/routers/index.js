import { createRouter, createWebHashHistory } from 'vue-router'
import http from '@/api/http'

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
      // 登录后强制补充部门/工号；见下方 beforeEach 里的强制跳转逻辑
      path: '/complete-profile',
      component: () => import('@/views/loginViews/page-complete-profile.vue')
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
      path: '/admin/dev-tasks',
      component: () => import('@/views/adminViews/page-dev-tasks.vue'),
      meta: { permission: 'developer:tasks:view' }
    },
    {
      path: '/product',
      component: () => import('@/views/productViews/page-product.vue'),
      meta: { permission: 'product:view' }
    },
    {
      path: '/material',
      component: () => import('@/views/materialViews/page-material.vue'),
      meta: { permission: 'material:view' }
    },
    {
      path: '/shipping',
      component: () => import('@/views/shippingViews/page-shipping.vue'),
      meta: { permission: 'shipping:view' },
      children: [
        { path: '', component: () => import('@/views/shippingViews/ShippingDashboard.vue') },
        { path: 'orders', component: () => import('@/views/shippingViews/ShippingTable.vue') },
        {
          path: 'imports',
          component: () => import('@/views/shippingViews/ShippingImportsPage.vue'),
          meta: { permission: 'shipping:edit' },
        },
        {
          path: 'settings',
          component: () => import('@/views/shippingViews/ShippingSettingsPage.vue'),
          meta: { permission: 'shipping:edit' },
        },
        {
          path: 'maintenance',
          component: () => import('@/views/shippingViews/ShippingMaintenancePage.vue'),
          meta: { permission: 'shipping:edit' },
        },
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
      path: '/trade-tools',
      component: () => import('@/views/tradeToolsViews/page-trade-tools.vue'),
      meta: { permission: 'trade:view' }
    },
    {
      path: '/general-tools',
      component: () => import('@/views/generalToolsViews/page-general-tools.vue'),
    },
    {
      path: '/lab',
      component: () => import('@/views/labViews/page-lab.vue'),
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

// 本地 8 小时计时只是前端估算，不代表后端 Cookie 真的还有效（账号被禁用/权限变更/被强制下线
// 都会让 token_version 立刻失效，与本地计时无关）。收藏夹直接打开深层路由这种场景下，壳组件
// 本身往往不发请求（比如 page-shipping.vue），要等子组件异步请求失败才会 401 跳转，用户会先
// 看到一个没有数据的空壳页面。所以在应用启动后的第一次导航时，主动向后端确认一次会话是否有效
// （GET /api/account/me），无效则直接跳登录页；只做一次，避免每次路由切换都多一次网络请求。
let authChecked = false

// 路由权限守卫
router.beforeEach(async (to) => {
  // 非登录页且已有登录态，检查是否过期
  if (to.path !== '/login' && localStorage.getItem('user')) {
    if (isSessionExpired()) {
      clearSession()
      return '/login'
    }
    if (!authChecked) {
      authChecked = true
      try {
        const res = await http.get('/api/account/me')
        if (res.success && res.data) {
          localStorage.setItem('user', JSON.stringify(res.data))
        } else {
          clearSession()
          return '/login'
        }
      } catch {
        clearSession()
        return '/login'
      }
    }
  }

  const user = JSON.parse(localStorage.getItem('user') || '{}')
  const roles = user.roles || []
  const perms = user.permissions || []

  // 强制补充资料：部门/工号缺失时（老账号在这次上线前没有这两项数据，或全新账号还没填过），
  // 除登录页/补充资料页本身外一律拦到 /complete-profile；填完后 update_my_profile 会回写
  // localStorage.user，下一次导航这里就通过了。admin/author 是账号保护类特殊账号，不参与这套
  // 业务流程（很多场景下是运维/初始化用的账号，不对应真实"部门/工号"），豁免。
  const isProtectedAccount = user.username === 'admin' || user.username === 'author'
  if (!isProtectedAccount && user.id && (!user.department_id || !user.employee_no)) {
    if (to.path !== '/complete-profile' && to.path !== '/login') return '/complete-profile'
  } else if (to.path === '/complete-profile' && (isProtectedAccount || (user.department_id && user.employee_no))) {
    // admin/author 豁免，或已经填过资料，都不需要停留在这个页面
    return '/index'
  }

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