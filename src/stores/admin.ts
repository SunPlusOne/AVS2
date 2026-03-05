import { defineStore } from 'pinia'

const LS_KEY = 'avs.admin.token.v1'

export const useAdminStore = defineStore('admin', {
  state: () => ({
    token: (localStorage.getItem(LS_KEY) ?? '') as string,
  }),
  actions: {
    setToken(token: string) {
      this.token = token
      localStorage.setItem(LS_KEY, token)
    },
    clear() {
      this.setToken('')
    },
  },
})

