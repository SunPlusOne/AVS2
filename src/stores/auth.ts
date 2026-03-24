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

function decodeJwtRole(token: string): UserRole | '' {
  if (!token) return ''
  const parts = token.split('.')
  if (parts.length < 2) return ''

  try {
    const b64 = parts[1].replace(/-/g, '+').replace(/_/g, '/')
    const padded = b64.padEnd(Math.ceil(b64.length / 4) * 4, '=')
    const payload = JSON.parse(atob(padded)) as { role?: string; exp?: number }
    const exp = Number(payload.exp)
    if (Number.isFinite(exp) && exp > 0) {
      const now = Math.floor(Date.now() / 1000)
      if (exp <= now) return ''
    }
    if (payload.role === 'admin' || payload.role === 'user') {
      return payload.role
    }
  } catch {
    return ''
  }

  return ''
}

export const useAuthStore = defineStore('auth', {
  state: () => {
    const token = readStoredToken()
    return {
      token,
      role: decodeJwtRole(token) as UserRole | '',
    }
  },
  getters: {
    isLoggedIn: (state) => state.token.length > 0 && !!state.role,
    isAdmin: (state) => state.role === 'admin',
  },
  actions: {
    setAuth(token: string) {
      this.token = token
      this.role = decodeJwtRole(token)
      writeStoredToken(token)
    },
    clear() {
      this.token = ''
      this.role = ''
      writeStoredToken('')
    },
    hydrate() {
      const token = readStoredToken()
      this.token = token
      this.role = decodeJwtRole(token)
    },
  },
})
