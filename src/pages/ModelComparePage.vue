<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { createTask, getFusionIntersectionUrl, getTask, getTaskReport, getResultUrl } from '@/api/avs'
import * as VideoUploadCardModule from '@/components/VideoUploadCard.vue'
import { useAuthStore } from '@/stores/auth'
import type {
  AlgorithmId,
  InferenceScene,
  TaskMetrics,
  TaskReport,
  TaskStatus,
  UploadResponse,
} from '@/types/contracts'

const VideoUploadCard = (VideoUploadCardModule as any).default ?? VideoUploadCardModule

interface CompareItem {
  algorithm: AlgorithmId
  taskId: string
  status: TaskStatus
  progress: number
  metrics?: TaskMetrics
  report?: TaskReport
}

const allAlgorithms: Array<{ id: AlgorithmId; label: string }> = [
  { id: 'avsegformer', label: 'AVSegFormer' },
  { id: 'mavsnet', label: 'MAVS-Net' },
  { id: 'avis', label: 'AVIS' },
  { id: 'vct', label: 'VCT' },
  { id: 'combo', label: 'COMBO' },
]

const uploaded = ref<UploadResponse | null>(null)
const originalFile = ref<File | null>(null)
const auth = useAuthStore()
const selectedAlgorithms = ref<AlgorithmId[]>(['mavsnet', 'avis', 'vct', 'combo'])
const selectedScene = ref<InferenceScene>('single_source')
const launching = ref(false)

const compareItems = ref<CompareItem[]>([])
const videoMap = ref<Record<string, HTMLVideoElement | null>>({})
const fusionVideoRef = ref<HTMLVideoElement | null>(null)
const fusionLoadFailed = ref(false)
const currentFrame = ref(1)
let pollTimer: number | null = null
let syncingVideos = false

const canStart = computed(() => !!uploaded.value?.file_id && selectedAlgorithms.value.length >= 2 && !launching.value)

const startDisabledReason = computed(() => {
  if (launching.value) return '任务正在创建中'
  if (!originalFile.value) return '请先上传视频'
  if (!uploaded.value?.file_id) return '文件尚未上传完成，请先获取 file_id'
  if (selectedAlgorithms.value.length < 2) return '至少选择两个模型才能对比'
  return ''
})

const totalFrames = computed(() => {
  const frames = compareItems.value
    .map((item) => item.report?.frames)
    .filter((v): v is number => v != null && Number.isFinite(v) && v > 0)
  if (!frames.length) return uploaded.value?.total_frames ?? 0
  return Math.max(...frames)
})

const effectiveFps = computed(() => {
  const fpsList = compareItems.value
    .map((item) => item.report?.fps)
    .filter((v): v is number => v != null && Number.isFinite(v) && v > 0)
  if (fpsList.length > 0) return fpsList[0]
  if (uploaded.value?.fps && uploaded.value.fps > 0) return uploaded.value.fps
  return 25
})

const hasFinishedResult = computed(() => compareItems.value.some((item) => item.status === 'completed'))

const completedTaskIds = computed(() => compareItems.value.filter((item) => item.status === 'completed').map((item) => item.taskId))

const fusionVideoUrl = computed(() => {
  if (completedTaskIds.value.length < 2) return ''
  const cacheBust = completedTaskIds.value.join('-')
  return getFusionIntersectionUrl(completedTaskIds.value, {
    cacheBust,
    authToken: auth.token || undefined,
  })
})

const chartRows = computed(() => {
  return compareItems.value
    .filter((item) => item.status === 'completed')
    .map((item) => {
      if (item.algorithm === 'avis') {
        return {
          algorithm: item.algorithm,
          metrics: [
            { label: 'FSLA', value: item.metrics?.fsla ?? 0, cls: 'bar-fsla' },
            { label: 'HOTA', value: item.metrics?.hota ?? 0, cls: 'bar-hota' },
            { label: 'mAP', value: item.metrics?.map ?? 0, cls: 'bar-map' },
          ],
        }
      }
      return {
        algorithm: item.algorithm,
        metrics: [
          { label: 'mIoU', value: item.metrics?.jaccard ?? 0, cls: 'bar-j' },
          { label: 'F-score', value: item.metrics?.f_measure ?? 0, cls: 'bar-f' },
        ],
      }
    })
})

