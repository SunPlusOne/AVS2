<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { adminLogin, userLogin } from '@/api/avs'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()

const username = ref('')
const password = ref('')
const loading = ref(false)

function getLanding(role: string) {
  return role === 'admin' ? '/admin' : '/workbench'
}

async function onLogin() {
  if (!username.value.trim()) {
    ElMessage.warning('请输入用户名')
    return
  }
  if (!password.value) {
    ElMessage.warning('请输入密码')
    return
  }

  loading.value = true
  try {
    let token = ''
    let role: 'admin' | 'user' = 'user'

    try {
      const adminRes = await adminLogin(username.value.trim(), password.value)
      token = adminRes.token
      role = adminRes.role
    } catch {
      const userRes = await userLogin(username.value.trim(), password.value)
      token = userRes.token
      role = userRes.role
    }

    auth.setAuth(token)
    ElMessage.success('登录成功')
    await router.replace(getLanding(role))
  } catch (e: any) {
    ElMessage.error(e?.message ?? '登录失败，请检查用户名或密码')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="auth-page">
    <div class="avs-card auth-card">
      <div class="page-heading">
        登录系统
      </div>
      <div class="page-subheading">
        统一入口：管理员与普通用户共用账号密码登录
      </div>

      <div class="mt-5 grid gap-3">
        <el-input
          v-model="username"
          placeholder="用户名"
          @keyup.enter="onLogin"
        />
        <el-input
          v-model="password"
          type="password"
          show-password
          placeholder="密码"
          @keyup.enter="onLogin"
        />
        <el-button
          class="avs-btn-primary"
          :loading="loading"
          @click="onLogin"
        >
          登录
        </el-button>
        <RouterLink
          to="/register"
          class="auth-link"
        >
          没有账号？去注册
        </RouterLink>
      </div>
    </div>
  </div>
</template>

<style scoped>
.auth-page {
  min-height: 100dvh;
  display: grid;
  place-items: center;
  padding: 24px 16px;
  position: relative;
  background-image: linear-gradient(to bottom, rgba(255, 255, 255, 0.16), rgba(255, 255, 255, 0.06)), url('/AVSbackground.png');
  background-size: cover;
  background-position: center top;
  background-repeat: no-repeat;
}

.auth-card {
  width: min(460px, 92vw);
  background: rgba(255, 255, 255, 0.88);
  backdrop-filter: blur(6px);
  border: 1px solid rgba(255, 255, 255, 0.35);
}

.auth-link {
  color: var(--primary);
  font-size: 13px;
  text-decoration: none;
}

.auth-link:hover {
  text-decoration: underline;
}

@media (max-width: 768px) {
  .auth-page {
    padding: 16px 12px;
  }
}
</style>
