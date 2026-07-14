import { createRouter, createWebHistory } from 'vue-router'

const isCheckoutApp = import.meta.env.MODE === 'checkout'

const developerRoutes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/LoginPage.vue'),
    meta: { title: '登录', requiresAuth: false },
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('@/views/RegisterPage.vue'),
    meta: { title: '注册', requiresAuth: false },
  },
  {
    path: '/',
    component: () => import('@/components/layout/MainLayout.vue'),
    redirect: '/detection',
    meta: { requiresAuth: true },
    children: [
      {
        path: 'chat',
        name: 'Chat',
        component: () => import('@/views/ChatPage.vue'),
        meta: { title: '智能对话', icon: 'ChatDotRound' },
      },
      {
        path: 'detection',
        name: 'Detection',
        component: () => import('@/views/DetectionPage.vue'),
        meta: { title: '检测工作台', icon: 'Camera' },
      },
      {
        path: 'training',
        name: 'Training',
        component: () => import('@/views/TrainingPage.vue'),
        meta: { title: '模型训练', icon: 'Cpu' },
      },
      {
        path: 'history',
        name: 'History',
        component: () => import('@/views/HistoryPage.vue'),
        meta: { title: '历史记录', icon: 'Clock' },
      },
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('@/views/DashboardPage.vue'),
        meta: { title: '数据看板', icon: 'DataAnalysis' },
      },
    ],
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/login',
  },
]

const checkoutRoutes = [
  {
    path: '/checkout',
    name: 'CustomerCheckout',
    component: () => import('@/views/CustomerCheckoutPage.vue'),
    meta: { title: '自助结算', requiresAuth: false },
  },
  {
    path: '/checkout/payment',
    name: 'CustomerPayment',
    component: () => import('@/views/CustomerPaymentPage.vue'),
    meta: { title: '确认付款', requiresAuth: false },
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/checkout',
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes: isCheckoutApp ? checkoutRoutes : developerRoutes,
})

router.beforeEach((to) => {
  document.title = to.meta.title
    ? `${to.meta.title} - VisionPay Agent Platform`
    : 'VisionPay Agent Platform'

  if (isCheckoutApp) return true

  const token = localStorage.getItem('vp_agent_token')
  const requiresAuth = to.matched.some((record) => record.meta.requiresAuth !== false)

  if (requiresAuth && !token) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }

  if ((to.path === '/login' || to.path === '/register') && token) {
    return '/'
  }

  return true
})

export default router
