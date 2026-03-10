<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { getMasksUrl, getResultUrl, getTaskReport } from '@/api/avs'
import type { TaskReport } from '@/types/contracts'

const props = defineProps<{
  taskId: string | null
  originalFile?: File | null
  status?: string
}>()

const mode = ref<'compare' | 'result'>('compare')
const cacheKey = ref(Date.now())
const originalUrl = ref('')
const report = ref<TaskReport | null>(null)

const compareStageRef = ref<HTMLDivElement | null>(null)
const compareOriginalRef = ref<HTMLVideoElement | null>(null)
const compareResultRef = ref<HTMLVideoElement | null>(null)
const resultRef = ref<HTMLVideoElement | null>(null)

const dividerPercent = ref(50)
const draggingDivider = ref(false)
const isPlaying = ref(false)
const currentFrame = ref(1)
const fallbackFps = ref(25)

let syncing = false

function revokeOriginalUrl() {
  if (originalUrl.value) {
    URL.revokeObjectURL(originalUrl.value)
    originalUrl.value = ''
  }
}

watch(
  () => [props.taskId, props.status],
  async () => {
    cacheKey.value = Date.now()
    report.value = null
    currentFrame.value = 1

    if (!props.taskId || props.status !== 'completed') return
    try {
      report.value = await getTaskReport(props.taskId)
    } catch {
      report.value = null
    }
  },
  { immediate: true },
)

watch(
  () => props.originalFile,
  (file) => {
    revokeOriginalUrl()
    originalUrl.value = file ? URL.createObjectURL(file) : ''
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  revokeOriginalUrl()
  window.removeEventListener('pointermove', onPointerMove)
  window.removeEventListener('pointerup', onPointerUp)
})

const resultUrl = computed(() => {
  if (!props.taskId) return ''
  return `${getResultUrl(props.taskId)}?v=${cacheKey.value}`
})

const masksUrl = computed(() => {
  if (!props.taskId) return ''
  return `${getMasksUrl(props.taskId)}?v=${cacheKey.value}`
})

const canShow = computed(() => props.status === 'completed' && !!props.taskId)

const emptyText = computed(() => {
  if (props.status === 'running' || props.status === 'queued') return '任务处理中，完成后可在此查看可视化结果'
  if (props.status === 'failed') return '任务失败，请修复后重新执行'
  return '完成后可在此对比原视频与分割掩码，并下载结果'
})

const totalFrames = computed(() => {
  const frames = report.value?.frames
  if (frames != null && Number.isFinite(frames) && frames > 0) return Math.round(frames)
  return 0
})

const coverageSeries = computed(() => report.value?.mask_coverage_pct_by_frame ?? [])

const effectiveFps = computed(() => {
  const reportFps = report.value?.fps
  if (reportFps != null && Number.isFinite(reportFps) && reportFps > 0) return reportFps

  const v = mode.value === 'compare' ? compareResultRef.value ?? compareOriginalRef.value : resultRef.value
  const duration = Number(v?.duration)
  if (duration > 0 && totalFrames.value > 0) return totalFrames.value / duration

  return fallbackFps.value
})

const currentCoverage = computed(() => {
  const arr = coverageSeries.value
  if (!arr.length) return null
  const idx = Math.max(0, Math.min(arr.length - 1, currentFrame.value - 1))
  const value = Number(arr[idx])
  if (!Number.isFinite(value)) return null
  return value
})

const coverageText = computed(() => {
  if (currentCoverage.value == null) return '--'
  return `${currentCoverage.value.toFixed(2)}%`
})

const sliderFrame = computed({
  get() {
    return currentFrame.value
  },
  set(v: number) {
    seekToFrame(v)
  },
})

function setMode(v: 'compare' | 'result') {
  mode.value = v
  pauseVisible()
}

function getVisibleVideos(): HTMLVideoElement[] {
  if (mode.value === 'compare') {
    return [compareOriginalRef.value, compareResultRef.value].filter(Boolean) as HTMLVideoElement[]
  }
  return [resultRef.value].filter(Boolean) as HTMLVideoElement[]
}

