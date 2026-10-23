import { ref } from 'vue'
import { defineStore } from 'pinia'

import { api } from '@/api/client'
import type { DigestResponse, ScoreScope } from '@/api/types'

export const useDigestStore = defineStore('digest', () => {
  const digest = ref<DigestResponse | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  let requestSeq = 0

  async function load(
    options: { date?: string; scope?: ScoreScope; window?: string } = {},
  ): Promise<void> {
    const seq = ++requestSeq
    loading.value = true
    error.value = null
    try {
      const response = await api.get<DigestResponse>('/digest', {
        date: options.date,
        scope: options.scope,
        window: options.window ?? '30d',
      })
      if (seq === requestSeq) digest.value = response
    } catch (err) {
      if (seq === requestSeq) {
        error.value = err instanceof Error ? err.message : '简报加载失败'
      }
    } finally {
      if (seq === requestSeq) loading.value = false
    }
  }

  return { digest, loading, error, load }
})
