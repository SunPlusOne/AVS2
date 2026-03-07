<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { getResultUrl, getMasksUrl } from '@/api/avs'

const props = defineProps<{
  taskId: string | null
  originalFile?: File | null
  status?: string
}>()

const mode = ref<'side' | 'result'>('side')
const cacheKey = ref(Date.now())
const originalUrl = ref('')

watch(
  () => [props.taskId, props.status],
  () => {
    cacheKey.value = Date.now()
  },
  { immediate: true },
)

watch(
  () => props.originalFile,
  (file) => {
    if (originalUrl.value) URL.revokeObjectURL(originalUrl.value)
    originalUrl.value = file ? URL.createObjectURL(file) : ''
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  if (originalUrl.value) URL.revokeObjectURL(originalUrl.value)
})

const resultUrl = computed(() => {
  if (!props.taskId) return ''
  return `${getResultUrl(props.taskId)}?v=${cacheKey.value}`
})

const canShow = computed(() => props.status === 'completed' && !!props.taskId)

function onModeChange(v: 'side' | 'result') {
  mode.value = v
}

const masksUrl = computed(() => {
  if (!props.taskId) return ''
  return `${getMasksUrl(props.taskId)}?v=${cacheKey.value}`
})

const emptyText = computed(() => {
  if (props.status === 'running' || props.status === 'queued') return '任务处理中，完成后在此显示结果'
  if (props.status === 'failed') return '任务失败，请修复后重新执行'
  return '任务完成后在此显示结果'
})
</script>

<template>
  <div class="avs-card">
    <div class="result-head">
      <div>
        <div class="avs-card-title">结果预览</div>
        <div class="avs-card-desc">支持原视频与结果视频对比</div>
      </div>

      <div class="result-segment" role="tablist" aria-label="结果展示模式">
        <button
          class="segment-btn"
          :class="{ active: mode === 'side' }"
          type="button"
          @click="onModeChange('side')"
        >
          对比
        </button>
        <button
          class="segment-btn"
          :class="{ active: mode === 'result' }"
          type="button"
          @click="onModeChange('result')"
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
      <div class="result-empty-hint">任务完成后可在此预览视频并下载输出文件</div>
    </div>

    <div v-else class="result-body">
      <div v-if="mode === 'side'" class="result-grid md:grid-cols-2">
        <div class="video-card">
          <div class="video-title">原始视频</div>
          <video v-if="originalUrl" class="video-player" controls :src="originalUrl" />
          <div v-else class="video-fallback">本地原视频不可用</div>
        </div>
        <div class="video-card">
          <div class="video-title">分割结果</div>
          <video class="video-player" controls :src="resultUrl" />
        </div>
      </div>

      <div v-else class="video-card">
        <div class="video-title">分割结果</div>
        <video class="video-player" controls :src="resultUrl" />
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
  height: 200px;
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

.result-grid {
  display: grid;
  gap: 16px;
}

.video-card {
  border: 1px solid var(--border-default);
  border-radius: 12px;
  background: var(--bg-hover);
  padding: 12px;
}

.video-title {
  margin-bottom: 8px;
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 500;
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

.download-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
</style>

