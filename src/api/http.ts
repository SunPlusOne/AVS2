import axios from 'axios'

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '',
  timeout: 60_000,
})

export function getWsBaseUrl(): string {
  const env = import.meta.env.VITE_WS_BASE_URL
  if (typeof env === 'string' && env.length > 0) return env

  const isHttps = window.location.protocol === 'https:'
  const wsProto = isHttps ? 'wss' : 'ws'
  return `${wsProto}://${window.location.host}`
}

