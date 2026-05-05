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
      path: '/index',
      component: () => import('@/views/indexViews/page-index.vue')
    },
    { 
      path: '/admin/version-release', 
      component: () => import('@/views/adminViews/page-version-release.vue') 
    },
    { 
      path: '/admin/users',       
      component: () => import('@/views/adminViews/page-users.vue') 
    },
    {
      path: '/admin/permissions',
      component: () => import('@/views/adminViews/page-permissions.vue')
    },
    {
      path: '/admin/login-logs',
      component: () => import('@/views/adminViews/page-login-logs.vue')
    },
    {
      path: '/product',
      component: () => import('@/views/productViews/page-product.vue')
    },
    {
      path: '/shipping',
      component: () => import('@/views/shippingViews/page-shipping.vue')
    },
    {
      path: '/data-mgmt',
      component: () => import('@/views/dataMgmtViews/page-data-mgmt.vue')
    },
    {
      path: '/aftersale',
      component: () => import('@/views/aftersaleViews/page-aftersale.vue')
    },
    {
      path: '/rd-tools',
      component: () => import('@/views/rdToolsViews/page-rd-tools.vue'),
      meta: { permission: 'rd:view' }
    },
  ]
})

// 路由权限守卫
router.beforeEach((to) => {
  const required = to.meta?.permission
  if (!required) return true
  const user = JSON.parse(localStorage.getItem('user') || '{}')
  const roles = user.roles || []
  const perms = user.permissions || []
  if (roles.includes('admin') || perms.includes(required)) return true
  return '/index'
})

export default router