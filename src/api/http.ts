import axios from 'axios'
import { useAuthStore } from '@/stores/auth'

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '',
  timeout: 60_000,
})

api.interceptors.request.use((config) => {
  const hasAuthHeader = Boolean(config.headers?.Authorization || config.headers?.authorization)
  if (hasAuthHeader) return config

  const auth = useAuthStore()
  if (auth.token) {
    const headers = (config.headers ?? {}) as any
    if (typeof headers.set === 'function') {
      headers.set('Authorization', `Bearer ${auth.token}`)
    } else {
      headers.Authorization = `Bearer ${auth.token}`
    }
    config.headers = headers
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = Number(error?.response?.status ?? 0)
    if (status === 401) {
      const auth = useAuthStore()
      if (auth.token) {
        auth.clear()
      }

      if (typeof window !== 'undefined') {
        const path = window.location.pathname
        if (path !== '/login') {
          const redirect = encodeURIComponent(path + window.location.search)
          window.location.href = `/login?redirect=${redirect}`
        }
      }
    }
    return Promise.reject(error)
  },
)

export function getWsBaseUrl(): string {
  const env = import.meta.env.VITE_WS_BASE_URL
  if (typeof env === 'string' && env.length > 0) return env

  const isHttps = window.location.protocol === 'https:'
  const wsProto = isHttps ? 'wss' : 'ws'
  return `${wsProto}://${window.location.host}`
}

