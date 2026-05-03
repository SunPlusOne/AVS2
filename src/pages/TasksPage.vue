<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { getTask } from '@/api/avs'
import { useTasksStore } from '@/stores/tasks'
import type { TaskProgress, TaskStatus } from '@/types/contracts'

const router = useRouter()
const store = useTasksStore()

const filterAlgorithm = ref<'all' | string>('all')
const filterStatus = ref<'all' | TaskStatus>('all')

const rows = computed(() => store.items)

const algorithmOptions = computed(() => {
  const set = new Set<string>()
  for (const row of rows.value) {
    if (row.algorithm) set.add(row.algorithm)
  }
  return Array.from(set)
})

const filteredRows = computed(() => {
  return rows.value.filter((row) => {
    const byAlgorithm = filterAlgorithm.value === 'all' || row.algorithm === filterAlgorithm.value
    const byStatus = filterStatus.value === 'all' || row.status === filterStatus.value
    return byAlgorithm && byStatus
  })
})

const summary = computed(() => {
  const total = rows.value.length
  const jfValues = rows.value
    .map((r) => r.metrics?.jf_mean)
    .filter((v): v is number => v != null && Number.isFinite(v))

  const avgJf = jfValues.length > 0 ? jfValues.reduce((sum, v) => sum + v, 0) / jfValues.length : null

  const algoCounter = new Map<string, number>()
  for (const item of rows.value) {
    const key = item.algorithm ?? '未知'
    algoCounter.set(key, (algoCounter.get(key) ?? 0) + 1)
  }

  let topAlgo = '—'
  let topCount = 0
  for (const [name, count] of algoCounter.entries()) {
    if (count > topCount) {
      topAlgo = name
      topCount = count
    }
  }

  return {
    total,
    avgJf,
    topAlgo,
  }
})

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

function sceneLabel(task: TaskProgress) {
  if (task.algorithm === 'avis') return '-'
  const scene = task.resolved_scene ?? task.scene
  if (scene === 'single_source') return '单个物体发声'
  if (scene === 'multi_source') return '多个物体同时发声'
  return '—'
}

function formatTime(ts?: string) {
  if (!ts) return '—'
  const d = new Date(ts)
  if (Number.isNaN(d.getTime())) return ts
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function formatJf(value?: number) {
  if (value == null || !Number.isFinite(value)) return '—'
  return `${value.toFixed(2)}%`
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
        <div class="page-subheading">历史任务管理、筛选与结果复查</div>
      </div>
      <div class="flex gap-2">
        <el-button class="avs-btn-secondary" @click="store.clear()">清空历史</el-button>
      </div>
    </div>

    <div class="summary-grid">
      <div class="summary-card">
        <div class="summary-label">总任务数</div>
        <div class="summary-value">{{ summary.total }}</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">平均 J&F</div>
        <div class="summary-value">{{ summary.avgJf == null ? '—' : `${summary.avgJf.toFixed(2)}%` }}</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">最常用算法</div>
        <div class="summary-value">{{ summary.topAlgo }}</div>
      </div>
    </div>

    <div class="avs-card">
      <div class="filter-row">
        <el-select v-model="filterAlgorithm" class="avs-select filter-select" popper-class="avs-select-dropdown">
          <el-option label="全部算法" value="all" />
          <el-option v-for="algo in algorithmOptions" :key="algo" :label="algo" :value="algo" />
        </el-select>

        <el-select v-model="filterStatus" class="avs-select filter-select" popper-class="avs-select-dropdown">
          <el-option label="全部状态" value="all" />
          <el-option label="排队中" value="queued" />
          <el-option label="运行中" value="running" />
          <el-option label="已完成" value="completed" />
          <el-option label="失败" value="failed" />
          <el-option label="已取消" value="canceled" />
        </el-select>
      </div>

      <el-table class="avs-table" :data="filteredRows" size="small" style="width: 100%" row-key="task_id">
        <el-table-column label="文件名" min-width="190">
          <template #default="scope">
            <span class="text-main">{{ scope.row.filename ?? '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="算法" min-width="110">
          <template #default="scope">
            <span class="text-main">{{ scope.row.algorithm ?? '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="场景" min-width="150">
          <template #default="scope">
            <span class="text-main">{{ sceneLabel(scope.row) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="时间" min-width="170">
          <template #default="scope">
            <span class="text-main">{{ formatTime(scope.row.created_at) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="J&F" min-width="110">
          <template #default="scope">
            <span class="mono-text progress-cell">{{ formatJf(scope.row.metrics?.jf_mean) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="状态" min-width="110">
          <template #default="scope">
            <span class="status-pill" :class="statusClass(scope.row.status)">
              {{ statusLabel(scope.row.status) }}
            </span>
          </template>
        </el-table-column>

        <el-table-column label="操作" min-width="180">
          <template #default="scope">
            <div class="table-actions">
              <el-button class="avs-btn-primary table-btn" @click="goDetail(scope.row.task_id)">重新查看结果</el-button>
              <el-button class="avs-btn-secondary table-btn" @click="store.remove(scope.row.task_id)">删除</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<style scoped>
.summary-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.summary-card {
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  padding: 14px 16px;
  box-shadow: var(--shadow-card);
}

.summary-label {
  color: var(--text-secondary);
  font-size: 12px;
}

.summary-value {
  margin-top: 4px;
  color: var(--text-primary);
  font-size: 22px;
  line-height: 1.3;
  font-weight: 700;
}

.filter-row {
  display: flex;
  gap: 10px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.filter-select {
  width: 190px;
}

.text-main {
  color: var(--text-primary);
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

@media (max-width: 900px) {
  .summary-grid {
    grid-template-columns: 1fr;
  }
}
</style>
