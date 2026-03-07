<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import VideoUploadCard from '@/components/VideoUploadCard.vue'
import TaskProgressCard from '@/components/TaskProgressCard.vue'
import ResultViewerCard from '@/components/ResultViewerCard.vue'
import { createTask, cancelTask, getTask } from '@/api/avs'
import { getWsBaseUrl } from '@/api/http'
import { useAlgorithmsStore } from '@/stores/algorithms'
import { useTasksStore } from '@/stores/tasks'
import type { AlgorithmId, TaskProgress, UploadResponse } from '@/types/contracts'

const algorithms = useAlgorithmsStore()
const tasksStore = useTasksStore()

const uploaded = ref<UploadResponse | null>(null)
const originalFile = ref<File | null>(null)
const selectedAlgorithm = ref<AlgorithmId>('avsegformer')
const currentTask = ref<TaskProgress | null>(null)

const starting = ref(false)
const wsRef = ref<WebSocket | null>(null)
let pollTimer: number | null = null

const canStart = computed(() => !!uploaded.value && !starting.value)

function onUploaded(payload: { file: File; res: UploadResponse }) {
  uploaded.value = payload.res
  originalFile.value = payload.file
}

function cleanupRealtime() {
  if (pollTimer != null) {
    window.clearInterval(pollTimer)
    pollTimer = null
  }
  if (wsRef.value) {
    wsRef.value.close()
    wsRef.value = null
  }
}

function attachPolling(taskId: string) {
  if (pollTimer != null) window.clearInterval(pollTimer)
  pollTimer = window.setInterval(async () => {
    try {
      const t = await getTask(taskId)
      currentTask.value = t
      tasksStore.upsert(t)
      if (t.status === 'completed' || t.status === 'failed' || t.status === 'canceled') cleanupRealtime()
    } catch {
      return
    }
  }, 1500)
}

function attachWebSocket(taskId: string) {
  const wsBase = getWsBaseUrl()
  const ws = new WebSocket(`${wsBase}/ws/tasks/${encodeURIComponent(taskId)}/progress`)
  wsRef.value = ws

  ws.onmessage = (ev) => {
    try {
      const t = JSON.parse(String(ev.data)) as TaskProgress
      currentTask.value = t
      tasksStore.upsert(t)
      if (t.status === 'completed' || t.status === 'failed' || t.status === 'canceled') cleanupRealtime()
    } catch {
      return
    }
  }
  ws.onerror = () => {
    attachPolling(taskId)
  }
  ws.onclose = () => {
    if (currentTask.value && (currentTask.value.status === 'queued' || currentTask.value.status === 'running')) {
      attachPolling(taskId)
    }
  }
}

async function startTask() {
  if (!uploaded.value) return
  starting.value = true
  cleanupRealtime()
  try {
    const { task_id } = await createTask({ file_id: uploaded.value.file_id, algorithm: selectedAlgorithm.value })
    currentTask.value = {
      task_id,
      status: 'queued',
      progress: 0,
      algorithm: selectedAlgorithm.value,
    }
    tasksStore.upsert(currentTask.value)
    attachWebSocket(task_id)
  } catch (e: any) {
    ElMessage.error(e?.message ?? '启动任务失败')
  } finally {
    starting.value = false
  }
}

async function onCancel() {
  if (!currentTask.value) return
  try {
    await cancelTask(currentTask.value.task_id)
    ElMessage.success('已取消')
    const t = await getTask(currentTask.value.task_id)
    currentTask.value = t
    tasksStore.upsert(t)
    cleanupRealtime()
  } catch (e: any) {
    ElMessage.error(e?.message ?? '取消失败')
  }
}

onMounted(async () => {
  await algorithms.refresh()
  const first = algorithms.enabledItems[0]
  if (first) selectedAlgorithm.value = first.id
})

onBeforeUnmount(() => {
  cleanupRealtime()
})
</script>

<template>
  <div class="grid gap-6 lg:grid-cols-3">
    <div class="grid gap-4 lg:col-span-1">
      <VideoUploadCard
        @uploaded="onUploaded"
      />

      <div class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <div class="text-sm font-semibold">算法选择</div>
        <div class="mt-1 text-xs text-slate-500">AVSegFormer / VCT / COMBO（可由管理员上传权重后启用）</div>
        <div class="mt-4">
          <el-select class="w-full" v-model="selectedAlgorithm" filterable placeholder="请选择算法">
            <el-option
              v-for="a in algorithms.items"
              :key="a.id"
              :label="`${a.name}${a.enabled ? '' : '（不可用）'}`"
              :value="a.id"
              :disabled="!a.enabled"
            />
          </el-select>
          <div v-if="algorithms.error" class="mt-2 text-xs text-red-300">{{ algorithms.error }}</div>
        </div>
        <div class="mt-4 flex gap-2">
          <el-button type="primary" :disabled="!canStart" :loading="starting" @click="startTask">启动推理</el-button>
        </div>
      </div>

      <TaskProgressCard :task="currentTask" :on-cancel="onCancel" />
    </div>

    <div class="grid gap-4 lg:col-span-2">
      <ResultViewerCard
        :task-id="currentTask?.task_id ?? null"
        :status="currentTask?.status"
        :original-file="originalFile"
      />

      <div class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <div class="text-sm font-semibold">说明</div>
        <div class="mt-2 text-sm text-slate-600">
          当前版本的后端推理为占位实现：支持任务流转、进度推送与结果下载；待你上传训练好的权重后，可在后端模型层
          替换推理实现而不改动 API 与前端。
        </div>
      </div>
    </div>
  </div>
</template>
