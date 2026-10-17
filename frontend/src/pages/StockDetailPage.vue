<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { showToast } from 'vant'

import { api } from '@/api/client'
import type { ScoreBreakdownItem, StockDetail } from '@/api/types'
import ReportCard from '@/components/ReportCard.vue'
import ScoreComposition from '@/components/ScoreComposition.vue'
import ScoreRing from '@/components/ScoreRing.vue'
import { categoryLabel, formatWindow } from '@/utils/format'
import { useWatchlistStore } from '@/stores/watchlist'

const route = useRoute()
const router = useRouter()
const watchlist = useWatchlistStore()

const detail = ref<StockDetail | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)
const scope = ref<'all' | 'followed'>('all')
const timeWindow = ref<'7d' | '30d' | '90d'>('30d')
const showAllBreakdown = ref(false)
const watchSaving = ref(false)

const windows: Array<'7d' | '30d' | '90d'> = ['7d', '30d', '90d']

const security = computed(() => detail.value?.security ?? null)
const score = computed(() => detail.value?.score ?? null)
const inWatchlist = computed(() =>
  security.value
    ? watchlist.items.some((item) => item.security.id === security.value?.id)
    : false,
)

const sortedBreakdown = computed<ScoreBreakdownItem[]>(() => {
  const items = [...(score.value?.breakdown ?? [])]
  return items.sort(
    (a, b) =>
      b.effective_weight * Math.abs(b.score) - a.effective_weight * Math.abs(a.score),
  )
})

const maxWeight = computed(() =>
  Math.max(...sortedBreakdown.value.map((item) => item.effective_weight), 0.0001),
)

const visibleBreakdown = computed(() =>
  showAllBreakdown.value ? sortedBreakdown.value : sortedBreakdown.value.slice(0, 6),
)

const categoryChips = computed(() => {
  const counts = score.value?.category_counts ?? {}
  return ['stock', 'industry', 'macro']
    .map((key) => ({ key, label: categoryLabel(key), count: counts[key] ?? 0 }))
    .filter((entry) => entry.count > 0)
})

const displayScore = computed(() =>
  score.value?.display_score === undefined ? null : score.value.display_score,
)

const scoreTone = computed(() => {
  const value = displayScore.value
  if (value === null) return 'neutral'
  if (value >= 55) return 'up'
  if (value <= 45) return 'down'
  return 'neutral'
})

function weightPercent(item: ScoreBreakdownItem): number {
  return Math.max(4, Math.min(100, (item.effective_weight / maxWeight.value) * 100))
}

function openReport(reportId: number): void {
  void router.push({ name: 'report', params: { id: reportId } })
}

function goBack(): void {
  if (window.history.length > 1) router.back()
  else void router.push('/watchlist')
}

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    detail.value = await api.get<StockDetail>(`/stocks/${route.params.code}`, {
      scope: scope.value,
      window: timeWindow.value,
      limit: 20,
    })
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败'
  } finally {
    loading.value = false
  }
}

async function changeScope(next: 'all' | 'followed'): Promise<void> {
  if (scope.value === next) return
  scope.value = next
  await load()
}

async function changeWindow(next: '7d' | '30d' | '90d'): Promise<void> {
  if (timeWindow.value === next) return
  timeWindow.value = next
  await load()
}

async function toggleWatchlist(): Promise<void> {
  if (!security.value) return
  watchSaving.value = true
  try {
    if (inWatchlist.value) {
      await watchlist.remove(security.value.id)
      showToast('已移出自选')
    } else {
      await watchlist.add(security.value.id, null)
      showToast('已加入自选')
    }
  } catch (err) {
    showToast(err instanceof Error ? err.message : '操作失败')
  } finally {
    watchSaving.value = false
  }
}

onMounted(async () => {
  await load()
  if (!watchlist.items.length) await watchlist.load()
})
</script>

