import { defineStore } from 'pinia'
import type { AlgorithmInfo } from '@/types/contracts'
import { listAlgorithms } from '@/api/avs'

export const useAlgorithmsStore = defineStore('algorithms', {
  state: () => ({
    items: [] as AlgorithmInfo[],
    loading: false,
    error: '' as string,
  }),
  getters: {
    enabledItems(state): AlgorithmInfo[] {
      return state.items.filter((a) => a.enabled)
    },
  },
  actions: {
    async refresh() {
      this.loading = true
      this.error = ''
      try {
        this.items = await listAlgorithms()
      } catch (e: any) {
        this.error = e?.message ?? '加载算法列表失败'
      } finally {
        this.loading = false
      }
    },
  },
})