function toPct(value?: number): number {
  if (value == null || !Number.isFinite(value)) return 0
  return value <= 1 ? value * 100 : value
}

function onUploaded(payload: { file: File; res: UploadResponse }) {
  uploaded.value = payload.res
  originalFile.value = payload.file
}

function onSelectedFile(file: File) {
  originalFile.value = file
  uploaded.value = null
}

function cleanupPolling() {
  if (pollTimer != null) {
    window.clearInterval(pollTimer)
    pollTimer = null
  }
}

async function fetchReport(item: CompareItem) {
  if (!item.taskId) return
  try {
    const report = await getTaskReport(item.taskId)
    item.report = report
    if (report.metrics) item.metrics = report.metrics
  } catch {
    return
  }
}

async function refreshItems() {
  const active = compareItems.value.filter((item) => item.status === 'queued' || item.status === 'running')
  if (!active.length) {
    cleanupPolling()
    return
  }

  await Promise.all(
    active.map(async (item) => {
      try {
        const latest = await getTask(item.taskId)
        item.status = latest.status
        item.progress = latest.progress
        item.metrics = latest.metrics

        if (latest.status === 'completed' && !item.report) {
          await fetchReport(item)
        }
      } catch {
        return
      }
    }),
  )

  const allFinished = compareItems.value.every(
    (item) => item.status === 'completed' || item.status === 'failed' || item.status === 'canceled',
  )
  if (allFinished) cleanupPolling()
}

function startPolling() {
  cleanupPolling()
  pollTimer = window.setInterval(() => {
    refreshItems()
  }, 1500)
}

async function startCompare() {
  if (!uploaded.value?.file_id) return

  cleanupPolling()
  compareItems.value = []
  launching.value = true

  try {
    const items: CompareItem[] = []
    for (const algorithm of selectedAlgorithms.value) {
      const res = await createTask({
        file_id: uploaded.value.file_id,
        algorithm,
        scene: selectedScene.value,
      })
      items.push({
        algorithm,
        taskId: res.task_id,
        status: 'queued',
        progress: 0,
      })
    }

    compareItems.value = items
    currentFrame.value = 1
    ElMessage.success('模型对比任务已启动')
    await refreshItems()
    startPolling()
  } catch (e: any) {
    ElMessage.error(e?.message ?? '启动模型对比失败')
  } finally {
    launching.value = false
  }
}

function statusLabel(status: TaskStatus) {
  if (status === 'queued') return '排队中'
  if (status === 'running') return '运行中'
  if (status === 'completed') return '已完成'
  if (status === 'failed') return '失败'
  if (status === 'canceled') return '已取消'
  return status
}

function statusClass(status: TaskStatus) {
  if (status === 'running') return 'status-warning'
  if (status === 'completed') return 'status-success'
  if (status === 'failed') return 'status-danger'
  return 'status-idle'
}

function formatPct(v?: number) {
  if (v == null || !Number.isFinite(v)) return '--'
  return `${toPct(v).toFixed(2)}%`
}

function formatTime(item: CompareItem) {
  const totalMs =
    item.metrics?.total_inference_ms ??
    item.report?.metrics?.total_inference_ms ??
    item.report?.processing?.total_ms
  const avgFrameMs =
    item.metrics?.avg_frame_ms ??
    item.report?.metrics?.avg_frame_ms ??
    item.report?.processing?.avg_frame_ms

  if (totalMs == null || !Number.isFinite(totalMs) || totalMs <= 0) return '--'
  const totalSec = totalMs / 1000
  if (avgFrameMs == null || !Number.isFinite(avgFrameMs) || avgFrameMs <= 0) return `${totalSec.toFixed(2)}s`
  return `${totalSec.toFixed(2)}s / ${avgFrameMs.toFixed(2)}ms/帧`
}

