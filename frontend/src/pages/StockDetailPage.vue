<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { showToast } from 'vant'

import { api } from '@/api/client'
import type {
  ScoreBreakdownItem,
  ScoreScope,
  StockDetail,
  StockHistory,
  StockWindow,
} from '@/api/types'
import EvidenceBadge from '@/components/EvidenceBadge.vue'
import ReportCard from '@/components/ReportCard.vue'
import ScoreComposition from '@/components/ScoreComposition.vue'
import ScoreDelta from '@/components/ScoreDelta.vue'
import ScoreRing from '@/components/ScoreRing.vue'
import ScoreSparkline from '@/components/ScoreSparkline.vue'
import { useAuthStore } from '@/stores/auth'
import { useWatchlistStore } from '@/stores/watchlist'
import { formatWindow, relationLabel, relationReasonLabel } from '@/utils/format'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const watchlist = useWatchlistStore()

const detail = ref<StockDetail | null>(null)
const history = ref<StockHistory | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)
const scope = ref<ScoreScope>(
  auth.user?.scoring_config?.default_scope ?? 'hybrid',
)
const timeWindow = ref<StockWindow>('30d')
const showAllBreakdown = ref(false)
const watchSaving = ref(false)
const feedbackSaving = ref<number | null>(null)

const windows: StockWindow[] = ['7d', '30d', '90d']
const scopes: Array<{ value: ScoreScope; label: string }> = [
  { value: 'personal', label: '仅关注' },
  { value: 'hybrid', label: '关注 + 精选' },
  { value: 'all', label: '全站' },
]

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

const evidenceWarning = computed(() => {
  const evidence = score.value?.evidence
  if (!evidence) return ''
  if (evidence.is_macro_only) {
    return '当前只有宏观证据，分数仅作宏观参考，不构成个股综合结论。'
  }
  if (evidence.is_insufficient) {
    return '暂无个股或行业证据，暂不展示综合分。'
  }
  if (evidence.stock_count === 0) {
    return '当前缺少个股直接证据，以下为行业参考。'
  }
  return ''
})

const coverage = computed(() => {
  const data = score.value?.evidence.coverage
  if (!data) return []
  return [
    { key: 'stock', label: '个股', covered: Boolean(data.stock) },
    { key: 'industry', label: '行业', covered: Boolean(data.industry) },
    { key: 'macro', label: '宏观', covered: Boolean(data.macro) },
  ]
})

const historyDeltas = computed(() => {
  const deltas = history.value?.deltas ?? {}
  return [
    { key: '1d', label: '1日', value: deltas['1d'] ?? null },
    { key: '7d', label: '7日', value: deltas['7d'] ?? null },
    { key: '30d', label: '30日', value: deltas['30d'] ?? null },
  ]
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

async function loadHistory(): Promise<void> {
  history.value = null
  try {
    history.value = await api.get<StockHistory>(
      `/stocks/${route.params.code}/history`,
      { scope: scope.value, window: timeWindow.value, days: 90 },
    )
  } catch {
    // History is advisory; keep the deterministic score visible if it fails.
  }
}

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const [stockDetail] = await Promise.all([
      api.get<StockDetail>(`/stocks/${route.params.code}`, {
        scope: scope.value,
        window: timeWindow.value,
        limit: 20,
      }),
      loadHistory(),
    ])
    detail.value = stockDetail
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败'
  } finally {
    loading.value = false
  }
}

async function changeScope(next: ScoreScope): Promise<void> {
  if (scope.value === next) return
  scope.value = next
  await load()
}

async function changeWindow(next: StockWindow): Promise<void> {
  if (timeWindow.value === next) return
  timeWindow.value = next
  await load()
}

