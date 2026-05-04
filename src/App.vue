<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowDown } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const isAuthPage = computed(() => route.path === '/login' || route.path === '/register')
const roleLabel = computed(() => (auth.role === 'admin' ? '管理员' : '用户'))
const accountText = computed(() => {
  const username = auth.username || '未命名账号'
  return `hi，${roleLabel.value}${username}`
})

async function onLogout() {
  auth.clear()
  await router.replace('/login')
}

async function onSwitchAccount() {
  auth.clear()
  await router.replace('/login')
  ElMessage.success('已退出当前账号，请登录其他账号')
}

async function onAccountCommand(command: string) {
  if (command === 'logout') {
    await onLogout()
    return
  }
  if (command === 'switch') {
    await onSwitchAccount()
  }
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
          <el-dropdown trigger="hover" @command="onAccountCommand">
            <button type="button" class="nav-link account-trigger">
              <span class="account-text">{{ accountText }}</span>
              <el-icon class="account-caret"><ArrowDown /></el-icon>
            </button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item disabled>{{ accountText }}</el-dropdown-item>
                <el-dropdown-item divided command="logout">退出登录</el-dropdown-item>
                <el-dropdown-item command="switch">切换账号</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </nav>
      </div>
    </header>

    <main :class="['app-main', { 'auth-main': isAuthPage }]">
      <router-view />
    </main>
  </div>
</template>

<style scoped>
.account-trigger {
  border: none;
  background: transparent;
  cursor: pointer;
}

.account-text {
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.account-caret {
  margin-left: 6px;
  font-size: 12px;
}
</style>
