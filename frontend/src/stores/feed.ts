import { ref } from 'vue'
import { defineStore } from 'pinia'

import { api } from '@/api/client'
import type { FeedResponse, FeedScope, FeedSort, FeedWindow, ReportItem } from '@/api/types'

export const useFeedStore = defineStore('feed', () => {
  const items = ref<ReportItem[]>([])
  const loading = ref(false)
  const finished = ref(false)
  const scope = ref<FeedScope>('following')
  const sort = ref<FeedSort>('smart')
  const window = ref<FeedWindow>('30d')
  const cursor = ref<string | null>(null)
  const error = ref<string | null>(null)

  let requestSeq = 0

  async function load(reset = false): Promise<void> {
    if (loading.value) return
    if (reset) {
      requestSeq += 1
      items.value = []
      cursor.value = null
      finished.value = false
      error.value = null
    }
    if (finished.value && !reset) return

    const seq = requestSeq
    loading.value = true
    try {
      const response = await api.get<FeedResponse>('/feed', {
        scope: scope.value,
        sort: sort.value,
        window: window.value,
        limit: 20,
        cursor: cursor.value ?? undefined,
      })
      if (seq !== requestSeq) return
      items.value = reset ? response.items : [...items.value, ...response.items]
      cursor.value = response.next_cursor
      finished.value = !response.has_more
    } catch (err) {
      if (seq === requestSeq) {
        error.value = err instanceof Error ? err.message : '加载失败'
        finished.value = true
      }
    } finally {
      if (seq === requestSeq) loading.value = false
    }
  }

  async function refresh(): Promise<void> {
    await load(true)
  }

  function setScope(next: FeedScope): void {
    if (scope.value === next) return
    scope.value = next
    sort.value = next === 'following' ? 'smart' : 'hot'
    window.value = next === 'following' ? '30d' : '72h'
    void load(true)
  }

  function setSort(next: FeedSort): void {
    if (sort.value === next) return
    sort.value = next
    void load(true)
  }

  function setWindow(next: FeedWindow): void {
    if (window.value === next) return
    window.value = next
    void load(true)
  }

  return {
    items,
    loading,
    finished,
    scope,
    sort,
    window,
    cursor,
    error,
    load,
    refresh,
    setScope,
    setSort,
    setWindow,
  }
})
