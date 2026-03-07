<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import * as VideoUploadCardModule from '@/components/VideoUploadCard.vue'
import * as TaskProgressCardModule from '@/components/TaskProgressCard.vue'
import * as ResultViewerCardModule from '@/components/ResultViewerCard.vue'
import { createTask, cancelTask, getTask } from '@/api/avs'
import { getWsBaseUrl } from '@/api/http'
import { useAlgorithmsStore } from '@/stores/algorithms'
import { useTasksStore } from '@/stores/tasks'
import type { AlgorithmId, TaskProgress, UploadResponse } from '@/types/contracts'

const VideoUploadCard = (VideoUploadCardModule as any).default ?? VideoUploadCardModule
const TaskProgressCard = (TaskProgressCardModule as any).default ?? TaskProgressCardModule
const ResultViewerCard = (ResultViewerCardModule as any).default ?? ResultViewerCardModule

const algorithms = useAlgorithmsStore()
const tasksStore = useTasksStore()

const uploaded = ref<UploadResponse | null>(null)
const originalFile = ref<File | null>(null)
const selectedAlgorithm = ref<AlgorithmId>('combo')
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
  const preferred = algorithms.enabledItems.find((a) => a.id === 'combo') ?? algorithms.enabledItems[0]
  if (preferred) selectedAlgorithm.value = preferred.id
})

onBeforeUnmount(() => {
  cleanupRealtime()
})
</script>

<template>
  <div class="grid gap-5 lg:grid-cols-3">
    <div class="grid gap-5 lg:col-span-1">
      <VideoUploadCard
        @uploaded="onUploaded"
      />

      <div class="avs-card">
        <div class="avs-card-title">算法选择</div>
        <div class="avs-card-desc">当前已接入 COMBO（部分权重）；其他算法可在管理员页上传后启用</div>
        <div class="mt-4">
          <el-select
            class="avs-select w-full"
            popper-class="avs-select-dropdown"
            v-model="selectedAlgorithm"
            filterable
            placeholder="请选择算法"
          >
            <el-option
              v-for="a in algorithms.items"
              :key="a.id"
              :label="`${a.name}${a.enabled ? '' : '（不可用）'}`"
              :value="a.id"
              :disabled="!a.enabled"
            />
          </el-select>
          <div v-if="algorithms.error" class="algo-error">{{ algorithms.error }}</div>
        </div>
        <div class="mt-4 flex gap-2">
          <el-button class="avs-btn-primary w-full" :disabled="!canStart" :loading="starting" @click="startTask">
            {{ starting ? '启动中...' : '启动推理' }}
          </el-button>
        </div>
      </div>

      <TaskProgressCard :task="currentTask" :on-cancel="onCancel" />
    </div>

    <div class="grid gap-5 lg:col-span-2">
      <ResultViewerCard
        :task-id="currentTask?.task_id ?? null"
        :status="currentTask?.status"
        :original-file="originalFile"
      />

      <div class="avs-card w-full">
        <div class="flex items-center gap-2">
          <span class="avs-badge-inline">COMBO 已接入</span>
          <div class="avs-note-title">说明</div>
        </div>
        <div class="mt-1 avs-note-desc">
          当前可直接使用 COMBO（已上传部分权重）。
          其他算法可在管理员页上传对应权重后启用。
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.algo-error {
  margin-top: 8px;
  color: var(--danger);
  font-size: 12px;
}

.avs-note-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
}

.avs-note-desc {
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-secondary);
}
</style>
