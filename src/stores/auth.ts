import { defineStore } from 'pinia'
import type { UserRole } from '@/types/contracts'

const AUTH_TOKEN_KEY = 'avs_auth_token'

function readStoredToken(): string {
  if (typeof window === 'undefined') return ''
  return window.localStorage.getItem(AUTH_TOKEN_KEY) ?? ''
}

function writeStoredToken(token: string) {
  if (typeof window === 'undefined') return
  if (token) {
    window.localStorage.setItem(AUTH_TOKEN_KEY, token)
  } else {
    window.localStorage.removeItem(AUTH_TOKEN_KEY)
  }
}

type DecodedAuth = {
  role: UserRole | ''
  username: string
}

function decodeAuthFromJwt(token: string): DecodedAuth {
  if (!token) return { role: '', username: '' }
  const parts = token.split('.')
  if (parts.length < 2) return { role: '', username: '' }

  try {
    const b64 = parts[1].replace(/-/g, '+').replace(/_/g, '/')
    const padded = b64.padEnd(Math.ceil(b64.length / 4) * 4, '=')
    const payload = JSON.parse(atob(padded)) as { role?: string; sub?: string; exp?: number }
    const exp = Number(payload.exp)
    if (Number.isFinite(exp) && exp > 0) {
      const now = Math.floor(Date.now() / 1000)
      if (exp <= now) return { role: '', username: '' }
    }
    const role: UserRole | '' = payload.role === 'admin' || payload.role === 'user' ? payload.role : ''
    const username = typeof payload.sub === 'string' ? payload.sub : ''
    return { role, username }
  } catch {
    return { role: '', username: '' }
  }
}

export const useAuthStore = defineStore('auth', {
  state: () => {
    const token = readStoredToken()
    const decoded = decodeAuthFromJwt(token)
    return {
      token,
      role: decoded.role,
      username: decoded.username,
    }
  },
  getters: {
    isLoggedIn: (state) => state.token.length > 0 && !!state.role,
    isAdmin: (state) => state.role === 'admin',
  },
  actions: {
    setAuth(token: string) {
      const decoded = decodeAuthFromJwt(token)
      this.token = token
      this.role = decoded.role
      this.username = decoded.username
      writeStoredToken(token)
    },
    clear() {
      this.token = ''
      this.role = ''
      this.username = ''
      writeStoredToken('')
    },
    hydrate() {
      const token = readStoredToken()
      const decoded = decodeAuthFromJwt(token)
      this.token = token
      this.role = decoded.role
      this.username = decoded.username
    },
  },
})
