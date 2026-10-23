<script setup lang="ts">
import { computed } from 'vue'

import type { DigestResponse } from '@/api/types'

const props = defineProps<{
  digest: DigestResponse | null
  loading?: boolean
}>()

const emit = defineEmits<{ open: [] }>()

const dateLabel = computed(() => {
  if (!props.digest?.date) return '今日简报'
  const date = new Date(`${props.digest.date}T00:00:00`)
  if (Number.isNaN(date.getTime())) return props.digest.date
  return `${date.getMonth() + 1}月${date.getDate()}日 · 今日简报`
})

const topChange = computed(() => props.digest?.watchlist_changes[0] ?? null)

const gapCount = computed(() => props.digest?.evidence_gaps.length ?? 0)
</script>

<template>
  <section class="digest-card card" @click="emit('open')">
    <div class="digest-card__head">
      <span class="digest-card__badge">
        <van-icon name="notes-o" size="12" />
        每日简报
      </span>
      <span class="digest-card__date">{{ dateLabel }}</span>
    </div>

    <p v-if="loading" class="digest-card__loading">正在整理你的研究简报…</p>

    <template v-else-if="digest">
      <div class="digest-card__metrics">
        <div class="digest-card__metric">
          <span class="digest-card__metric-value mono">
            {{ digest.followed_updates.length }}
          </span>
          <span class="digest-card__metric-label">关注更新</span>
        </div>
        <div class="digest-card__metric">
          <span class="digest-card__metric-value mono">
            {{ digest.watchlist_changes.length }}
          </span>
          <span class="digest-card__metric-label">自选变化</span>
        </div>
        <div class="digest-card__metric">
          <span class="digest-card__metric-value mono">{{ gapCount }}</span>
          <span class="digest-card__metric-label">证据缺口</span>
        </div>
      </div>

      <p v-if="topChange" class="digest-card__line">
        <span class="digest-card__stock">
          {{ topChange.security.name }}
          <span class="mono">{{ topChange.security.code }}</span>
        </span>
        <span
          v-if="topChange.score_delta !== null"
          class="digest-card__delta mono"
          :class="
            topChange.score_delta > 0
              ? 'up'
              : topChange.score_delta < 0
                ? 'down'
                : 'neutral'
          "
        >
          {{ topChange.score_delta > 0 ? '+' : '' }}{{ topChange.score_delta.toFixed(1) }}
        </span>
        <span v-else class="digest-card__muted">评分 {{ topChange.display_label }}</span>
      </p>
      <p v-else-if="!digest.followed_updates.length" class="digest-card__line digest-card__muted">
        关注作者今日暂无更新，添加自选股可追踪评分变化。
      </p>

      <div class="digest-card__foot">
        <span>查看关注更新、评分变化与推荐作者</span>
        <van-icon name="arrow" size="12" />
      </div>
    </template>

    <p v-else class="digest-card__loading">简报暂时不可用，稍后再试。</p>
  </section>
</template>

<style scoped>
.digest-card {
  padding: 15px 16px 13px;
  margin-bottom: 12px;
  background:
    radial-gradient(320px 140px at 110% -30%, rgba(194, 65, 12, 0.1), transparent 70%),
    #fff;
  cursor: pointer;
}

.digest-card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.digest-card__badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  border-radius: 6px;
  background: var(--rs-accent-soft);
  color: var(--rs-accent);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.05em;
}

.digest-card__date {
  font-size: 10.5px;
  color: var(--rs-muted);
}

.digest-card__loading {
  margin: 12px 0 2px;
  font-size: 11.5px;
  color: var(--rs-muted);
}

.digest-card__metrics {
  display: flex;
  gap: 6px;
  margin-top: 12px;
}

.digest-card__metric {
  flex: 1;
  padding: 9px 10px;
  border-radius: 10px;
  background: #f8fafc;
}

.digest-card__metric-value {
  display: block;
  font-size: 18px;
  font-weight: 700;
  color: var(--rs-ink);
  line-height: 1.1;
}

.digest-card__metric-label {
  display: block;
  margin-top: 3px;
  font-size: 9.5px;
  color: var(--rs-muted);
}

.digest-card__line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin: 11px 0 0;
  font-size: 11px;
  color: var(--rs-ink-soft);
}

.digest-card__stock {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 600;
}

.digest-card__stock .mono {
  margin-left: 4px;
  font-size: 9.5px;
  font-weight: 400;
  color: var(--rs-muted);
}

.digest-card__delta {
  flex: none;
  font-size: 12px;
  font-weight: 700;
}

.digest-card__muted {
  color: var(--rs-muted);
}

.digest-card__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 11px;
  padding-top: 10px;
  border-top: 1px dashed var(--rs-line);
  font-size: 10px;
  color: var(--rs-muted);
}
</style>