function updateCurrentFrameByTime(timeSec: number) {
  const fps = Math.max(1, effectiveFps.value)
  const rawFrame = Math.floor(Math.max(0, timeSec) * fps) + 1
  const maxFrame = totalFrames.value > 0 ? totalFrames.value : rawFrame
  currentFrame.value = Math.max(1, Math.min(maxFrame, rawFrame))
}

function seekToTime(timeSec: number) {
  const videos = getVisibleVideos()
  if (!videos.length) return

  for (const video of videos) {
    const duration = Number(video.duration)
    const bounded = Number.isFinite(duration) && duration > 0 ? Math.max(0, Math.min(duration, timeSec)) : Math.max(0, timeSec)
    video.currentTime = bounded
  }

  updateCurrentFrameByTime(timeSec)
}

function seekToFrame(frame: number) {
  const target = Math.max(1, Math.round(frame))
  const fps = Math.max(1, effectiveFps.value)
  const timeSec = (target - 1) / fps
  seekToTime(timeSec)
}

function stepFrame(delta: number) {
  const base = currentFrame.value > 0 ? currentFrame.value : 1
  const maxFrame = totalFrames.value > 0 ? totalFrames.value : Math.max(base, 1)
  const next = Math.max(1, Math.min(maxFrame, base + delta))
  seekToFrame(next)
}

async function togglePlay() {
  const videos = getVisibleVideos()
  if (!videos.length) return

  const shouldPlay = videos.some((v) => v.paused)
  if (shouldPlay) {
    for (const video of videos) {
      try {
        await video.play()
      } catch {
        // ignore browser autoplay policy failures
      }
    }
    isPlaying.value = true
  } else {
    for (const video of videos) video.pause()
    isPlaying.value = false
  }
}

function pauseVisible() {
  for (const video of getVisibleVideos()) video.pause()
  isPlaying.value = false
}

function syncVideoTime(source: HTMLVideoElement | null, target: HTMLVideoElement | null) {
  if (!source || !target || syncing) return
  if (Math.abs(source.currentTime - target.currentTime) < 0.05) return

  syncing = true
  target.currentTime = source.currentTime
  window.setTimeout(() => {
    syncing = false
  }, 0)
}

function onCompareTimeUpdate(source: 'original' | 'result') {
  const sourceVideo = source === 'original' ? compareOriginalRef.value : compareResultRef.value
  const targetVideo = source === 'original' ? compareResultRef.value : compareOriginalRef.value
  syncVideoTime(sourceVideo, targetVideo)
  if (sourceVideo) updateCurrentFrameByTime(sourceVideo.currentTime)
}

function onResultTimeUpdate() {
  if (resultRef.value) updateCurrentFrameByTime(resultRef.value.currentTime)
}

function onVideoPlay() {
  isPlaying.value = true
}

function onVideoPause() {
  isPlaying.value = false
}

function onVideoMetaLoaded() {
  const v = mode.value === 'compare' ? compareResultRef.value ?? compareOriginalRef.value : resultRef.value
  const duration = Number(v?.duration)
  if (duration > 0 && totalFrames.value > 0) {
    fallbackFps.value = totalFrames.value / duration
  }
}

function updateDivider(clientX: number) {
  if (!compareStageRef.value) return
  const rect = compareStageRef.value.getBoundingClientRect()
  if (rect.width <= 0) return
  const ratio = ((clientX - rect.left) / rect.width) * 100
  dividerPercent.value = Math.max(0, Math.min(100, ratio))
}

function onDividerPointerDown(e: PointerEvent) {
  draggingDivider.value = true
  updateDivider(e.clientX)
  window.addEventListener('pointermove', onPointerMove)
  window.addEventListener('pointerup', onPointerUp)
}

function onPointerMove(e: PointerEvent) {
  if (!draggingDivider.value) return
  updateDivider(e.clientX)
}

