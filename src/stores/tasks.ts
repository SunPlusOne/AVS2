import { defineStore } from 'pinia'
import type { TaskProgress } from '@/types/contracts'

const LS_KEY = 'avs.tasks.v1'

function loadFromStorage(): TaskProgress[] {
  try {
    const raw = localStorage.getItem(LS_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as TaskProgress[]
    if (!Array.isArray(parsed)) return []
    return parsed
  } catch {
    return []
  }
}

function saveToStorage(items: TaskProgress[]) {
  localStorage.setItem(LS_KEY, JSON.stringify(items))
}

export const useTasksStore = defineStore('tasks', {
  state: () => ({
    items: loadFromStorage() as TaskProgress[],
  }),
  getters: {
    byId: (state) => {
      const map = new Map<string, TaskProgress>()
      for (const t of state.items) map.set(t.task_id, t)
      return map
    },
  },
  actions: {
    upsert(task: TaskProgress) {
      const idx = this.items.findIndex((t) => t.task_id === task.task_id)
      const next = { ...this.items[idx], ...task }
      if (idx >= 0) {
        this.items.splice(idx, 1, next)
      } else {
        this.items.unshift(next)
      }
      saveToStorage(this.items)
    },
    remove(taskId: string) {
      this.items = this.items.filter((t) => t.task_id !== taskId)
      saveToStorage(this.items)
    },
    clear() {
      this.items = []
      saveToStorage(this.items)
    },
  },
})