<template>
  <div class="page page--plain stock-page">
    <header class="stock-nav">
      <button type="button" class="stock-nav__back" aria-label="返回" @click="goBack">
        <van-icon name="arrow-left" size="18" />
      </button>
      <span class="stock-nav__title">综合评分</span>
      <button
        v-if="security"
        type="button"
        class="stock-nav__watch"
        :class="{ 'is-active': inWatchlist }"
        :disabled="watchSaving"
        @click="toggleWatchlist"
      >
        <van-icon :name="inWatchlist ? 'star' : 'star-o'" size="13" />
        {{ inWatchlist ? '已自选' : '加自选' }}
      </button>
      <span v-else class="stock-nav__watch is-placeholder" />
    </header>

    <div v-if="loading" class="stock-loading">
      <van-loading size="24" vertical>正在聚合多篇研报…</van-loading>
      <p class="stock-loading__hint">首次生成 AI 结论可能需要几秒</p>
    </div>

    <div v-else-if="error" class="empty-state">
      <van-icon name="warning-o" size="32" />
      <p class="empty-state__title">无法读取这只股票</p>
      <p class="empty-state__text">{{ error }}</p>
      <van-button size="small" round class="retry" @click="load">重试</van-button>
    </div>

    <template v-else-if="detail && score">
      <section class="stock-hero">
        <div class="stock-hero__identity">
          <p class="stock-hero__eyebrow">WEIGHTED SIGNAL</p>
          <h1 class="stock-hero__name">{{ detail.security.name }}</h1>
          <p class="stock-hero__code mono">
            {{ detail.security.code }}
            <span class="stock-hero__exchange">{{ detail.security.exchange }}</span>
          </p>
        </div>
        <ScoreRing :value="displayScore" :size="96" :stroke="8" caption="综合得分" />
      </section>

      <section class="stock-conclusion card">
        <div class="stock-conclusion__head">
          <span class="stock-conclusion__badge">
            <van-icon name="magic" size="11" />
            AI 结论
          </span>
          <span class="stock-conclusion__meta">
            {{ score.report_count }} 篇研报 · 有效样本 {{ score.n_eff.toFixed(1) }}
          </span>
        </div>
        <p class="stock-conclusion__text" :class="scoreTone">
          {{ score.conclusion || '暂无足够研报形成结论。' }}
        </p>
        <div class="stock-conclusion__chips">
          <span v-for="entry in categoryChips" :key="entry.key" class="chip" :class="`chip--${entry.key}`">
            {{ entry.label }} {{ entry.count }}
          </span>
          <span class="chip chip--outline">聚合置信度 {{ Math.round(score.confidence * 100) }}%</span>
        </div>
      </section>

      <div class="stock-controls">
        <div class="stock-controls__row">
          <button
            type="button"
            :class="{ active: scope === 'all' }"
            @click="changeScope('all')"
          >
            全部研报
          </button>
          <button
            type="button"
            :class="{ active: scope === 'followed' }"
            @click="changeScope('followed')"
          >
            仅关注作者
          </button>
        </div>
        <div class="stock-controls__row stock-controls__row--windows">
          <button
            v-for="option in windows"
            :key="option"
            type="button"
            :class="{ active: timeWindow === option }"
            @click="changeWindow(option)"
          >
            {{ formatWindow(option) }}
          </button>
        </div>
      </div>

      <ScoreComposition
        v-if="score.report_count"
        :categories="score.category_scores"
        :total="score.total_points"
        :report-count="score.report_count"
      />

      <section v-if="sortedBreakdown.length" class="section">
        <div class="section__head">
          <h2 class="section__title">信号拆解</h2>
          <span class="section__hint">按文章有效权重排序</span>
        </div>
        <div class="card breakdown">
          <button
            v-for="item in visibleBreakdown"
            :key="item.report_id"
            type="button"
            class="breakdown__row"
            @click="openReport(item.report_id)"
          >
            <div class="breakdown__top">
              <span class="chip" :class="`chip--${item.category}`">
                {{ categoryLabel(item.category) }}
              </span>
              <span class="breakdown__title">{{ item.title }}</span>
            </div>
            <div class="breakdown__bar">
              <span
                class="breakdown__fill"
                :class="`is-${item.category}`"
                :style="{ width: `${weightPercent(item)}%` }"
              />
            </div>
            <div class="breakdown__meta">
              <span>文章权重 {{ item.effective_weight.toFixed(2) }}</span>
              <span>作者权重 {{ item.author_weight.toFixed(1) }}</span>
              <span>板块配额 {{ Math.round(item.category_weight * 100) }}%</span>
              <span>时效 {{ Math.round(item.recency_factor * 100) }}%</span>
              <span>相关度 {{ Math.round(item.relevance * 100) }}%</span>
            </div>
          </button>

          <button
            v-if="sortedBreakdown.length > 6"
            type="button"
            class="breakdown__more"
            @click="showAllBreakdown = !showAllBreakdown"
          >
            {{ showAllBreakdown ? '收起' : `查看全部 ${sortedBreakdown.length} 条` }}
            <van-icon :name="showAllBreakdown ? 'arrow-up' : 'arrow-down'" size="10" />
          </button>
        </div>
        <p class="formula-note">
          文章权重 = 置信度 × √作者权重 × 相关度 × 0.5^(距今天数 ÷ 半衰期)；
          个股 / 行业 / 宏观半衰期分别为 7 / 14 / 30 天，仅纳入近 90 天文章。
          板块内先按文章权重求加权信号，再折算为板块配额得分。
        </p>
      </section>

      <section class="section">
        <div class="section__head">
          <h2 class="section__title">相关研报</h2>
          <span class="section__hint">{{ detail.related_reports.length }} 篇</span>
        </div>
        <div v-if="detail.related_reports.length" class="related-list">
          <ReportCard
            v-for="report in detail.related_reports"
            :key="report.id"
            :report="report"
          />
        </div>
        <div v-else class="empty-state">
          <van-icon name="notes-o" size="28" />
          <p class="empty-state__title">当前窗口没有相关研报</p>
          <p class="empty-state__text">试试扩大时间窗口，或切换为「全部研报」。</p>
        </div>
      </section>

      <footer class="stock-footer">
        <p>评分为统计聚合结果，不构成投资建议。</p>
        <p class="stock-footer__meta">
          {{ detail.security.industry_code ? `行业代码 ${detail.security.industry_code} · ` : '' }}
          更新于 {{ score.computed_at ? new Date(score.computed_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) : '—' }}
        </p>
      </footer>
    </template>
  </div>
