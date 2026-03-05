export type AlgorithmId = 'avsegformer' | 'vct' | 'combo'
export type TaskStatus = 'queued' | 'running' | 'completed' | 'failed' | 'canceled'

export interface UploadResponse {
  file_id: string
  filename: string
  size_bytes: number
}

export interface CreateTaskRequest {
  file_id: string
  algorithm: AlgorithmId
}

export interface TaskProgress {
  task_id: string
  status: TaskStatus
  progress: number
  current_frame?: number
  total_frames?: number
  message?: string
  algorithm?: AlgorithmId
  created_at?: string
  updated_at?: string
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
}

export interface LogEntry {
  ts: string
  level: string
  message: string
}

