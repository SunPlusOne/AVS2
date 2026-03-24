<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { userRegister } from '@/api/avs'

const router = useRouter()

const username = ref('')
const password = ref('')
const confirmPassword = ref('')
const loading = ref(false)

async function onRegister() {
  const u = username.value.trim()
  if (!u) {
    ElMessage.warning('请输入用户名')
    return
  }
  if (u.toLowerCase() === 'admin') {
    ElMessage.warning('管理员账号由后台创建，请使用其他用户名')
    return
  }
  if (password.value.length < 6) {
    ElMessage.warning('密码长度至少为 6 位')
    return
  }
  if (password.value !== confirmPassword.value) {
    ElMessage.warning('两次输入的密码不一致')
    return
  }

  loading.value = true
  try {
    await userRegister(u, password.value)
    ElMessage.success('注册成功，请登录')
    await router.replace('/login')
  } catch (e: any) {
    ElMessage.error(e?.message ?? '注册失败')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="auth-page">
    <div class="avs-card auth-card">
      <div class="page-heading">
        用户注册
      </div>
      <div class="page-subheading">
        仅普通用户可自助注册，管理员由后台直接创建
      </div>

      <div class="mt-5 grid gap-3">
        <el-input
          v-model="username"
          placeholder="用户名"
          @keyup.enter="onRegister"
        />
        <el-input
          v-model="password"
          type="password"
          show-password
          placeholder="密码（至少 6 位）"
          @keyup.enter="onRegister"
        />
        <el-input
          v-model="confirmPassword"
          type="password"
          show-password
          placeholder="确认密码"
          @keyup.enter="onRegister"
        />
        <el-button
          class="avs-btn-primary"
          :loading="loading"
          @click="onRegister"
        >
          注册
        </el-button>
        <RouterLink
          to="/login"
          class="auth-link"
        >
          已有账号？去登录
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
