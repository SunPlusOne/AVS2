<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { getTask } from '@/api/avs'
import { useTasksStore } from '@/stores/tasks'

const router = useRouter()
const store = useTasksStore()

const rows = computed(() => store.items)

function goDetail(taskId: string) {
  router.push(`/tasks/${encodeURIComponent(taskId)}`)
}

function statusLabel(status: string) {
  if (status === 'queued') return '排队中'
  if (status === 'running') return '运行中'
  if (status === 'completed') return '已完成'
  if (status === 'failed') return '失败'
  if (status === 'canceled') return '已取消'
  return status
}

function statusClass(status: string) {
  if (status === 'running') return 'status-warning'
  if (status === 'completed') return 'status-success'
  if (status === 'failed') return 'status-danger'
  return 'status-idle'
}

onMounted(async () => {
  const pending = store.items.filter((t) => t.status === 'queued' || t.status === 'running')
  for (const item of pending) {
    try {
      const latest = await getTask(item.task_id)
      store.upsert(latest)
    } catch {
      // Keep local snapshot when the task cannot be fetched.
    }
  }
})
</script>

<template>
  <div class="grid gap-5">
    <div class="flex items-end justify-between gap-3">
      <div>
        <div class="page-heading">任务中心</div>
        <div class="page-subheading">本地保存历史任务列表（浏览器 localStorage）</div>
      </div>
      <div class="flex gap-2">
        <el-button class="avs-btn-secondary" @click="store.clear()">清空历史</el-button>
      </div>
    </div>

    <div class="avs-card">
      <el-table class="avs-table" :data="rows" size="small" style="width: 100%" row-key="task_id">
        <el-table-column label="task_id" min-width="240">
          <template #default="scope">
            <span class="mono-text task-id-cell">{{ scope.row.task_id }}</span>
          </template>
        </el-table-column>
        <el-table-column label="算法" min-width="120">
          <template #default="scope">
            <span class="text-main">{{ scope.row.algorithm ?? '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" min-width="120">
          <template #default="scope">
            <span class="status-pill" :class="statusClass(scope.row.status)">
              {{ statusLabel(scope.row.status) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="进度" min-width="120">
          <template #default="scope">
            <span class="mono-text progress-cell">{{ scope.row.progress }}%</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" min-width="140">
          <template #default="scope">
            <div class="table-actions">
              <el-button class="avs-btn-primary table-btn" @click="goDetail(scope.row.task_id)">查看</el-button>
              <el-button class="avs-btn-secondary table-btn" @click="store.remove(scope.row.task_id)">删除</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<style scoped>
.text-main {
  color: var(--text-primary);
}

.task-id-cell {
  color: var(--text-secondary);
  font-size: 12px;
}

.progress-cell {
  color: var(--primary);
  font-size: 13px;
  font-weight: 600;
}

.status-pill {
  display: inline-flex;
  align-items: center;
  border-radius: var(--radius-sm);
  padding: 3px 10px;
  font-size: 12px;
  font-weight: 500;
}

.status-idle {
  background: var(--neutral-light);
  color: var(--text-secondary);
}

.status-warning {
  background: var(--warning-light);
  color: var(--warning);
}

.status-success {
  background: var(--success-light);
  color: var(--success);
}

.status-danger {
  background: var(--danger-light);
  color: var(--danger);
}

.table-actions {
  display: flex;
  gap: 8px;
}

.table-btn {
  height: 32px;
  padding: 0 12px;
  font-size: 13px;
  border-radius: 8px;
}
</style>

