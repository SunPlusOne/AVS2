import { api } from '@/api/http'
import type {
  AdminLoginResponse,
  AlgorithmInfo,
  CreateTaskRequest,
  LogEntry,
  TaskProgress,
  TaskReport,
  UploadResponse,
  UserLoginResponse,
} from '@/types/contracts'

type TaskAssetUrlOptions = {
  cacheBust?: string | number
  authToken?: string
}

function buildTaskAssetUrl(path: string, options?: TaskAssetUrlOptions): string {
  const params = new URLSearchParams()
  if (options?.cacheBust != null) {
    params.set('v', String(options.cacheBust))
  }
  if (options?.authToken) {
    params.set('token', options.authToken)
  }
  const query = params.toString()
  return query ? `${path}?${query}` : path
}

export async function uploadVideo(file: File): Promise<UploadResponse> {
  const form = new FormData()
  form.append('file', file)
  const { data } = await api.post<UploadResponse>('/api/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function listAlgorithms(): Promise<AlgorithmInfo[]> {
  const { data } = await api.get<AlgorithmInfo[]>('/api/algorithms')
  return data
}

export async function createTask(body: CreateTaskRequest): Promise<{ task_id: string }> {
  const { data } = await api.post<{ task_id: string }>('/api/tasks', body)
  return data
}

export async function getTask(taskId: string): Promise<TaskProgress> {
  const { data } = await api.get<TaskProgress>(`/api/tasks/${encodeURIComponent(taskId)}`)
  return data
}

export async function getTaskReport(taskId: string): Promise<TaskReport> {
  const { data } = await api.get<TaskReport>(`/api/tasks/${encodeURIComponent(taskId)}/report`)
  return data
}

export async function cancelTask(taskId: string): Promise<{ ok: true }> {
  const { data } = await api.delete<{ ok: true }>(`/api/tasks/${encodeURIComponent(taskId)}`)
  return data
}

export function getResultUrl(taskId: string, options?: TaskAssetUrlOptions): string {
  const path = `/api/tasks/${encodeURIComponent(taskId)}/result`
  return buildTaskAssetUrl(path, options)
}

export function getMasksUrl(taskId: string, options?: TaskAssetUrlOptions): string {
  const path = `/api/tasks/${encodeURIComponent(taskId)}/masks`
  return buildTaskAssetUrl(path, options)
}

export async function adminLogin(username: string, password: string): Promise<AdminLoginResponse> {
  const { data } = await api.post<AdminLoginResponse>('/api/admin/login', { username, password })
  return data
}

export async function userLogin(username: string, password: string): Promise<UserLoginResponse> {
  const { data } = await api.post<UserLoginResponse>('/api/user/login', { username, password })
  return data
}

export async function userRegister(username: string, password: string): Promise<{ ok: true }> {
  const { data } = await api.post<{ ok: true }>('/api/user/register', { username, password })
  return data
}

export async function getAdminLogs(token: string, params?: { limit?: number }): Promise<LogEntry[]> {
  const { data } = await api.get<LogEntry[]>('/api/admin/logs', {
    params,
    headers: { Authorization: `Bearer ${token}` },
  })
  return data
}

export async function adminUploadModel(
  token: string,
  payload: {
    algorithm_id: string
    name: string
    version: string
    description: string
    input_size: string
    enabled: boolean
    weight_file: File
  },
): Promise<{ ok: true }> {
  const form = new FormData()
  form.append('algorithm_id', payload.algorithm_id)
  form.append('name', payload.name)
  form.append('version', payload.version)
  form.append('description', payload.description)
  form.append('input_size', payload.input_size)
  form.append('enabled', String(payload.enabled))
  form.append('file', payload.weight_file)

  const { data } = await api.post<{ ok: true }>('/api/admin/models', form, {
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'multipart/form-data' },
  })
  return data
}

