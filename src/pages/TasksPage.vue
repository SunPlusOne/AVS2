<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
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
</script>

<template>
  <div class="grid gap-4">
    <div class="flex items-end justify-between gap-3">
      <div>
        <div class="text-lg font-semibold">任务中心</div>
        <div class="mt-1 text-sm text-slate-500">本地保存历史任务列表（浏览器 localStorage）</div>
      </div>
      <div class="flex gap-2">
        <el-button @click="store.clear()">清空历史</el-button>
      </div>
    </div>

    <div class="rounded-2xl border border-slate-200 bg-white p-3 shadow-sm">
      <el-table :data="rows" size="small" style="width: 100%" row-key="task_id">
        <el-table-column prop="task_id" label="task_id" min-width="220" />
        <el-table-column label="算法" min-width="120">
          <template #default="scope">
            <span class="text-slate-700">{{ scope.row.algorithm ?? '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" min-width="120">
          <template #default="scope">
            <el-tag>
              {{ statusLabel(scope.row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="进度" min-width="120">
          <template #default="scope">
            <span class="text-slate-700">{{ scope.row.progress }}%</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" min-width="140">
          <template #default="scope">
            <el-button size="small" type="primary" @click="goDetail(scope.row.task_id)">查看</el-button>
            <el-button size="small" @click="store.remove(scope.row.task_id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

