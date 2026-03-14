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
      path: '/product',
      component: () => import('@/views/productViews/page-product.vue')
    },
  ]
})

export default router  