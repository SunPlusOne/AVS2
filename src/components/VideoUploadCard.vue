<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { uploadVideo } from '@/api/avs'
import type { UploadResponse } from '@/types/contracts'

const emit = defineEmits<{
  (e: 'uploaded', payload: { file: File; res: UploadResponse }): void
}>()

const fileInputRef = ref<HTMLInputElement | null>(null)
const fileRef = ref<File | null>(null)
const loading = ref(false)
const dragover = ref(false)

const accept = '.mp4,.avi,.mov,.mkv'
const maxSizeBytes = 2 * 1024 * 1024 * 1024

const hasFile = computed(() => !!fileRef.value)

const uploadDisabled = computed(() => !fileRef.value || loading.value)

const zoneClasses = computed(() => ({
  'upload-zone': true,
  dragover: dragover.value,
  'has-file': hasFile.value,
}))

function formatFileSize(bytes: number): string {
  const mb = bytes / 1024 / 1024
  if (mb < 1024) return `${mb.toFixed(2)} MB`
  return `${(mb / 1024).toFixed(2)} GB`
}

function applyPickedFile(file: File | undefined | null): boolean {
  if (!file) return false
  const ext = file.name.split('.').pop()?.toLowerCase() ?? ''
  const allowed = new Set(['mp4', 'avi', 'mov', 'mkv'])
  if (!allowed.has(ext)) {
    ElMessage.error('不支持的文件格式')
    return false
  }
  if (file.size > maxSizeBytes) {
    ElMessage.error('文件过大，单文件需小于等于 2GB')
    return false
  }
  fileRef.value = file
  return true
}

function openFileDialog() {
  if (loading.value) return
  fileInputRef.value?.click()
}

function onPickFile(e: Event) {
  const input = e.target as HTMLInputElement
  const f = input.files?.[0]
  applyPickedFile(f)
}

function onDragOver(e: DragEvent) {
  e.preventDefault()
  if (loading.value) return
  dragover.value = true
}

function onDragLeave(e: DragEvent) {
  e.preventDefault()
  dragover.value = false
}

function onDrop(e: DragEvent) {
  e.preventDefault()
  dragover.value = false
  if (loading.value) return
  applyPickedFile(e.dataTransfer?.files?.[0])
}

async function onUpload() {
  if (!fileRef.value) {
    ElMessage.warning('请选择视频文件')
    return
  }
  const f = fileRef.value

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
  <div class="avs-card">
    <div class="avs-card-title">视频上传</div>
    <div class="avs-card-desc">支持 MP4 / AVI / MOV / MKV，单文件 ≤ 2GB</div>

    <div class="upload-content">
      <input
        ref="fileInputRef"
        class="hidden-file-input"
        type="file"
        :accept="accept"
        @change="onPickFile"
      />

      <div
        :class="zoneClasses"
        role="button"
        tabindex="0"
        @click="openFileDialog"
        @keydown.enter.prevent="openFileDialog"
        @keydown.space.prevent="openFileDialog"
        @dragover="onDragOver"
        @dragleave="onDragLeave"
        @drop="onDrop"
      >
        <svg class="upload-zone-icon" viewBox="0 0 24 24" aria-hidden="true">
          <path
            fill="currentColor"
            d="M6 18h11a4 4 0 0 0 1-7.874A6 6 0 0 0 6.062 9.2 4.5 4.5 0 0 0 6 18Zm6-8.586 2.293 2.293-1.414 1.414L13 11.414V16h-2v-4.586l-.879.879-1.414-1.414L11 9.414V8h2v1.414Z"
          />
        </svg>
        <div class="upload-zone-title">点击或拖拽视频文件至此处</div>
        <div class="upload-zone-hint">支持 MP4 / AVI / MOV / MKV，单文件 ≤ 2GB</div>

        <div v-if="fileRef" class="upload-file-info">
          <span class="upload-file-check" aria-hidden="true">
            <svg viewBox="0 0 16 16">
              <path
                fill="currentColor"
                d="M13.78 3.22a.75.75 0 0 1 0 1.06L6.53 11.53a.75.75 0 0 1-1.06 0L2.22 8.28a.75.75 0 1 1 1.06-1.06L6 9.94l6.72-6.72a.75.75 0 0 1 1.06 0Z"
              />
            </svg>
          </span>
          <span class="upload-file-name">{{ fileRef.name }}</span>
          <span class="upload-file-size">{{ formatFileSize(fileRef.size) }}</span>
        </div>
      </div>

      <el-button class="avs-btn-primary w-full" :disabled="uploadDisabled" :loading="loading" @click="onUpload">
        {{ loading ? '上传中...' : '上传并获取 file_id' }}
      </el-button>
    </div>
  </div>
</template>

<style scoped>
.upload-content {
  display: grid;
  gap: 16px;
  margin-top: 16px;
}

.hidden-file-input {
  position: absolute;
  width: 1px;
  height: 1px;
  opacity: 0;
  pointer-events: none;
}

.upload-zone {
  border: 2px dashed var(--primary-border);
  border-radius: 12px;
  padding: 24px;
  min-height: 120px;
  background: var(--primary-light);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  cursor: pointer;
  transition: all 0.15s ease;
}

.upload-zone:hover,
.upload-zone.dragover {
  border-color: var(--primary);
  background: var(--upload-hover);
}

.upload-zone.has-file {
  border-style: solid;
  border-color: var(--primary);
  background: var(--primary-light);
}

.upload-zone-icon {
  width: 32px;
  height: 32px;
  color: var(--primary);
}

.upload-zone-title {
  margin-top: 10px;
  color: var(--text-primary);
  font-size: 14px;
  font-weight: 600;
  line-height: 1.3;
}

.upload-zone-hint {
  margin-top: 4px;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.6;
}

.upload-file-info {
  margin-top: 12px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-radius: 999px;
  background: var(--upload-success-bg);
  color: var(--success-ink);
  font-size: 12px;
  max-width: 100%;
}

.upload-file-check {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  color: var(--success);
}

.upload-file-check svg {
  display: block;
}

.upload-file-name {
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.upload-file-size {
  font-family: var(--font-mono);
  opacity: 0.9;
}
</style>

