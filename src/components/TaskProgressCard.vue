<script setup lang="ts">
import type { TaskProgress } from '@/types/contracts'

defineProps<{
  task: TaskProgress | null
  onCancel?: () => void
}>()

function statusLabel(status?: string) {
  if (!status) return '—'
  if (status === 'queued') return '排队中'
  if (status === 'running') return '运行中'
  if (status === 'completed') return '已完成'
  if (status === 'failed') return '失败'
  if (status === 'canceled') return '已取消'
  return status
}

function statusTagType(status?: string): 'success' | 'warning' | 'danger' | 'info' {
  if (status === 'completed') return 'success'
  if (status === 'running') return 'warning'
  if (status === 'failed') return 'danger'
  return 'info'
}
</script>

<template>
  <div class="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4">
    <div class="flex items-start justify-between gap-3">
      <div>
        <div class="text-sm font-semibold">任务状态</div>
        <div v-if="task" class="mt-1 text-xs text-zinc-400">task_id：{{ task.task_id }}</div>
      </div>
      <div>
        <el-tag v-if="task" :type="statusTagType(task.status)">{{ statusLabel(task.status) }}</el-tag>
        <el-tag v-else type="info">未开始</el-tag>
      </div>
    </div>

    <div class="mt-4">
      <el-progress :percentage="task?.progress ?? 0" />
      <div class="mt-2 flex items-center justify-between text-xs text-zinc-400">
        <div>
          <span v-if="task?.current_frame != null && task?.total_frames != null">
            {{ task.current_frame }} / {{ task.total_frames }} 帧
          </span>
          <span v-else>—</span>
        </div>
        <div>
          <span v-if="task?.algorithm">算法：{{ task.algorithm }}</span>
        </div>
      </div>
      <div v-if="task?.message" class="mt-2 rounded-md bg-zinc-950/60 px-3 py-2 text-xs text-zinc-300">
        {{ task.message }}
      </div>
    </div>

    <div class="mt-4 flex gap-2">
      <el-button
        v-if="task && (task.status === 'queued' || task.status === 'running')"
        @click="onCancel?.()"
      >
        取消任务
      </el-button>
    </div>
  </div>
</template>