async function markIrrelevant(item: ScoreBreakdownItem): Promise<void> {
  if (!security.value || feedbackSaving.value !== null) return
  feedbackSaving.value = item.report_id
  try {
    await api.post(`/stocks/${security.value.code}/feedback`, {
      report_id: item.report_id,
      action: 'irrelevant',
    })
    showToast('已从这只股票的评分中排除')
    await load()
  } catch (err) {
    showToast(err instanceof Error ? err.message : '操作失败')
  } finally {
    feedbackSaving.value = null
  }
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
      <span class="stock-nav__title">个股研究</span>
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
      <van-loading size="24" vertical>正在聚合相关研报…</van-loading>
      <p class="stock-loading__hint">评分由相关证据、作者权重与时间衰减共同决定</p>
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
          <p class="stock-hero__eyebrow">EVIDENCE-WEIGHTED SIGNAL</p>
          <h1 class="stock-hero__name">{{ detail.security.name }}</h1>
          <p class="stock-hero__code mono">
            {{ detail.security.code }}
            <span class="stock-hero__exchange">{{ detail.security.exchange }}</span>
          </p>
          <p class="stock-hero__delta">
            <ScoreDelta
              :value="score.score_delta"
              :since="score.delta_since"
              prefix="较上次"
            />
          </p>
        </div>
        <ScoreRing
          :value="displayScore"
          :size="96"
          :stroke="8"
          :caption="score.display_label"
        />
      </section>

      <section class="stock-conclusion card">
        <div class="stock-conclusion__head">
          <span class="stock-conclusion__badge">
            <van-icon name="magic" size="11" />
            {{ score.evidence.is_macro_only ? '宏观参考' : '综合结论' }}
          </span>
          <span class="stock-conclusion__meta">
            {{ score.report_count }} 篇相关研报 · 有效样本 {{ score.n_eff.toFixed(1) }}
          </span>
        </div>
        <p class="stock-conclusion__text" :class="scoreTone">
          {{ score.conclusion || '暂无足够研报形成结论。' }}
        </p>

        <p v-if="evidenceWarning" class="stock-conclusion__warning">
          <van-icon name="info-o" size="12" />
          {{ evidenceWarning }}
        </p>

        <div class="stock-conclusion__chips">
          <EvidenceBadge :evidence="score.evidence" counts />
          <span class="chip chip--outline">
            聚合置信度 {{ Math.round(score.confidence * 100) }}%
          </span>
        </div>

        <div class="evidence-coverage">
          <span
            v-for="item in coverage"
            :key="item.key"
            class="evidence-coverage__item"
            :class="item.covered ? 'is-covered' : 'is-missing'"
          >
            <van-icon :name="item.covered ? 'checked' : 'minus'" size="10" />
            {{ item.label }}{{ item.covered ? '已覆盖' : '缺失' }}
          </span>
          <span class="evidence-coverage__authors">
            {{ score.evidence.distinct_authors }} 位作者
          </span>
        </div>
      </section>

      <div class="stock-controls">
        <div class="stock-controls__row">
          <button
            v-for="option in scopes"
            :key="option.value"
            type="button"
            :class="{ active: scope === option.value }"
            @click="changeScope(option.value)"
          >
            {{ option.label }}
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
        :relations="score.relation_scores"
        :total="score.total_points"
        :report-count="score.report_count"
        :display-label="score.display_label"
      />

      <section v-if="history" class="section">
        <div class="section__head">
          <h2 class="section__title">评分变化</h2>
          <span class="section__hint">每日快照</span>
        </div>
        <div class="card history-card">
          <div class="history-card__deltas">
            <div
              v-for="item in historyDeltas"
              :key="item.key"
              class="history-card__delta"
            >
              <span class="history-card__delta-label">{{ item.label }}</span>
              <ScoreDelta :value="item.value" />
            </div>
          </div>
          <ScoreSparkline :points="history.points" />
        </div>
      </section>

      <section v-if="sortedBreakdown.length" class="section">
        <div class="section__head">
          <h2 class="section__title">证据拆解</h2>
          <span class="section__hint">按文章有效权重排序</span>
        </div>
        <div class="card breakdown">
          <div
            v-for="item in visibleBreakdown"
            :key="item.report_id"
            class="breakdown__row"
          >
            <button
              type="button"
              class="breakdown__main"
              @click="openReport(item.report_id)"
            >
              <div class="breakdown__top">
                <span class="chip" :class="`chip--${item.relation}`">
                  {{ relationLabel(item.relation) }}
                </span>
                <span class="breakdown__title">{{ item.title }}</span>
              </div>
              <p class="breakdown__reason">
                {{ relationReasonLabel(item.relation_reason) }}
                <span v-if="item.author_name" class="breakdown__author">
                  · {{ item.author_name }}
                </span>
              </p>
              <div class="breakdown__bar">
                <span
                  class="breakdown__fill"
                  :class="`is-${item.relation}`"
                  :style="{ width: `${weightPercent(item)}%` }"
                />
              </div>
              <div class="breakdown__meta">
                <span>文章权重 {{ item.effective_weight.toFixed(2) }}</span>
                <span>作者权重 {{ item.author_weight.toFixed(1) }}</span>
                <span>关系配额 {{ Math.round(item.relation_weight * 100) }}%</span>
                <span>时效 {{ Math.round(item.recency_factor * 100) }}%</span>
                <span>相关度 {{ Math.round(item.relevance * 100) }}%</span>
              </div>
            </button>
            <button
              type="button"
              class="breakdown__feedback"
              :disabled="feedbackSaving !== null"
              @click="markIrrelevant(item)"
            >
              {{ feedbackSaving === item.report_id ? '处理中…' : '这篇与我无关' }}
            </button>
          </div>

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
          文章权重 = 置信度 × √作者权重 × 关系相关度 × 0.5^(距今天数 ÷ 半衰期)；
          个股 / 行业 / 宏观半衰期分别为 {{ score.half_life_days.stock ?? 7 }} /
          {{ score.half_life_days.industry ?? 14 }} /
          {{ score.half_life_days.macro ?? 30 }} 天，仅纳入近
          {{ Math.round(score.max_age_days) }} 天文章。同一篇文章对同一只股票只计一次。
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
          <p class="empty-state__title">当前范围没有相关研报</p>
          <p class="empty-state__text">
            试试切换「全站」或扩大时间窗口；也可以在作者页关注更多相关博主。
          </p>
        </div>
      </section>

      <footer class="stock-footer">
        <p>评分仅作研究参考，不构成投资建议。</p>
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

.stock-hero__delta {
  margin: 9px 0 0;
}

.stock-hero__delta :deep(.score-delta__since),
.stock-hero__delta :deep(.score-delta__prefix) {
  color: rgba(255, 255, 255, 0.48);
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

.stock-conclusion__warning {
  display: flex;
  align-items: flex-start;
  gap: 5px;
  margin: 11px 0 0;
  padding: 8px 10px;
  border-radius: 8px;
  background: #fff7e6;
  color: #8a5a00;
  font-size: 10.5px;
  line-height: 1.6;
}

.stock-conclusion__chips {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 13px;
  padding-top: 13px;
  border-top: 1px dashed var(--rs-line);
}

.evidence-coverage {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 10px;
  font-size: 9.5px;
  color: var(--rs-muted);
}

.evidence-coverage__item {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 2px 7px;
  border-radius: 999px;
  background: var(--rs-neutral-soft);
}

.evidence-coverage__item.is-covered {
  background: var(--rs-down-soft);
  color: var(--rs-down);
}

.evidence-coverage__item.is-missing {
  color: var(--rs-muted);
  opacity: 0.75;
}

.evidence-coverage__authors {
  margin-left: auto;
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

.history-card {
  padding: 14px 16px;
}

.history-card__deltas {
  display: flex;
  gap: 6px;
  margin-bottom: 13px;
}

.history-card__delta {
  flex: 1;
  padding: 8px 10px;
  border-radius: 9px;
  background: #f8fafc;
}

.history-card__delta-label {
  display: block;
  margin-bottom: 3px;
  font-size: 9.5px;
  color: var(--rs-muted);
}

.breakdown {
  overflow: hidden;
}

.breakdown__row {
  display: flex;
  align-items: stretch;
  gap: 4px;
  padding-right: 10px;
}

.breakdown__row + .breakdown__row {
  border-top: 1px solid var(--rs-line);
}

.breakdown__main {
  flex: 1;
  min-width: 0;
  display: block;
  padding: 13px 8px 13px 15px;
  border: none;
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.breakdown__main:active {
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

.breakdown__reason {
  margin: 5px 0 0;
  font-size: 9.5px;
  color: var(--rs-muted);
}

.breakdown__author {
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

.breakdown__feedback {
  align-self: center;
  flex: none;
  padding: 5px 8px;
  border: 1px solid var(--rs-line);
  border-radius: 999px;
  background: #fff;
  font-size: 9.5px;
  color: var(--rs-muted);
  cursor: pointer;
}

.breakdown__feedback:disabled {
  opacity: 0.5;
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
