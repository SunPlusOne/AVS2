<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getTask, cancelTask } from '@/api/avs'
import * as TaskProgressCardModule from '@/components/TaskProgressCard.vue'
import * as ResultViewerCardModule from '@/components/ResultViewerCard.vue'
import { useTasksStore } from '@/stores/tasks'
import type { TaskProgress } from '@/types/contracts'

const TaskProgressCard = (TaskProgressCardModule as any).default ?? TaskProgressCardModule
const ResultViewerCard = (ResultViewerCardModule as any).default ?? ResultViewerCardModule

const route = useRoute()
const store = useTasksStore()

const loading = ref(false)
const task = ref<TaskProgress | null>(null)

const taskId = computed(() => String(route.params.taskId ?? ''))

async function refresh() {
  if (!taskId.value) return
  loading.value = true
  try {
    const t = await getTask(taskId.value)
    task.value = t
    store.upsert(t)
  } catch (e: any) {
    ElMessage.error(e?.message ?? '加载任务失败')
  } finally {
    loading.value = false
  }
}

async function onCancel() {
  if (!task.value) return
  try {
    await cancelTask(task.value.task_id)
    await refresh()
    ElMessage.success('已取消')
  } catch (e: any) {
    ElMessage.error(e?.message ?? '取消失败')
  }
}

onMounted(async () => {
  const cached = store.byId.get(taskId.value)
  if (cached) task.value = cached
  await refresh()
})
</script>

<template>
  <div class="grid gap-4">
    <div class="flex items-end justify-between gap-3">
      <div>
        <div class="text-lg font-semibold">任务详情</div>
        <div class="mt-1 text-sm text-slate-500">task_id：{{ taskId }}</div>
      </div>
      <div class="flex gap-2">
        <el-button :loading="loading" @click="refresh">刷新</el-button>
      </div>
    </div>

    <div class="grid gap-4 lg:grid-cols-3">
      <div class="lg:col-span-1">
        <TaskProgressCard :task="task" :on-cancel="onCancel" />
      </div>
      <div class="lg:col-span-2">
        <ResultViewerCard :task-id="task?.task_id ?? null" :status="task?.status" />
      </div>
    </div>
  </div>
</template>

