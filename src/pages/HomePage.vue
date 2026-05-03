<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { ElMessage } from 'element-plus'
import * as VideoUploadCardModule from '@/components/VideoUploadCard.vue'
import * as TaskProgressCardModule from '@/components/TaskProgressCard.vue'
import * as ResultViewerCardModule from '@/components/ResultViewerCard.vue'
import { createTask, cancelTask, getTask } from '@/api/avs'
import { getWsBaseUrl } from '@/api/http'
import { useTasksStore } from '@/stores/tasks'
import type { AlgorithmId, InferenceScene, TaskProgress, UploadResponse } from '@/types/contracts'

const VideoUploadCard = (VideoUploadCardModule as any).default ?? VideoUploadCardModule
const TaskProgressCard = (TaskProgressCardModule as any).default ?? TaskProgressCardModule
const ResultViewerCard = (ResultViewerCardModule as any).default ?? ResultViewerCardModule

const tasksStore = useTasksStore()

const allAlgorithms: Array<{ id: AlgorithmId; label: string }> = [
  { id: 'avsegformer', label: 'AVSegFormer' },
  { id: 'avis', label: 'AVIS' },
  { id: 'vct', label: 'VCT' },
  { id: 'combo', label: 'COMBO' },
]

const uploaded = ref<UploadResponse | null>(null)
const originalFile = ref<File | null>(null)
const selectedAlgorithm = ref<AlgorithmId>('combo')
const selectedScene = ref<InferenceScene>('single_source')
const currentTask = ref<TaskProgress | null>(null)

const starting = ref(false)
const wsRef = ref<WebSocket | null>(null)
let pollTimer: number | null = null

const canStart = computed(() => !!uploaded.value?.file_id && !starting.value)
const needsSceneSelection = computed(() => selectedAlgorithm.value !== 'avis')

const startDisabledReason = computed(() => {
  if (starting.value) return '任务启动中，请稍候'
  if (!originalFile.value) return '请先上传视频'
  if (!uploaded.value?.file_id) return '文件尚未上传完成，请先获取 file_id'
  return ''
})

function onUploaded(payload: { file: File; res: UploadResponse }) {
  uploaded.value = payload.res
  originalFile.value = payload.file
}

function onSelectedFile(file: File) {
  originalFile.value = file
  uploaded.value = null
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
    const { task_id } = await createTask({
      file_id: uploaded.value.file_id,
      algorithm: selectedAlgorithm.value,
      scene: needsSceneSelection.value ? selectedScene.value : undefined,
    })
    currentTask.value = {
      task_id,
      status: 'queued',
      progress: 0,
      algorithm: selectedAlgorithm.value,
      scene: needsSceneSelection.value ? selectedScene.value : undefined,
      resolved_scene: needsSceneSelection.value ? selectedScene.value : undefined,
      filename: uploaded.value.filename,
      fps: uploaded.value.fps,
      duration_seconds: uploaded.value.duration_seconds,
      width: uploaded.value.width,
      height: uploaded.value.height,
      total_frames: uploaded.value.total_frames,
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

onBeforeUnmount(() => {
  cleanupRealtime()
})
</script>

<template>
  <div class="grid gap-5 lg:grid-cols-3">
    <div class="grid gap-5 lg:col-span-1">
      <VideoUploadCard
        @selected="onSelectedFile"
        @uploaded="onUploaded"
      />

      <div class="avs-card">
        <div class="avs-card-title">算法选择</div>
        <div class="avs-card-desc">AVIS 直接推理，无需场景；其他算法请手动选择场景。</div>
        <div class="mt-4">
          <el-select
            class="avs-select w-full"
            popper-class="avs-select-dropdown"
            v-model="selectedAlgorithm"
            filterable
            placeholder="请选择算法"
          >
            <el-option
              v-for="algo in allAlgorithms"
              :key="algo.id"
              :label="algo.label"
              :value="algo.id"
            />
          </el-select>
        </div>

        <div v-if="needsSceneSelection" class="mt-4">
          <div class="scene-title">使用场景</div>
          <el-radio-group v-model="selectedScene" class="scene-group">
            <el-radio label="single_source" border>
              单个物体发声（画面中只有一个物体在发声）
            </el-radio>
            <el-radio label="multi_source" border>
              多个物体同时发声（画面中有多个物体同时发声）
            </el-radio>
          </el-radio-group>
        </div>

        <div class="mt-4 flex gap-2">
          <el-tooltip :content="startDisabledReason" :disabled="canStart || !startDisabledReason" placement="top">
            <div class="w-full">
              <el-button class="avs-btn-primary w-full" :disabled="!canStart" :loading="starting" @click="startTask">
                {{ starting ? '启动中...' : '启动推理' }}
              </el-button>
            </div>
          </el-tooltip>
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
          <span class="avs-badge-inline">AVSegFormer / AVIS / VCT / COMBO 已接入</span>
          <div class="avs-note-title">说明</div>
        </div>
        <div class="mt-1 avs-note-desc">
          当前支持 AVSegFormer、AVIS、VCT 和 COMBO 的本地推理。请按实际视频内容手动选择“使用场景”。
          语义分割权重（AVSS）暂不在本页面开放。
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

.scene-title {
  margin-bottom: 8px;
  color: var(--text-primary);
  font-size: 13px;
  font-weight: 600;
}

.scene-group {
  display: grid;
  gap: 10px;
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
