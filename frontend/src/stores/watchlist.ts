import { ref } from 'vue'
import { defineStore } from 'pinia'

import { api } from '@/api/client'
import type { Message, ScoreScope, WatchlistItem } from '@/api/types'

export const WATCHLIST_SCOPE_KEY = 'rs_watchlist_scope'

const SCOPES: ScoreScope[] = ['personal', 'hybrid', 'all']

function storedScope(): ScoreScope {
  const value = localStorage.getItem(WATCHLIST_SCOPE_KEY) as ScoreScope | null
  return value && SCOPES.includes(value) ? value : 'hybrid'
}

export const useWatchlistStore = defineStore('watchlist', () => {
  const items = ref<WatchlistItem[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  const scope = ref<ScoreScope>(storedScope())
  const window = ref<'7d' | '30d' | '90d'>('30d')

  async function load(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      items.value = await api.get<WatchlistItem[]>('/watchlist', {
        scope: scope.value,
        window: window.value,
      })
    } catch (err) {
      error.value = err instanceof Error ? err.message : '加载失败'
    } finally {
      loading.value = false
    }
  }

  async function add(securityId: number | null, code: string | null): Promise<WatchlistItem> {
    const item = await api.post<WatchlistItem>('/watchlist', {
      security_id: securityId,
      code,
    })
    await load()
    return item
  }

  async function remove(securityId: number): Promise<void> {
    await api.delete<Message>(`/watchlist/${securityId}`)
    items.value = items.value.filter((item) => item.security.id !== securityId)
  }

  async function setScope(next: ScoreScope): Promise<void> {
    if (scope.value === next) return
    scope.value = next
    localStorage.setItem(WATCHLIST_SCOPE_KEY, next)
    await load()
  }

  async function setWindow(next: '7d' | '30d' | '90d'): Promise<void> {
    if (window.value === next) return
    window.value = next
    await load()
  }

  return { items, loading, error, scope, window, load, add, remove, setScope, setWindow }
})