</template>

<style scoped>
.stock-page {
  background: var(--rs-bg);
}

.stock-nav {
  position: sticky;
  top: 0;
  z-index: 30;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  background: rgba(255, 255, 255, 0.92);
  border-bottom: 1px solid var(--rs-line);
  backdrop-filter: blur(12px);
}

.stock-nav__back {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border: 1px solid var(--rs-line);
  border-radius: 10px;
  background: #fff;
  color: var(--rs-ink);
  cursor: pointer;
}

.stock-nav__title {
  flex: 1;
  font-size: 14px;
  font-weight: 700;
  letter-spacing: 0.04em;
}

.stock-nav__watch {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 5px 11px;
  border: 1px solid var(--rs-line);
  border-radius: 999px;
  background: #fff;
  font-size: 11px;
  font-weight: 600;
  color: var(--rs-ink-soft);
  cursor: pointer;
}

.stock-nav__watch.is-active {
  border-color: transparent;
  background: var(--rs-accent-soft);
  color: var(--rs-accent);
}

.stock-nav__watch.is-placeholder {
  width: 58px;
  visibility: hidden;
}

.stock-loading {
  padding: 100px 0;
  text-align: center;
}

.stock-loading__hint {
  margin-top: 12px;
  font-size: 10.5px;
  color: var(--rs-muted);
}

.stock-hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 24px 20px 20px;
  background:
    radial-gradient(500px 200px at 110% -40%, rgba(194, 65, 12, 0.12), transparent 65%),
    linear-gradient(160deg, #0e2439, #173a56);
  color: #fff;
}

.stock-hero__eyebrow {
  margin: 0;
  font-size: 9.5px;
  letter-spacing: 0.26em;
  color: rgba(255, 255, 255, 0.45);
}

