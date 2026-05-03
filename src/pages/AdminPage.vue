<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getAdminLogs } from '@/api/avs'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()

const logs = ref<{ ts: string; level: string; message: string }[]>([])
const loadingLogs = ref(false)

const benchmarkRows = [
  { model: 'AVSegFormer', s4_jf: '78.4%', ms3_jf: '54.0%', avis_metric: '--', params: '47M', speed: '~50ms/帧' },
  { model: 'VCT', s4_jf: '81.2%', ms3_jf: '58.3%', avis_metric: '--', params: '52M', speed: '~80ms/帧' },
  { model: 'COMBO', s4_jf: '83.1%', ms3_jf: '61.7%', avis_metric: '--', params: '68M', speed: '~100ms/帧' },
  { model: 'AVIS', s4_jf: '-', ms3_jf: '-', avis_metric: '52.49 / 71.13 / 53.46', params: '-', speed: '-' },
]

const authed = computed(() => auth.isLoggedIn && auth.isAdmin)

async function onRefreshLogs() {
  if (!authed.value) {
    ElMessage.warning('请先登录')
    return
  }
  loadingLogs.value = true
  try {
    logs.value = await getAdminLogs(auth.token, { limit: 200 })
  } catch (e: any) {
    ElMessage.error(e?.message ?? '加载日志失败')
  } finally {
    loadingLogs.value = false
  }
}
</script>

<template>
  <div class="grid gap-5">
    <div>
      <div class="page-heading">管理员后台</div>
      <div class="page-subheading">系统日志查询</div>
    </div>

    <div class="avs-card">
      <div class="avs-card-title">基准性能（AVSBench + AVIS 官方指标）</div>
      <div class="avs-card-desc">AVIS 行使用官方仓库 checkpoints 指标（FSLA / HOTA / mAP），其任务定义与 AVSBench 不同。</div>

      <el-table class="avs-table benchmark-table" :data="benchmarkRows" size="small" style="width: 100%">
        <el-table-column prop="model" label="模型" min-width="140" />
        <el-table-column prop="s4_jf" label="S4 J&F" min-width="120" />
        <el-table-column prop="ms3_jf" label="MS3 J&F" min-width="120" />
        <el-table-column prop="avis_metric" label="AVIS(FSLA/HOTA/mAP)" min-width="210" />
        <el-table-column prop="params" label="参数量" min-width="120" />
        <el-table-column prop="speed" label="推理速度" min-width="140" />
      </el-table>
    </div>

    <div class="avs-card">
      <div class="flex items-end justify-between gap-3">
        <div>
          <div class="avs-card-title">系统日志</div>
          <div class="avs-card-desc">支持按最新 N 条获取</div>
        </div>
        <div class="flex gap-2">
          <el-button class="avs-btn-secondary" :loading="loadingLogs" @click="onRefreshLogs">刷新</el-button>
        </div>
      </div>

      <div class="logs-panel">
        <div v-if="logs.length === 0" class="logs-empty">暂无日志</div>
        <div v-for="(l, idx) in logs" :key="idx" class="logs-row">
          <span class="logs-time mono-text">{{ l.ts }}</span>
          <span class="logs-level">[{{ l.level }}]</span>
          <span class="ml-2">{{ l.message }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.logs-panel {
  margin-top: 16px;
  max-height: 360px;
  overflow: auto;
  border: 1px solid var(--border-default);
  border-radius: 12px;
  background: var(--bg-hover);
  padding: 12px;
}

.logs-empty {
  color: var(--text-secondary);
  font-size: 12px;
}

.logs-row {
  color: var(--text-primary);
  font-size: 12px;
  line-height: 1.7;
}

.logs-time,
.logs-level {
  color: var(--text-secondary);
}

.benchmark-table {
  margin-top: 12px;
}
</style>

