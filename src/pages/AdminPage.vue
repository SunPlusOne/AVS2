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
  <div class="grid gap-4">
    <div>
      <div class="text-lg font-semibold">管理员后台</div>
      <div class="mt-1 text-sm text-zinc-400">模型权重管理与日志查询（占位实现，可接入真实 JWT/权限）</div>
    </div>

    <div class="grid gap-4 lg:grid-cols-2">
      <div class="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4">
        <div class="text-sm font-semibold">管理员登录</div>
        <div class="mt-1 text-xs text-zinc-400">默认通过 /api/admin/login 获取 JWT 并存入浏览器</div>

        <div class="mt-4 grid gap-3">
          <el-input v-model="password" type="password" placeholder="管理员密码" show-password />
          <div class="flex gap-2">
            <el-button type="primary" :loading="loggingIn" @click="onLogin">登录</el-button>
            <el-button v-if="authed" @click="admin.clear()">退出</el-button>
          </div>
          <div class="text-xs text-zinc-400">当前 token：{{ authed ? admin.token.slice(0, 24) + '…' : '未登录' }}</div>
        </div>
      </div>

      <div class="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4">
        <div class="text-sm font-semibold">模型权重上传</div>
        <div class="mt-1 text-xs text-zinc-400">上传 .pth 并注册算法元数据（实际推理替换在后端模型层）</div>

        <div class="mt-4 grid gap-3">
          <el-input v-model="modelAlgorithmId" placeholder="algorithm_id (avsegformer/vct/combo/...)" />
          <el-input v-model="modelName" placeholder="name" />
          <el-input v-model="modelVersion" placeholder="version" />
          <el-input v-model="modelInputSize" placeholder="input_size (224x224/384x384)" />
          <el-input v-model="modelDescription" type="textarea" :rows="3" placeholder="description" />
          <el-switch v-model="modelEnabled" active-text="启用" inactive-text="禁用" />
          <input
            class="block w-full text-sm text-zinc-200 file:mr-3 file:rounded-md file:border-0 file:bg-zinc-800 file:px-3 file:py-2 file:text-sm file:text-zinc-100 hover:file:bg-zinc-700"
            type="file"
            accept=".pth"
            @change="onPickWeight"
          />
          <div v-if="weightFile" class="text-xs text-zinc-400">已选择：{{ weightFile.name }}</div>
          <el-button type="primary" :loading="uploading" @click="onUploadModel">上传并注册</el-button>
        </div>
      </div>
    </div>

    <div class="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4">
      <div class="flex items-end justify-between gap-3">
        <div>
          <div class="text-sm font-semibold">系统日志</div>
          <div class="mt-1 text-xs text-zinc-400">支持按最新 N 条获取（占位实现）</div>
        </div>
        <div class="flex gap-2">
          <el-button :loading="loadingLogs" @click="onRefreshLogs">刷新</el-button>
        </div>
      </div>

      <div class="mt-4 max-h-[360px] overflow-auto rounded-lg border border-zinc-800 bg-black p-3">
        <div v-if="logs.length === 0" class="text-xs text-zinc-500">暂无日志</div>
        <div v-for="(l, idx) in logs" :key="idx" class="text-xs text-zinc-300">
          <span class="text-zinc-500">{{ l.ts }}</span>
          <span class="ml-2 text-zinc-400">[{{ l.level }}]</span>
          <span class="ml-2">{{ l.message }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

