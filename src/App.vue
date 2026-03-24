<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const isAuthPage = computed(() => route.path === '/login' || route.path === '/register')

async function onLogout() {
  auth.clear()
  await router.replace('/login')
}
</script>

<template>
  <div class="app-shell">
    <header v-if="!isAuthPage" class="app-header">
      <div class="app-header-inner">
        <div class="brand">
          <div class="brand-mark">
            AVS
          </div>
          <div>
            <div class="brand-title">AVS System</div>
            <div class="brand-subtitle">视频发声物体分割</div>
          </div>
        </div>

        <nav class="app-nav">
          <RouterLink to="/workbench" class="nav-link">工作台</RouterLink>
          <RouterLink to="/tasks" class="nav-link">任务中心</RouterLink>
          <RouterLink to="/compare" class="nav-link">模型对比</RouterLink>
          <RouterLink v-if="auth.isAdmin" to="/admin" class="nav-link">管理员</RouterLink>
          <a href="#" class="nav-link" @click.prevent="onLogout">退出</a>
        </nav>
      </div>
    </header>

    <main :class="['app-main', { 'auth-main': isAuthPage }]">
      <router-view />
    </main>
  </div>
</template>
