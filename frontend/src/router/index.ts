import { createRouter, createWebHistory } from 'vue-router'

import { getAccessToken } from '@/api/tokens'

const router = createRouter({
  history: createWebHistory(),
  scrollBehavior(to, from, savedPosition) {
    if (savedPosition) return savedPosition
    if (to.path === from.path) return {}
    return { top: 0 }
  },
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('@/pages/LoginPage.vue'),
      meta: { public: true, tabbar: false },
    },
    {
      path: '/',
      redirect: '/feed',
    },
    {
      path: '/feed',
      name: 'feed',
      component: () => import('@/pages/FeedPage.vue'),
      meta: { tabbar: true },
    },
    {
      path: '/reports/:id',
      name: 'report',
      component: () => import('@/pages/ReportDetailPage.vue'),
      meta: { tabbar: false },
    },
    {
      path: '/authors',
      name: 'authors',
      component: () => import('@/pages/AuthorsPage.vue'),
      meta: { tabbar: true },
    },
    {
      path: '/watchlist',
      name: 'watchlist',
      component: () => import('@/pages/WatchlistPage.vue'),
      meta: { tabbar: true },
    },
    {
      path: '/stocks/:code',
      name: 'stock',
      component: () => import('@/pages/StockDetailPage.vue'),
      meta: { tabbar: false },
    },
    {
      path: '/settings',
      name: 'settings',
      component: () => import('@/pages/SettingsPage.vue'),
      meta: { tabbar: true },
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/feed',
    },
  ],
})

router.beforeEach((to) => {
  const hasToken = Boolean(getAccessToken())
  if (!to.meta.public && !hasToken) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (to.name === 'login' && hasToken) {
    return { name: 'feed' }
  }
  return true
})

export default router
