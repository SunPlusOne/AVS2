import { createRouter, createWebHistory } from 'vue-router'
import HomePage from '@/pages/HomePage.vue'
import TasksPage from '@/pages/TasksPage.vue'
import TaskDetailPage from '@/pages/TaskDetailPage.vue'
import ModelComparePage from '@/pages/ModelComparePage.vue'
import AdminPage from '@/pages/AdminPage.vue'

// 定义路由配置
const routes = [
  {
    path: '/',
    name: 'home',
    component: HomePage,
  },
  {
    path: '/tasks',
    name: 'tasks',
    component: TasksPage,
  },
  {
    path: '/compare',
    name: 'compare',
    component: ModelComparePage,
  },
  {
    path: '/tasks/:taskId',
    name: 'taskDetail',
    component: TaskDetailPage,
  },
  {
    path: '/admin',
    name: 'admin',
    component: AdminPage,
  },
]

// 创建路由实例
const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
