import { defineStore } from 'pinia'
import type { UserRole } from '@/types/contracts'

function decodeJwtRole(token: string): UserRole | '' {
  if (!token) return ''
  const parts = token.split('.')
  if (parts.length < 2) return ''

  try {
    const b64 = parts[1].replace(/-/g, '+').replace(/_/g, '/')
    const padded = b64.padEnd(Math.ceil(b64.length / 4) * 4, '=')
    const payload = JSON.parse(atob(padded)) as { role?: string }
    if (payload.role === 'admin' || payload.role === 'user') {
      return payload.role
    }
  } catch {
    return ''
  }

  return ''
}

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: '',
    role: '' as UserRole | '',
  }),
  getters: {
    isLoggedIn: (state) => state.token.length > 0 && !!state.role,
    isAdmin: (state) => state.role === 'admin',
  },
  actions: {
    setAuth(token: string) {
      this.token = token
      this.role = decodeJwtRole(token)
    },
    clear() {
      this.token = ''
      this.role = ''
    },
  },
})