function onPointerUp() {
  draggingDivider.value = false
  window.removeEventListener('pointermove', onPointerMove)
  window.removeEventListener('pointerup', onPointerUp)
}

function onStagePointerDown(e: PointerEvent) {
  if (mode.value !== 'compare') return
  if (draggingDivider.value) return
  updateDivider(e.clientX)
}
</script>

<template>
  <div class="avs-card">
    <div class="result-head">
      <div>
        <div class="avs-card-title">结果预览</div>
        <div class="avs-card-desc">支持滑动对比、逐帧步进与掩码覆盖率查看</div>
      </div>

      <div class="result-segment" role="tablist" aria-label="结果展示模式">
        <button
          class="segment-btn"
          :class="{ active: mode === 'compare' }"
          type="button"
          @click="setMode('compare')"
        >
          对比
        </button>
        <button
          class="segment-btn"
          :class="{ active: mode === 'result' }"
          type="button"
          @click="setMode('result')"
        >
          结果
        </button>
      </div>
    </div>

    <div v-if="!canShow" class="result-empty">
      <svg class="result-empty-illus" viewBox="0 0 64 64" aria-hidden="true">
        <path
          fill="currentColor"
          d="M18 48h28a10 10 0 0 0 2.5-19.684A14 14 0 0 0 20.2 27.4 9 9 0 0 0 18 48Zm14-20 6 6h-4v8h-4v-8h-4l6-6Z"
        />
      </svg>
      <div class="result-empty-title">{{ emptyText }}</div>
      <div class="result-empty-hint">完成后可在此对比原视频与分割掩码，并下载结果</div>
    </div>

    <div v-else class="result-body">
      <div v-if="mode === 'compare'" class="video-card">
        <div class="video-title">滑动对比（左：原始帧，右：分割结果）</div>

        <div v-if="!originalUrl" class="video-fallback">原始视频不可用，仅可查看结果模式</div>

        <div
          v-else
          ref="compareStageRef"
          class="compare-stage"
          @pointerdown="onStagePointerDown"
        >
          <video
            ref="compareOriginalRef"
            class="compare-video"
            :src="originalUrl"
            muted
            playsinline
            preload="metadata"
            @timeupdate="onCompareTimeUpdate('original')"
            @loadedmetadata="onVideoMetaLoaded"
            @play="onVideoPlay"
            @pause="onVideoPause"
          />

          <div class="compare-overlay" :style="{ clipPath: `inset(0 0 0 ${dividerPercent}%)` }">
            <video
              ref="compareResultRef"
              class="compare-video"
              :src="resultUrl"
              playsinline
              preload="metadata"
              @timeupdate="onCompareTimeUpdate('result')"
              @loadedmetadata="onVideoMetaLoaded"
              @play="onVideoPlay"
              @pause="onVideoPause"
            />
          </div>

          <div class="compare-divider" :style="{ left: `${dividerPercent}%` }" @pointerdown.stop.prevent="onDividerPointerDown">
            <span class="divider-handle" aria-hidden="true"></span>
          </div>

          <div class="viewer-chip chip-frame">第 {{ currentFrame }} 帧</div>
          <div class="viewer-chip chip-coverage">覆盖 {{ coverageText }}</div>
        </div>
      </div>

      <div v-else class="video-card result-only-card">
        <div class="video-title">结果视频（彩色掩码叠加）</div>
        <div class="viewer-chip chip-frame">当前帧 #{{ currentFrame }}</div>
        <div class="viewer-chip chip-coverage">覆盖 {{ coverageText }}</div>
        <video
          ref="resultRef"
          class="video-player"
          controls
          :src="resultUrl"
          preload="metadata"
          @timeupdate="onResultTimeUpdate"
          @loadedmetadata="onVideoMetaLoaded"
          @play="onVideoPlay"
          @pause="onVideoPause"
        />
      </div>

      <div class="frame-control-panel">
        <div class="frame-actions">
          <el-button class="avs-btn-secondary" @click="stepFrame(-1)">← 上一帧</el-button>
          <el-button class="avs-btn-primary" @click="togglePlay">{{ isPlaying ? '暂停' : '播放' }}</el-button>
          <el-button class="avs-btn-secondary" @click="stepFrame(1)">下一帧 →</el-button>
        </div>

        <el-slider
          v-model="sliderFrame"
          :min="1"
          :max="Math.max(totalFrames, 1)"
          :show-tooltip="false"
          :disabled="totalFrames <= 1"
        />

        <div class="frame-hint">
          帧位置：{{ currentFrame }} / {{ totalFrames > 0 ? totalFrames : '--' }}
        </div>
      </div>

      <div class="download-row">
        <a class="btn-primary" :href="resultUrl" target="_blank" rel="noreferrer">下载结果视频</a>
        <a class="btn-outline" :href="masksUrl" target="_blank" rel="noreferrer">下载逐帧掩码</a>
      </div>
    </div>
  </div>
