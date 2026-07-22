import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/login',
    name: 'Login',
    redirect: (to) => ({ path: '/welcome', query: { ...to.query, entry: 'core' } }),
    meta: { title: '登录', requiresAuth: false, hideVisionPet: true },
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('@/views/RegisterPage.vue'),
    meta: { title: '注册', requiresAuth: false, hideVisionPet: true },
  },
  {
    path: '/welcome',
    name: 'VisionJourney',
    component: () => import('@/views/VisionJourneyPage.vue'),
    meta: { title: 'Vision', requiresAuth: false, hideVisionPet: true },
  },
  {
    path: '/',
    component: () => import('@/components/layout/MainLayout.vue'),
    redirect: '/chat',
    meta: { requiresAuth: true },
    children: [
      {
        path: 'chat',
        name: 'Chat',
        component: () => import('@/views/ChatPage.vue'),
        meta: { title: '智能对话', icon: 'ChatDotRound' },
      },
      {
        path: 'training',
        name: 'Training',
        component: () => import('@/views/TrainingPage.vue'),
        meta: {
          title: '模型训练',
          icon: 'Cpu',
          description: '启动 YOLOv11 训练任务，实时观察 loss、mAP 与运行状态。',
        },
      },
      {
        path: 'datasets',
        name: 'Datasets',
        component: () => import('@/views/DatasetManagementPage.vue'),
        meta: {
          title: '数据集版本',
          icon: 'Files',
          description: '登记数据集元数据和类别映射，冻结后形成不可变版本，并记录训练与模型谱系。',
        },
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
      {
        path: 'settings',
        name: 'Settings',
        component: () => import('@/views/SettingsPage.vue'),
        meta: { title: '账号设置', icon: 'Setting' },
      },
      {
        path: 'checkout',
        name: 'CustomerCheckout',
        component: () => import('@/views/CustomerCheckoutPage.vue'),
        meta: { title: '用户结算端', icon: 'ShoppingCart' },
      },
      {
        path: 'prices',
        name: 'PriceManagement',
        component: () => import('@/views/PriceManagementPage.vue'),
        meta: {
          title: '价目表管理',
          icon: 'PriceTag',
          description: '选择数据集版本后，只管理该版本中已有商品的价格。',
        },
      },
      {
        path: 'checkout/history',
        name: 'CheckoutHistory',
        component: () => import('@/views/CheckoutHistoryPage.vue'),
        meta: { title: '结算历史' },
      },
      {
        path: 'checkout/payment',
        name: 'CustomerPayment',
        component: () => import('@/views/CustomerPaymentPage.vue'),
        meta: { title: '确认付款' },
      },
    ],
  },
  {
    path: '/mock-pay/:token',
    name: 'MockPayment',
    component: () => import('@/views/MockPaymentPage.vue'),
    meta: { title: '模拟付款', requiresAuth: false },
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: { path: '/welcome', query: { entry: 'core' } },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export function resolveAuthNavigation(to, token = localStorage.getItem('vp_agent_token')) {
  const requiresAuth = to.matched.some((record) => record.meta.requiresAuth !== false)

  if (requiresAuth && !token) {
    return { path: '/welcome', query: { redirect: to.fullPath, entry: 'awakening' } }
  }

  if (
    to.name === 'VisionJourney' &&
    token &&
    to.query.entry !== 'core' &&
    to.query.entry !== 'replay'
  ) {
    return { path: '/welcome', query: { ...to.query, entry: 'core' } }
  }

  if ((to.path === '/login' || to.path === '/register') && token) {
    return '/'
  }

  return true
}

router.beforeEach((to) => {
  document.title = to.meta.title
    ? `${to.meta.title} - VisionPay Agent Platform`
    : 'VisionPay Agent Platform'

  return resolveAuthNavigation(to)
})

export default router
