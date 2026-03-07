<script setup lang="ts">
import { computed } from 'vue'
import type { TaskProgress } from '@/types/contracts'

const props = defineProps<{
  task: TaskProgress | null
  onCancel?: () => void
}>()

const statusMeta = computed(() => {
  const status = props.task?.status
  if (!status) return { label: '未开始', cls: 'status-idle', icon: 'dot' }
  if (status === 'queued') return { label: '未开始', cls: 'status-idle', icon: 'dot' }
  if (status === 'running') return { label: '处理中', cls: 'status-warning', icon: 'spinner' }
  if (status === 'completed') return { label: '已完成', cls: 'status-success', icon: 'check' }
  if (status === 'failed') return { label: '失败', cls: 'status-danger', icon: 'cross' }
  if (status === 'canceled') return { label: '已取消', cls: 'status-idle', icon: 'cross' }
  return { label: status, cls: 'status-idle', icon: 'dot' }
})

const percentage = computed(() => {
  const value = Number(props.task?.progress ?? 0)
  if (!Number.isFinite(value)) return 0
  return Math.max(0, Math.min(100, Math.round(value)))
})

const frameText = computed(() => {
  if (props.task?.current_frame != null && props.task.total_frames != null) {
    return `${props.task.current_frame} / ${props.task.total_frames} 帧`
  }
  return '—'
})

const statusDescription = computed(() => {
  if (!props.task) return '任务尚未开始'
  if (props.task.status === 'running' && props.task.current_frame != null && props.task.total_frames != null) {
    return `正在处理第 ${props.task.current_frame} 帧 / 共 ${props.task.total_frames} 帧`
  }
  if (props.task.status === 'queued') return '任务已进入队列，等待计算资源'
  if (props.task.status === 'completed') return '处理完成，可在结果区预览与下载'
  if (props.task.status === 'failed') return '处理失败，请检查日志后重试'
  if (props.task.status === 'canceled') return '任务已取消'
  return props.task.message ?? '处理中'
})
</script>

<template>
  <div class="avs-card">
    <div class="task-head">
      <div>
        <div class="avs-card-title">任务状态</div>
        <div v-if="task" class="task-id mono-text">task_id：{{ task.task_id }}</div>
      </div>
      <span class="status-badge" :class="statusMeta.cls">
        <span class="status-icon" :class="statusMeta.icon" aria-hidden="true"></span>
        {{ statusMeta.label }}
      </span>
    </div>

    <div class="task-body">
      <div class="progress-row">
        <div class="progress-track">
          <div class="progress-fill" :style="{ width: `${percentage}%` }"></div>
        </div>
        <span class="progress-number mono-text">{{ percentage }}%</span>
      </div>

      <div class="progress-meta">
        <span>{{ frameText }}</span>
        <span v-if="task?.algorithm">算法：{{ task.algorithm }}</span>
      </div>

      <div class="progress-desc">{{ statusDescription }}</div>

      <div v-if="task?.message" class="task-message">
        {{ task.message }}
      </div>
    </div>

    <div class="task-actions">
      <el-button
        v-if="task && (task.status === 'queued' || task.status === 'running')"
        class="avs-btn-secondary"
        @click="onCancel?.()"
      >
        取消任务
      </el-button>
    </div>
  </div>
</template>

<style scoped>
.task-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.task-id {
  margin-top: 6px;
  color: var(--text-secondary);
  font-size: 12px;
}

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border-radius: var(--radius-sm);
  padding: 3px 10px;
  font-size: 12px;
  font-weight: 500;
  animation: status-fade 0.2s ease;
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

.status-icon {
  display: inline-block;
  width: 12px;
  height: 12px;
  position: relative;
}

.status-icon.dot {
  border-radius: 999px;
  background: currentColor;
  opacity: 0.65;
}

.status-icon.spinner {
  border: 1.5px solid currentColor;
  border-right-color: transparent;
  border-radius: 999px;
  animation: spin 0.8s linear infinite;
}

.status-icon.check::before {
  content: '';
  position: absolute;
  left: 3px;
  top: 1px;
  width: 4px;
  height: 7px;
  border-right: 2px solid currentColor;
  border-bottom: 2px solid currentColor;
  transform: rotate(45deg);
}

.status-icon.cross::before,
.status-icon.cross::after {
  content: '';
  position: absolute;
  left: 5px;
  top: 1px;
  width: 2px;
  height: 10px;
  background: currentColor;
  border-radius: 2px;
}

.status-icon.cross::before {
  transform: rotate(45deg);
}

.status-icon.cross::after {
  transform: rotate(-45deg);
}

.task-body {
  margin-top: 16px;
}

.progress-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.progress-track {
  height: 8px;
  flex: 1;
  overflow: hidden;
  border-radius: 99px;
  background: var(--border-default);
}

.progress-fill {
  height: 100%;
  border-radius: 99px;
  background: linear-gradient(90deg, var(--primary), var(--primary-accent));
  transition: width 0.4s ease;
}

.progress-number {
  min-width: 52px;
  text-align: right;
  color: var(--primary);
  font-size: 14px;
  font-weight: 600;
}

.progress-meta {
  margin-top: 8px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  color: var(--text-secondary);
  font-size: 12px;
}

.progress-desc {
  margin-top: 6px;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.task-message {
  margin-top: 10px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  background: var(--bg-hover);
  padding: 10px 12px;
  color: var(--text-primary);
  font-size: 13px;
  line-height: 1.6;
}

.task-actions {
  margin-top: 16px;
  display: flex;
  gap: 8px;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@keyframes status-fade {
  from {
    opacity: 0;
    transform: translateY(4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
