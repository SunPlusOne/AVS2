<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { uploadVideo } from '@/api/avs'
import type { UploadResponse } from '@/types/contracts'

const emit = defineEmits<{
  (e: 'uploaded', payload: { file: File; res: UploadResponse }): void
}>()

const fileRef = ref<File | null>(null)
const loading = ref(false)

const accept = '.mp4,.avi,.mov,.mkv'

function onPickFile(e: Event) {
  const input = e.target as HTMLInputElement
  const f = input.files?.[0]
  if (!f) return
  fileRef.value = f
}

async function onUpload() {
  if (!fileRef.value) {
    ElMessage.warning('请选择视频文件')
    return
  }
  const f = fileRef.value
  const ext = f.name.split('.').pop()?.toLowerCase() ?? ''
  const allowed = new Set(['mp4', 'avi', 'mov', 'mkv'])
  if (!allowed.has(ext)) {
    ElMessage.error('不支持的文件格式')
    return
  }

  loading.value = true
  try {
    const res = await uploadVideo(f)
    ElMessage.success('上传成功')
    emit('uploaded', { file: f, res })
  } catch (e: any) {
    ElMessage.error(e?.message ?? '上传失败')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
    <div class="flex items-start justify-between gap-3">
      <div>
        <div class="text-sm font-semibold">视频上传</div>
        <div class="mt-1 text-xs text-slate-500">支持 MP4 / AVI / MOV / MKV，单文件 ≤ 2GB</div>
      </div>
    </div>

    <div class="mt-4 grid gap-3">
      <input
        class="block w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700 file:mr-3 file:rounded-md file:border-0 file:bg-slate-200 file:px-3 file:py-2 file:text-sm file:font-medium file:text-slate-700 hover:file:bg-slate-300"
        type="file"
        :accept="accept"
        @change="onPickFile"
      />

      <div v-if="fileRef" class="text-xs text-slate-500">
        已选择：<span class="text-slate-800">{{ fileRef.name }}</span>
        <span class="ml-2">({{ (fileRef.size / 1024 / 1024).toFixed(2) }} MB)</span>
      </div>

      <el-button type="primary" :loading="loading" @click="onUpload">上传并获取 file_id</el-button>
    </div>
  </div>
</template>