function setVideoRef(taskId: string) {
  return (el: Element | null) => {
    videoMap.value[taskId] = el as HTMLVideoElement | null
  }
}

function getVideoPairs() {
  return compareItems.value
    .map((item) => ({ id: item.taskId, video: videoMap.value[item.taskId] }))
    .filter((entry): entry is { id: string; video: HTMLVideoElement } => !!entry.video)
}

function syncBySource(sourceTaskId: string) {
  if (syncingVideos) return
  const source = sourceTaskId === '__fusion__' ? fusionVideoRef.value : videoMap.value[sourceTaskId]
  if (!source) return

  const time = source.currentTime
  const fps = Math.max(1, effectiveFps.value)
  const frame = Math.floor(time * fps) + 1
  const maxFrame = Math.max(totalFrames.value, frame)
  currentFrame.value = Math.max(1, Math.min(maxFrame, frame))

  // Fusion video should feel like normal single-video playback.
  // Do not force-seek all compare videos on every fusion timeupdate.
  if (sourceTaskId === '__fusion__') return

  syncingVideos = true
  for (const { id: taskId, video } of getVideoPairs()) {
    if (!video || taskId === sourceTaskId) continue
    if (Math.abs(video.currentTime - time) > 0.05) {
      video.currentTime = time
    }
  }
  window.setTimeout(() => {
    syncingVideos = false
  }, 0)
}

function onFusionTimeUpdate() {
  syncBySource('__fusion__')
}

function onFusionLoaded() {
  fusionLoadFailed.value = false
}

function onFusionError() {
  fusionLoadFailed.value = true
}

onBeforeUnmount(() => {
  cleanupPolling()
})

watch(fusionVideoUrl, () => {
  fusionLoadFailed.value = false
  const v = fusionVideoRef.value
  if (v) v.currentTime = 0
})
</script>

