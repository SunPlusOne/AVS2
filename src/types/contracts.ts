export type AlgorithmId = 'avsegformer' | 'avis' | 'vct' | 'combo'
export type InferenceScene = 'single_source' | 'multi_source'
export type TaskStatus = 'queued' | 'running' | 'completed' | 'failed' | 'canceled'
export type UserRole = 'admin' | 'user'

export interface UploadResponse {
  file_id: string
  filename: string
  size_bytes: number
  duration_seconds?: number
  width?: number
  height?: number
  fps?: number
  total_frames?: number
  audio_energy?: number
}

export interface CreateTaskRequest {
  file_id: string
  algorithm: AlgorithmId
  scene?: InferenceScene
}

export interface TaskProgress {
  task_id: string
  status: TaskStatus
  progress: number
  current_frame?: number
  total_frames?: number
  message?: string
  algorithm?: AlgorithmId
  scene?: InferenceScene
  resolved_scene?: 'single_source' | 'multi_source'
  filename?: string
  fps?: number
  duration_seconds?: number
  width?: number
  height?: number
  metrics?: TaskMetrics
  created_at?: string
  updated_at?: string
}

export interface TaskMetrics {
  jaccard?: number
  f_measure?: number
  jf_mean?: number
  map?: number
  hota?: number
  fsla?: number
  total_inference_ms?: number
  avg_frame_ms?: number
  processed_frames?: number
}

export interface TaskReport {
  task_id: string
  algorithm: AlgorithmId | string
  subset?: string
  frames?: number
  fps?: number
  duration_seconds?: number
  width?: number
  height?: number
  metrics?: TaskMetrics
  processing?: {
    total_ms?: number
    avg_frame_ms?: number
    processed_frames?: number
  }
  mask_coverage_pct_by_frame?: number[]
  note?: string
}

export interface AlgorithmInfo {
  id: AlgorithmId
  name: string
  version?: string
  description: string
  input_size?: string
  enabled: boolean
}

export interface AdminLoginResponse {
  token: string
  expires_at: string
  role: UserRole
}

export interface UserLoginResponse {
  token: string
  expires_at: string
  role: UserRole
}

export interface LogEntry {
  ts: string
  level: string
  message: string
}

