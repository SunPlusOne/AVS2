<script setup lang="ts">
import { computed, ref } from 'vue'
import { getResultUrl, getMasksUrl } from '@/api/avs'

const props = defineProps<{
  taskId: string | null
  originalFile?: File | null
  status?: string
}>()

const mode = ref<'side' | 'result'>('side')

const originalUrl = computed(() => {
  if (!props.originalFile) return ''
  return URL.createObjectURL(props.originalFile)
})

const resultUrl = computed(() => {
  if (!props.taskId) return ''
  return getResultUrl(props.taskId)
})

const canShow = computed(() => props.status === 'completed' && !!props.taskId)

function onModeChange(v: 'side' | 'result') {
  mode.value = v
}

const masksUrl = computed(() => {
  if (!props.taskId) return ''
  return getMasksUrl(props.taskId)
})
</script>

<template>
  <div class="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4">
    <div class="flex items-start justify-between gap-3">
      <div>
        <div class="text-sm font-semibold">结果预览</div>
        <div class="mt-1 text-xs text-zinc-400">支持原视频与结果视频对比（占位推理返回结果后可替换）</div>
      </div>
      <div class="flex items-center gap-2">
        <el-segmented
          :model-value="mode"
          :options="[
            { label: '对比', value: 'side' },
            { label: '结果', value: 'result' },
          ]"
          @update:model-value="onModeChange"
        />
      </div>
    </div>

    <div v-if="!canShow" class="mt-4 rounded-lg border border-dashed border-zinc-800 p-6 text-sm text-zinc-400">
      任务完成后在此显示结果视频与下载入口。
    </div>

    <div v-else class="mt-4 grid gap-4">
      <div v-if="mode === 'side'" class="grid gap-4 md:grid-cols-2">
        <div class="rounded-lg border border-zinc-800 bg-black p-2">
          <div class="mb-2 text-xs text-zinc-400">原始视频</div>
          <video v-if="originalUrl" class="w-full" controls :src="originalUrl" />
          <div v-else class="text-xs text-zinc-500">本地原视频 URL 不可用</div>
        </div>
        <div class="rounded-lg border border-zinc-800 bg-black p-2">
          <div class="mb-2 text-xs text-zinc-400">分割结果</div>
          <video class="w-full" controls :src="resultUrl" />
        </div>
      </div>

      <div v-else class="rounded-lg border border-zinc-800 bg-black p-2">
        <div class="mb-2 text-xs text-zinc-400">分割结果</div>
        <video class="w-full" controls :src="resultUrl" />
      </div>

      <div class="flex flex-wrap gap-2">
        <el-button type="primary" :href="resultUrl" tag="a">下载结果视频（MP4）</el-button>
        <el-button :href="masksUrl" tag="a">下载逐帧掩码（ZIP）</el-button>
      </div>
    </div>
  </div>
</template>

