import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import HomePage from '@/pages/HomePage.vue'
import TasksPage from '@/pages/TasksPage.vue'
import TaskDetailPage from '@/pages/TaskDetailPage.vue'
import ModelComparePage from '@/pages/ModelComparePage.vue'
import AdminPage from '@/pages/AdminPage.vue'
import LoginPage from '@/pages/LoginPage.vue'
import RegisterPage from '@/pages/RegisterPage.vue'
import { useAuthStore } from '@/stores/auth'

// 定义路由配置
const routes: RouteRecordRaw[] = [
  {
    path: '/',
    redirect: '/login',
  },
  {
    path: '/workbench',
    name: 'workbench',
    component: HomePage,
    meta: { requiresAuth: true, roles: ['admin', 'user'] },
  },
  {
    path: '/tasks',
    name: 'tasks',
    component: TasksPage,
    meta: { requiresAuth: true, roles: ['admin', 'user'] },
  },
  {
    path: '/compare',
    name: 'compare',
    component: ModelComparePage,
    meta: { requiresAuth: true, roles: ['admin', 'user'] },
  },
  {
    path: '/tasks/:taskId',
    name: 'taskDetail',
    component: TaskDetailPage,
    meta: { requiresAuth: true, roles: ['admin', 'user'] },
  },
  {
    path: '/admin',
    name: 'admin',
    component: AdminPage,
    meta: { requiresAuth: true, roles: ['admin'] },
  },
  {
    path: '/login',
    name: 'login',
    component: LoginPage,
    meta: { guestOnly: true },
  },
  {
    path: '/register',
    name: 'register',
    component: RegisterPage,
    meta: { guestOnly: true },
  },
]

// 创建路由实例
const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  const hasToken = !!auth.token
  const role = auth.role
  const isLoggedIn = hasToken && !!role

  if (to.meta.requiresAuth && !isLoggedIn) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }

  const roles = Array.isArray(to.meta.roles) ? to.meta.roles as string[] : []
  if (roles.length > 0 && (!role || !roles.includes(role))) {
    return isLoggedIn ? '/workbench' : '/login'
  }

  if (to.meta.guestOnly && isLoggedIn) {
    return role === 'admin' ? '/admin' : '/workbench'
  }

  return true
})

export default router
