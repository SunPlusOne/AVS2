<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getAdminLogs, listAdminUsers, updateAdminUserRole } from '@/api/avs'
import { useAuthStore } from '@/stores/auth'
import type { AdminUserProfile, UserRole } from '@/types/contracts'

const auth = useAuthStore()

const logs = ref<{ ts: string; level: string; message: string }[]>([])
const loadingLogs = ref(false)
const users = ref<AdminUserProfile[]>([])
const loadingUsers = ref(false)
const roleSavingUserId = ref<number | null>(null)

const benchmarkRows = [
  { model: 'AVSegFormer', s4_metric: '78.7% / 87.9%', ms3_metric: '54.0% / 64.5%', avis_metric: '--', params: '47M', speed: '~50ms/帧' },
  { model: 'MAVS-Net', s4_metric: '83.65% / 97.45%', ms3_metric: '61.92% / 74.75%', avis_metric: '--', params: '47M', speed: '~50ms/帧' },
  { model: 'VCT', s4_metric: '86.2% / 93.4%', ms3_metric: '67.6% / 81.4%', avis_metric: '--', params: '52M', speed: '~80ms/帧' },
  { model: 'COMBO', s4_metric: '84.7% / 91.9%', ms3_metric: '59.2% / 71.2%', avis_metric: '--', params: '68M', speed: '~100ms/帧' },
  { model: 'AVIS', s4_metric: '-', ms3_metric: '-', avis_metric: '42.78 / 61.73 / 40.57', params: '-', speed: '-' },
]

const authed = computed(() => auth.isLoggedIn && auth.isAdmin)

async function onRefreshLogs() {
  if (!authed.value) {
    ElMessage.warning('请先登录')
    return
  }
  loadingLogs.value = true
  try {
    logs.value = await getAdminLogs(auth.token, { limit: 200 })
  } catch (e: any) {
    ElMessage.error(e?.message ?? '加载日志失败')
  } finally {
    loadingLogs.value = false
  }
}

async function onRefreshUsers() {
  if (!authed.value) {
    ElMessage.warning('请先登录')
    return
  }
  loadingUsers.value = true
  try {
    users.value = await listAdminUsers(auth.token)
  } catch (e: any) {
    ElMessage.error(e?.message ?? '加载用户失败')
  } finally {
    loadingUsers.value = false
  }
}

function formatDateTime(v?: string | null): string {
  if (!v) return '-'
  const d = new Date(v)
  if (Number.isNaN(d.getTime())) return v
  return d.toLocaleString()
}

async function onToggleUserRole(user: AdminUserProfile) {
  if (!authed.value) {
    ElMessage.warning('请先登录')
    return
  }
  if (roleSavingUserId.value != null) {
    return
  }

  const nextRole: UserRole = user.role === 'admin' ? 'user' : 'admin'
  roleSavingUserId.value = user.id
  try {
    const res = await updateAdminUserRole(auth.token, user.id, nextRole)
    users.value = users.value.map((u) => (u.id === res.user.id ? res.user : u))
    ElMessage.success(`已将 ${user.username} 设置为 ${nextRole === 'admin' ? '管理员' : '普通用户'}`)
  } catch (e: any) {
    ElMessage.error(e?.message ?? '修改角色失败')
  } finally {
    roleSavingUserId.value = null
  }
}

onMounted(async () => {
  if (!authed.value) return
  await Promise.all([onRefreshUsers(), onRefreshLogs()])
})
</script>

<template>
  <div class="grid gap-5">
    <div>
      <div class="page-heading">管理员后台</div>
      <div class="page-subheading">系统日志查询</div>
    </div>

    <div class="avs-card">
      <div class="avs-card-title">基准性能（AVSBench + AVIS 官方指标）</div>
      <div class="avs-card-desc">AVIS 行使用官方仓库 checkpoints 指标（FSLA / HOTA / mAP），其任务定义与 AVSBench 不同。</div>

      <el-table class="avs-table benchmark-table" :data="benchmarkRows" size="small" style="width: 100%">
        <el-table-column prop="model" label="模型" min-width="140" />
        <el-table-column prop="s4_metric" label="S4 mIoU / F-score" min-width="170" />
        <el-table-column prop="ms3_metric" label="MS3 mIoU / F-score" min-width="170" />
        <el-table-column prop="avis_metric" label="AVIS(FSLA/HOTA/mAP)" min-width="210" />
        <el-table-column prop="params" label="参数量" min-width="120" />
        <el-table-column prop="speed" label="推理速度" min-width="140" />
      </el-table>
    </div>

    <div class="avs-card">
      <div class="flex items-end justify-between gap-3">
        <div>
          <div class="avs-card-title">用户管理</div>
          <div class="avs-card-desc">查看全部用户并调整用户权限</div>
        </div>
        <el-button class="avs-btn-secondary" :loading="loadingUsers" @click="onRefreshUsers">刷新用户</el-button>
      </div>

      <el-table class="avs-table users-table" :data="users" size="small" style="width: 100%">
        <el-table-column prop="id" label="ID" min-width="80" />
        <el-table-column prop="username" label="用户名" min-width="180" />
        <el-table-column label="角色" min-width="140">
          <template #default="scope">
            <el-tag :type="scope.row.role === 'admin' ? 'danger' : 'info'">
              {{ scope.row.role === 'admin' ? '管理员' : '普通用户' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" min-width="220">
          <template #default="scope">{{ formatDateTime(scope.row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="最后登录" min-width="220">
          <template #default="scope">{{ formatDateTime(scope.row.last_login) }}</template>
        </el-table-column>
        <el-table-column label="操作" min-width="160" fixed="right">
          <template #default="scope">
            <el-button
              class="avs-btn-secondary"
              size="small"
              :loading="roleSavingUserId === scope.row.id"
              @click="onToggleUserRole(scope.row)"
            >
              {{ scope.row.role === 'admin' ? '设为普通用户' : '设为管理员' }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
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

.benchmark-table {
  margin-top: 12px;
}

.users-table {
  margin-top: 12px;
}
</style>