.stock-hero__name {
  margin: 7px 0 0;
  font-size: 27px;
  font-weight: 700;
  letter-spacing: 0.03em;
}

.stock-hero__code {
  margin: 7px 0 0;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.56);
  letter-spacing: 0.06em;
}

.stock-hero__exchange {
  margin-left: 6px;
  padding: 1px 5px;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.12);
  font-size: 9px;
}

.stock-hero :deep(.score-ring__caption) {
  color: rgba(255, 255, 255, 0.5);
}

.stock-conclusion {
  margin: -8px 14px 0;
  padding: 16px;
}

.stock-conclusion__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.stock-conclusion__badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  border-radius: 6px;
  background: var(--rs-accent-soft);
  color: var(--rs-accent);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.06em;
}

.stock-conclusion__meta {
  font-size: 10px;
  color: var(--rs-muted);
}

.stock-conclusion__text {
  margin: 12px 0 0;
  font-size: 13.5px;
  line-height: 1.85;
  font-weight: 500;
  color: var(--rs-ink-soft);
}

.stock-conclusion__text.up,
.stock-conclusion__text.down {
  color: var(--rs-ink-soft);
}

.stock-conclusion__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 13px;
  padding-top: 13px;
  border-top: 1px dashed var(--rs-line);
}

.stock-controls {
  margin: 14px 14px 0;
  padding: 8px;
  border-radius: 13px;
  background: #fff;
  border: 1px solid rgba(232, 237, 243, 0.9);
  box-shadow: 0 4px 16px rgba(16, 35, 58, 0.05);
}

.stock-controls__row {
  display: flex;
  gap: 4px;
}

.stock-controls__row + .stock-controls__row {
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px dashed var(--rs-line);
}

.stock-controls__row button {
  flex: 1;
  padding: 7px 0;
  border: none;
  border-radius: 8px;
  background: transparent;
  font-size: 11.5px;
  font-weight: 600;
  color: var(--rs-muted);
  cursor: pointer;
}

.stock-controls__row button.active {
  background: var(--rs-navy);
  color: #fff;
}

.stock-controls__row--windows button.active {
  background: var(--rs-accent-soft);
  color: var(--rs-accent);
}

.breakdown {
  overflow: hidden;
}

.breakdown__row {
  display: block;
  width: 100%;
  padding: 13px 15px;
  border: none;
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.breakdown__row + .breakdown__row {
  border-top: 1px solid var(--rs-line);
}

.breakdown__row:active {
  background: #fafcff;
}

.breakdown__top {
  display: flex;
  align-items: center;
  gap: 7px;
}

.breakdown__title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--rs-ink-soft);
}

.breakdown__bar {
  height: 4px;
  margin-top: 9px;
  border-radius: 99px;
  background: #eef2f7;
  overflow: hidden;
}

.breakdown__fill {
  display: block;
  height: 100%;
  border-radius: 99px;
}

.breakdown__fill.is-stock {
  background: #2a78d6;
}

.breakdown__fill.is-industry {
  background: #eb6834;
}

.breakdown__fill.is-macro {
  background: #1baf7a;
}

.breakdown__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 10px;
  margin-top: 7px;
  font-size: 9.5px;
  color: var(--rs-muted);
}

.breakdown__more {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  width: 100%;
  padding: 11px 0;
  border: none;
  border-top: 1px solid var(--rs-line);
  background: #fbfcfe;
  font-size: 11px;
  font-weight: 600;
  color: var(--rs-muted);
  cursor: pointer;
}

.formula-note {
  margin: 9px 4px 0;
  font-size: 10px;
  line-height: 1.7;
  color: var(--rs-muted);
}

.related-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.stock-footer {
  padding: 26px 20px calc(30px + env(safe-area-inset-bottom));
  text-align: center;
  font-size: 10.5px;
  line-height: 1.8;
  color: var(--rs-muted);
}

.stock-footer p {
  margin: 0;
}

.stock-footer__meta {
  margin-top: 4px !important;
  opacity: 0.75;
}

.retry {
  margin-top: 16px;
}
</style>
