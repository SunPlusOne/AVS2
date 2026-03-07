<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { adminLogin, adminUploadModel, getAdminLogs } from '@/api/avs'
import { useAdminStore } from '@/stores/admin'

const admin = useAdminStore()

const password = ref('')
const loggingIn = ref(false)

const modelAlgorithmId = ref('avsegformer')
const modelName = ref('AVSegFormer')
const modelVersion = ref('v1')
const modelDescription = ref('占位权重，待上传训练后模型')
const modelInputSize = ref('384x384')
const modelEnabled = ref(true)
const weightFile = ref<File | null>(null)
const uploading = ref(false)

const logs = ref<{ ts: string; level: string; message: string }[]>([])
const loadingLogs = ref(false)

const authed = computed(() => admin.token.length > 0)

async function onLogin() {
  loggingIn.value = true
  try {
    const { token } = await adminLogin(password.value)
    admin.setToken(token)
    ElMessage.success('登录成功')
    password.value = ''
  } catch (e: any) {
    ElMessage.error(e?.message ?? '登录失败')
  } finally {
    loggingIn.value = false
  }
}

function onPickWeight(e: Event) {
  const input = e.target as HTMLInputElement
  const f = input.files?.[0]
  if (!f) return
  weightFile.value = f
}

async function onUploadModel() {
  if (!authed.value) {
    ElMessage.warning('请先登录')
    return
  }
  if (!weightFile.value) {
    ElMessage.warning('请选择 .pth 权重文件')
    return
  }
  uploading.value = true
  try {
    await adminUploadModel(admin.token, {
      algorithm_id: modelAlgorithmId.value,
      name: modelName.value,
      version: modelVersion.value,
      description: modelDescription.value,
      input_size: modelInputSize.value,
      enabled: modelEnabled.value,
      weight_file: weightFile.value,
    })
    ElMessage.success('上传成功')
  } catch (e: any) {
    ElMessage.error(e?.message ?? '上传失败')
  } finally {
    uploading.value = false
  }
}

async function onRefreshLogs() {
  if (!authed.value) {
    ElMessage.warning('请先登录')
    return
  }
  loadingLogs.value = true
  try {
    logs.value = await getAdminLogs(admin.token, { limit: 200 })
  } catch (e: any) {
    ElMessage.error(e?.message ?? '加载日志失败')
  } finally {
    loadingLogs.value = false
  }
}
</script>

<template>
  <div class="grid gap-5">
    <div>
      <div class="page-heading">管理员后台</div>
      <div class="page-subheading">模型权重管理与日志查询</div>
    </div>

    <div class="grid gap-5 lg:grid-cols-2">
      <div class="avs-card">
        <div class="avs-card-title">管理员登录</div>
        <div class="avs-card-desc">通过 /api/admin/login 获取 JWT 并存入浏览器</div>

        <div class="mt-4 grid gap-3">
          <el-input v-model="password" type="password" placeholder="管理员密码" show-password />
          <div class="flex gap-2">
            <el-button class="avs-btn-primary" :loading="loggingIn" @click="onLogin">登录</el-button>
            <el-button v-if="authed" class="avs-btn-secondary" @click="admin.clear()">退出</el-button>
          </div>
          <div class="token-preview">当前 token：{{ authed ? admin.token.slice(0, 24) + '…' : '未登录' }}</div>
        </div>
      </div>

      <div class="avs-card">
        <div class="avs-card-title">模型权重上传</div>
        <div class="avs-card-desc">上传 .pth 并注册算法元数据</div>

        <div class="mt-4 grid gap-3">
          <el-input v-model="modelAlgorithmId" placeholder="algorithm_id (avsegformer/vct/combo/...)" />
          <el-input v-model="modelName" placeholder="name" />
          <el-input v-model="modelVersion" placeholder="version" />
          <el-input v-model="modelInputSize" placeholder="input_size (224x224/384x384)" />
          <el-input v-model="modelDescription" type="textarea" :rows="3" placeholder="description" />
          <el-switch v-model="modelEnabled" class="model-switch" active-text="启用" inactive-text="禁用" />
          <input
            class="weight-input"
            type="file"
            accept=".pth"
            @change="onPickWeight"
          />
          <div v-if="weightFile" class="weight-hint">已选择：{{ weightFile.name }}</div>
          <el-button class="avs-btn-primary" :loading="uploading" @click="onUploadModel">上传并注册</el-button>
        </div>
      </div>
    </div>

    <div class="avs-card">
      <div class="flex items-end justify-between gap-3">
        <div>
          <div class="avs-card-title">系统日志</div>
          <div class="avs-card-desc">支持按最新 N 条获取</div>
        </div>
        <div class="flex gap-2">
          <el-button class="avs-btn-secondary" :loading="loadingLogs" @click="onRefreshLogs">刷新</el-button>
        </div>
      </div>

      <div class="logs-panel">
        <div v-if="logs.length === 0" class="logs-empty">暂无日志</div>
        <div v-for="(l, idx) in logs" :key="idx" class="logs-row">
          <span class="logs-time mono-text">{{ l.ts }}</span>
          <span class="logs-level">[{{ l.level }}]</span>
          <span class="ml-2">{{ l.message }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.token-preview,
.weight-hint {
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.6;
}

.model-switch {
  width: fit-content;
}

.weight-input {
  display: block;
  width: 100%;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  background: var(--bg-hover);
  color: var(--text-primary);
  font-size: 14px;
  padding: 10px 12px;
  transition: all 0.15s ease;
}

.weight-input:hover {
  border-color: var(--primary-border);
}

.weight-input::file-selector-button {
  margin-right: 10px;
  border: none;
  border-radius: 8px;
  padding: 8px 12px;
  background: var(--info-soft);
  color: var(--text-primary);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.logs-panel {
  margin-top: 16px;
  max-height: 360px;
  overflow: auto;
  border: 1px solid var(--border-default);
  border-radius: 12px;
  background: var(--bg-hover);
  padding: 12px;
}

.logs-empty {
  color: var(--text-secondary);
  font-size: 12px;
}

.logs-row {
  color: var(--text-primary);
  font-size: 12px;
  line-height: 1.7;
}

.logs-time,
.logs-level {
  color: var(--text-secondary);
}
</style>