<template>
  <div class="grid gap-5">
    <div>
      <div class="page-heading">
        模型对比
      </div>
      <div class="page-subheading">
        同一视频并行运行多模型，进行结果与指标对比
      </div>
    </div>

    <div class="grid gap-5 lg:grid-cols-3">
      <div class="lg:col-span-1 grid gap-5">
        <VideoUploadCard
          @selected="onSelectedFile"
          @uploaded="onUploaded"
        />

        <div class="avs-card">
          <div class="avs-card-title">
            对比配置
          </div>
          <div class="avs-card-desc">
            至少选择 2 个模型。任务启动后将并行推理。
          </div>

          <div class="mt-4 grid gap-3">
            <el-checkbox-group
              v-model="selectedAlgorithms"
              class="model-group"
            >
              <el-checkbox
                v-for="algo in allAlgorithms"
                :key="algo.id"
                :label="algo.id"
              >
                {{ algo.label }}
              </el-checkbox>
            </el-checkbox-group>

            <el-radio-group
              v-model="selectedScene"
              class="scene-group"
            >
              <el-radio
                label="single_source"
                border
              >
                单个物体发声
              </el-radio>
              <el-radio
                label="multi_source"
                border
              >
                多个物体同时发声
              </el-radio>
            </el-radio-group>

            <el-tooltip
              :content="startDisabledReason"
              :disabled="canStart || !startDisabledReason"
              placement="top"
            >
              <div>
                <el-button
                  class="avs-btn-primary w-full"
                  :disabled="!canStart"
                  :loading="launching"
                  @click="startCompare"
                >
                  {{ launching ? '启动中...' : '开始模型对比' }}
                </el-button>
              </div>
            </el-tooltip>
          </div>
        </div>
      </div>

      <div class="lg:col-span-2 grid gap-5">
        <div class="avs-card">
          <div class="avs-card-title">
            融合结果展示
          </div>
          <div class="avs-card-desc">
            后端预合成交集掩码覆盖视频，前端直接播放，避免逐帧闪烁
          </div>

          <div
            v-if="fusionVideoUrl"
            class="fusion-stage mt-3"
          >
            <video
              ref="fusionVideoRef"
              class="fusion-video"
              controls
              :src="fusionVideoUrl"
              preload="metadata"
              @loadeddata="onFusionLoaded"
              @timeupdate="onFusionTimeUpdate"
              @seeked="onFusionTimeUpdate"
              @error="onFusionError"
            />
          </div>
          <div
            v-else
            class="video-placeholder mt-3"
          >
            至少有 2 个模型完成后才会生成融合结果视频
          </div>

          <div class="fusion-hint">
            当前帧：{{ currentFrame }} / {{ totalFrames > 0 ? totalFrames : '--' }}，参与交集模型：{{ compareItems.filter((item) => item.status === 'completed').length }}
          </div>
          <div class="fusion-note">
            首次播放会触发后端合成，耗时与视频长度及分辨率相关。
          </div>
          <div
            v-if="fusionLoadFailed"
            class="fusion-error"
          >
            融合结果加载失败，请确认参与对比的是同一上传视频并稍后重试。
          </div>
        </div>

        <div
          v-if="compareItems.length === 0"
          class="avs-card compare-empty"
        >
          上传同一视频并选择多个模型后，即可在此并排对比结果。
        </div>

        <div
          v-else
          class="compare-grid"
          :class="`cols-${Math.min(compareItems.length, 3)}`"
        >
          <div
            v-for="item in compareItems"
            :key="item.taskId"
            class="avs-card compare-col"
          >
            <div class="col-head">
              <div class="col-title">
                {{ item.algorithm.toUpperCase() }}
              </div>
              <span
                class="status-pill"
                :class="statusClass(item.status)"
              >{{ statusLabel(item.status) }}</span>
            </div>

            <div class="col-meta">
              进度：{{ item.progress }}%
            </div>

            <video
              v-if="item.status === 'completed'"
              :ref="setVideoRef(item.taskId)"
              class="compare-video"
              controls
              :src="getResultUrl(item.taskId, { cacheBust: item.taskId, authToken: auth.token || undefined })"
              preload="metadata"
              @timeupdate="syncBySource(item.taskId)"
            />
            <div
              v-else
              class="video-placeholder"
            >
              任务完成后显示结果视频
            </div>

            <div
              v-if="item.status === 'completed'"
              class="metric-grid"
            >
              <template v-if="item.algorithm === 'avis'">
                <div class="metric-cell">
                  <div class="metric-label">
                    FSLA
                  </div>
                  <div class="metric-value">
                    {{ formatPct(item.metrics?.fsla) }}
                  </div>
                </div>
                <div class="metric-cell">
                  <div class="metric-label">
                    HOTA
                  </div>
                  <div class="metric-value">
                    {{ formatPct(item.metrics?.hota) }}
                  </div>
                </div>
                <div class="metric-cell">
                  <div class="metric-label">
                    mAP
                  </div>
                  <div class="metric-value">
                    {{ formatPct(item.metrics?.map) }}
                  </div>
                </div>
              </template>
              <template v-else>
                <div class="metric-cell">
                  <div class="metric-label">
                    mIoU
                  </div>
                  <div class="metric-value">
                    {{ formatPct(item.metrics?.jaccard) }}
                  </div>
                </div>
                <div class="metric-cell">
                  <div class="metric-label">
                    F-score
                  </div>
                  <div class="metric-value">
                    {{ formatPct(item.metrics?.f_measure) }}
                  </div>
                </div>
              </template>
              <div class="metric-cell">
                <div class="metric-label">
                  耗时
                </div>
                <div class="metric-value">
                  {{ formatTime(item) }}
                </div>
              </div>
            </div>
          </div>
        </div>

        <div
          v-if="hasFinishedResult"
          class="avs-card"
        >
          <div class="avs-card-title">
            模型指标柱状对比
          </div>
          <div class="avs-card-desc">
            按当前对比任务展示指标：AVS 模型显示 mIoU/F-score，AVIS 显示 FSLA/HOTA/mAP
          </div>

          <div class="chart-wrap">
            <div
              v-for="row in chartRows"
              :key="row.algorithm"
              class="chart-row"
            >
              <div class="chart-name">
                {{ row.algorithm.toUpperCase() }}
              </div>

              <div
                v-for="metric in row.metrics"
                :key="`${row.algorithm}-${metric.label}`"
                class="bar-line"
              >
                <span class="bar-label">{{ metric.label }}</span>
                <div class="bar-track">
                  <div
                    class="bar-fill"
                    :class="metric.cls"
                    :style="{ width: `${Math.max(0, Math.min(100, toPct(metric.value)))}%` }"
                  />
                </div>
                <span class="bar-value">{{ formatPct(metric.value) }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.model-group {
  display: grid;
  gap: 8px;
}

.scene-group {
  display: grid;
  gap: 10px;
}

.fusion-stage {
  position: relative;
  width: 100%;
  border-radius: 10px;
  overflow: hidden;
  background: var(--media-bg);
}

.fusion-video {
  width: 100%;
  display: block;
  border-radius: 10px;
}

.fusion-hint {
  margin-top: 8px;
  color: var(--text-secondary);
  font-size: 12px;
}

.fusion-note {
  margin-top: 4px;
  color: var(--text-secondary);
  font-size: 12px;
}

.fusion-error {
  margin-top: 8px;
  color: var(--danger);
  font-size: 12px;
}

.compare-empty {
  color: var(--text-secondary);
  font-size: 14px;
}

.compare-grid {
  display: grid;
  gap: 12px;
}

.compare-grid.cols-2 {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.compare-grid.cols-3 {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.compare-col {
  padding: 14px;
}

.col-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.col-title {
  color: var(--text-primary);
  font-size: 14px;
  font-weight: 700;
}

.col-meta {
  margin-top: 6px;
  color: var(--text-secondary);
  font-size: 12px;
}

.compare-video {
  margin-top: 10px;
  width: 100%;
  border-radius: 8px;
  background: var(--media-bg);
}

.video-placeholder {
  margin-top: 10px;
  min-height: 120px;
  border: 1px dashed var(--border-default);
  border-radius: 8px;
  display: grid;
  place-items: center;
  color: var(--text-secondary);
  font-size: 12px;
}

.metric-grid {
  margin-top: 10px;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.metric-cell {
  border: 1px solid var(--border-default);
  border-radius: 8px;
  background: var(--bg-hover);
  padding: 8px;
}

.metric-label {
  color: var(--text-secondary);
  font-size: 11px;
}

.metric-value {
  margin-top: 3px;
  color: var(--text-primary);
  font-size: 13px;
  font-weight: 700;
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

.chart-wrap {
  margin-top: 12px;
  display: grid;
  gap: 12px;
}

.chart-row {
  border: 1px solid var(--border-default);
  border-radius: 10px;
  background: var(--bg-hover);
  padding: 10px;
}

.chart-name {
  color: var(--text-primary);
  font-size: 13px;
  font-weight: 700;
  margin-bottom: 6px;
}

.bar-line {
  display: grid;
  grid-template-columns: 36px minmax(0, 1fr) 64px;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
}

.bar-label {
  color: var(--text-secondary);
  font-size: 12px;
}

.bar-track {
  height: 10px;
  border-radius: 999px;
  background: #e2e8f0;
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  border-radius: 999px;
}

.bar-j {
  background: linear-gradient(90deg, #1d4ed8, #3b82f6);
}

.bar-f {
  background: linear-gradient(90deg, #0891b2, #22d3ee);
}

.bar-fsla {
  background: linear-gradient(90deg, #059669, #34d399);
}

.bar-hota {
  background: linear-gradient(90deg, #b45309, #f59e0b);
}

.bar-map {
  background: linear-gradient(90deg, #7c3aed, #a78bfa);
}

.bar-value {
  color: var(--text-primary);
  font-size: 12px;
  text-align: right;
}

@media (max-width: 1024px) {
  .compare-grid.cols-2,
  .compare-grid.cols-3 {
    grid-template-columns: 1fr;
  }
}
</style>