</template>

<style scoped>
.result-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.result-segment {
  display: inline-flex;
  padding: 3px;
  border-radius: 999px;
  background: var(--info-soft);
}

.segment-btn {
  min-width: 70px;
  height: 34px;
  padding: 0 14px;
  border: none;
  border-radius: 999px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s ease;
}

.segment-btn:hover {
  color: var(--text-primary);
}

.segment-btn.active {
  color: var(--text-primary);
  background: var(--bg-card);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.12);
}

.result-empty {
  margin-top: 16px;
  height: 220px;
  border: 1.5px dashed var(--border-default);
  border-radius: 12px;
  background: var(--bg-card);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 20px;
}

.result-empty-illus {
  width: 48px;
  height: 48px;
  color: var(--icon-muted);
}

.result-empty-title {
  margin-top: 10px;
  color: var(--text-subtle);
  font-size: 14px;
  line-height: 1.4;
  font-weight: 500;
}

.result-empty-hint {
  margin-top: 4px;
  color: var(--text-subtle);
  font-size: 12px;
  line-height: 1.6;
}

.result-body {
  margin-top: 16px;
  display: grid;
  gap: 16px;
}

.video-card {
  border: 1px solid var(--border-default);
  border-radius: 12px;
  background: var(--bg-hover);
  padding: 12px;
  position: relative;
}

.video-title {
  margin-bottom: 8px;
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 500;
}

.compare-stage {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 9;
  border-radius: 10px;
  overflow: hidden;
  background: #000;
}

.compare-video {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: contain;
  background: #000;
}

.compare-overlay {
  position: absolute;
  inset: 0;
  overflow: hidden;
}

.compare-divider {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 2px;
  background: rgba(255, 255, 255, 0.85);
  transform: translateX(-1px);
  z-index: 2;
  cursor: ew-resize;
}

.divider-handle {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 20px;
  height: 28px;
  transform: translate(-50%, -50%);
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.9);
  background: rgba(15, 23, 42, 0.65);
}

.viewer-chip {
  position: absolute;
  z-index: 3;
  border-radius: 999px;
  padding: 4px 10px;
  font-size: 12px;
  font-weight: 600;
  color: #fff;
  background: rgba(15, 23, 42, 0.68);
  backdrop-filter: blur(2px);
}

.chip-frame {
  top: 8px;
  left: 8px;
}

.chip-coverage {
  right: 8px;
  bottom: 8px;
}

.result-only-card {
  display: grid;
  gap: 8px;
}

.video-player {
  width: 100%;
  border-radius: 8px;
  background: var(--media-bg);
}

.video-fallback {
  min-height: 120px;
  display: grid;
  place-items: center;
  color: var(--text-secondary);
  font-size: 13px;
}

.frame-control-panel {
  border: 1px solid var(--border-default);
  border-radius: 12px;
  background: var(--bg-hover);
  padding: 12px;
}

.frame-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.frame-hint {
  margin-top: 6px;
  color: var(--text-secondary);
  font-size: 12px;
}

.download-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

@media (max-width: 768px) {
  .result-head {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
