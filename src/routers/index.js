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
      path: '/admin/version-release',
      component: () => import('@/views/adminViews/page-version-release.vue'),
      meta: { adminOnly: true }
    },
    {
      path: '/admin/users',
      component: () => import('@/views/adminViews/page-users.vue'),
      meta: { adminOnly: true }
    },
    {
      path: '/admin/permissions',
      component: () => import('@/views/adminViews/page-permissions.vue'),
      meta: { adminOnly: true }
    },
    {
      path: '/admin/login-logs',
      component: () => import('@/views/adminViews/page-login-logs.vue'),
      meta: { authorOnly: true }
    },
    {
      path: '/product',
      component: () => import('@/views/productViews/page-product.vue'),
      meta: { permission: 'product:view' }
    },
    {
      path: '/shipping',
      component: () => import('@/views/shippingViews/page-shipping.vue'),
      meta: { permission: 'shipping:view' }
    },
    {
      path: '/data-mgmt',
      component: () => import('@/views/dataMgmtViews/page-data-mgmt.vue'),
      meta: { permission: 'shipping:view' }
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
  const isAdmin = roles.includes('admin')

  if (to.meta?.authorOnly) {
    return user.username === 'author' ? true : '/index'
  }
  if (to.meta?.adminOnly) {
    return isAdmin ? true : '/index'
  }

  const required = to.meta?.permission
  if (!required) return true
  if (isAdmin || perms.includes(required)) return true
  return '/index'
})

export default router