<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { showConfirmDialog, showToast } from 'vant'

import { api } from '@/api/client'
import type { ScoreScope, Security, WatchlistItem } from '@/api/types'
import EvidenceBadge from '@/components/EvidenceBadge.vue'
import ScoreDelta from '@/components/ScoreDelta.vue'
import ScoreRing from '@/components/ScoreRing.vue'
import { formatWindow, relationLabel } from '@/utils/format'
import { useWatchlistStore } from '@/stores/watchlist'

const router = useRouter()
const watchlist = useWatchlistStore()

const windows: Array<'7d' | '30d' | '90d'> = ['7d', '30d', '90d']
const scopes: Array<{ value: ScoreScope; label: string }> = [
  { value: 'personal', label: '仅关注' },
  { value: 'hybrid', label: '关注 + 精选' },
  { value: 'all', label: '全站' },
]

const relationOrder = ['stock', 'industry', 'macro']

const addPopup = ref(false)
const searchQ = ref('')
const searchResults = ref<Security[]>([])
const searching = ref(false)
const adding = ref<number | null>(null)
let searchTimer: number | undefined

const isEmpty = computed(() => !watchlist.loading && watchlist.items.length === 0)

function scoreTone(value: number | null | undefined): string {
  if (value === null || value === undefined) return 'neutral'
  if (value >= 55) return 'up'
  if (value <= 45) return 'down'
  return 'neutral'
}

function openStock(code: string): void {
  void router.push({ name: 'stock', params: { code } })
}

function countsLabel(item: WatchlistItem): Array<{ key: string; label: string; count: number }> {
  const counts = item.score?.relation_counts ?? {}
  return relationOrder
    .map((key) => ({ key, label: relationLabel(key), count: counts[key] ?? 0 }))
    .filter((entry) => entry.count > 0)
}

function gapHints(item: WatchlistItem): string[] {
  const score = item.score
  if (!score) return []
  if (score.report_count === 0) return ['暂无相关研报']
  const hints: string[] = []
  if (score.evidence.stock_count === 0) hints.push('缺少个股直接证据')
  if (score.evidence.industry_count === 0) hints.push('缺少行业证据')
  if (score.evidence.is_macro_only) hints.push('仅宏观参考')
  return hints
}

async function removeItem(item: WatchlistItem): Promise<void> {
  try {
    await showConfirmDialog({
      title: '移出自选',
      message: `确定把「${item.security.name}」移出自选吗？`,
      confirmButtonText: '移出',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    await watchlist.remove(item.security.id)
    showToast('已移出自选')
  } catch (error) {
    showToast(error instanceof Error ? error.message : '操作失败')
  }
}

function openAdd(): void {
  searchQ.value = ''
  searchResults.value = []
  addPopup.value = true
}

async function runSearch(): Promise<void> {
  const query = searchQ.value.trim()
  if (!query) {
    searchResults.value = []
    return
  }
  searching.value = true
  try {
    searchResults.value = await api.get<Security[]>('/securities/search', { q: query, limit: 20 })
  } catch (error) {
    showToast(error instanceof Error ? error.message : '搜索失败')
  } finally {
    searching.value = false
  }
}

async function addSecurity(security: Security): Promise<void> {
  adding.value = security.id
  try {
    await watchlist.add(security.id, null)
    addPopup.value = false
    showToast(`已添加 ${security.name}`)
  } catch (error) {
    showToast(error instanceof Error ? error.message : '添加失败')
  } finally {
    adding.value = null
  }
}

watch(searchQ, () => {
  window.clearTimeout(searchTimer)
  searchTimer = window.setTimeout(() => {
    void runSearch()
  }, 320)
})

onMounted(() => {
  void watchlist.load()
})

onBeforeUnmount(() => {
  window.clearTimeout(searchTimer)
})
</script>

<template>
  <div class="page watch-page">
    <header class="hero watch-hero">
      <div class="watch-hero__top">
        <span class="hero__eyebrow">PORTFOLIO SIGNALS</span>
        <button type="button" class="watch-hero__add" @click="openAdd">
          <van-icon name="plus" size="12" />
          添加自选
        </button>
      </div>
      <h1 class="hero__title">自选</h1>
      <p class="hero__subtitle">只看真正关联到这只股票的个股、行业与宏观证据</p>

      <div class="watch-scope">
        <button
          v-for="scope in scopes"
          :key="scope.value"
          type="button"
          :class="{ active: watchlist.scope === scope.value }"
          @click="watchlist.setScope(scope.value)"
        >
          {{ scope.label }}
        </button>
      </div>
    </header>

    <div class="watch-windows">
      <button
        v-for="option in windows"
        :key="option"
        type="button"
        :class="{ active: watchlist.window === option }"
        @click="watchlist.setWindow(option)"
      >
        {{ formatWindow(option) }}
      </button>
    </div>

    <div class="watch-list">
      <div v-if="watchlist.loading" class="loading-block">
        <van-loading size="20" vertical>正在聚合信号…</van-loading>
      </div>

      <div v-else-if="watchlist.error" class="empty-state">
        <van-icon name="warning-o" size="32" />
        <p class="empty-state__title">加载失败</p>
        <p class="empty-state__text">{{ watchlist.error }}</p>
        <van-button size="small" round class="empty-action" @click="watchlist.load()">
          重试
        </van-button>
      </div>

      <div v-else-if="isEmpty" class="empty-state">
        <van-icon name="star-o" size="34" />
        <p class="empty-state__title">自选股还是空的</p>
        <p class="empty-state__text">
          添加股票后，系统会把相关的个股、行业、宏观研报按权重聚合成综合评分与 AI 结论。
        </p>
        <van-button size="small" round type="primary" class="empty-action" @click="openAdd">
          添加第一只股票
        </van-button>
      </div>

      <template v-else>
        <van-swipe-cell v-for="item in watchlist.items" :key="item.id" class="watch-swipe">
          <article class="card stock-card" @click="openStock(item.security.code)">
            <div class="stock-card__head">
              <div class="stock-card__identity">
                <h3>{{ item.security.name }}</h3>
                <p class="stock-card__code mono">
                  {{ item.security.code }}
                  <span class="stock-card__exchange">{{ item.security.exchange }}</span>
                </p>
                <p class="stock-card__delta">
                  <ScoreDelta
                    :value="item.score?.score_delta"
                    :since="item.score?.delta_since"
                  />
                </p>
              </div>
              <ScoreRing
                :value="item.score?.display_score"
                :size="62"
                :stroke="5"
                :caption="item.score?.display_label ?? '综合得分'"
              />
            </div>

            <p class="stock-card__conclusion" :class="scoreTone(item.score?.display_score)">
              <span class="stock-card__conclusion-text">
                {{ item.score?.conclusion || '暂无足够研报形成结论' }}
              </span>
            </p>

            <div class="stock-card__signals">
              <EvidenceBadge
                v-if="item.score"
                :evidence="item.score.evidence"
                class="stock-card__evidence"
              />
              <div class="tag-row stock-card__counts">
                <span
                  v-for="entry in countsLabel(item)"
                  :key="entry.key"
                  class="chip"
                  :class="`chip--${entry.key}`"
                >
                  {{ entry.label }} {{ entry.count }}
                </span>
                <span v-if="!countsLabel(item).length" class="chip chip--outline">暂无信号</span>
              </div>
            </div>

            <div class="stock-card__footer">
              <span v-if="gapHints(item).length" class="stock-card__gaps">
                {{ gapHints(item).join(' · ') }}
              </span>
              <span v-else class="stock-card__gaps">证据覆盖完整</span>
              <span class="stock-card__count">
                {{ item.score?.report_count ?? 0 }} 篇
              </span>
            </div>
          </article>

          <template #right>
            <button type="button" class="swipe-delete" @click.stop="removeItem(item)">
              移出
            </button>
          </template>
        </van-swipe-cell>

        <p class="watch-note">
          综合分由报告置信度、作者权重、品类权重和时间衰减共同决定；结论由 AI 生成。
        </p>
      </template>
    </div>

    <van-popup v-model:show="addPopup" position="bottom" round closeable>
      <div class="search-sheet">
        <h3 class="search-sheet__title">添加自选</h3>
        <p class="search-sheet__subtitle">搜索 A 股代码或名称，例如「贵州茅台」或「600519」。</p>

        <div class="search-sheet__input">
          <van-icon name="search" size="15" />
          <input
            v-model="searchQ"
            type="search"
            placeholder="股票代码 / 名称"
            autofocus
          />
          <van-loading v-if="searching" size="14" />
        </div>

        <div class="search-results">
          <div v-if="!searchQ.trim()" class="search-hint">
            <van-icon name="bulb-o" size="18" />
            <span>输入关键词开始搜索</span>
          </div>
          <div v-else-if="!searching && !searchResults.length" class="search-hint">
            <van-icon name="search" size="18" />
            <span>没有找到匹配的股票</span>
          </div>
          <button
            v-for="security in searchResults"
            :key="security.id"
            type="button"
            class="search-result"
            :disabled="adding === security.id"
            @click="addSecurity(security)"
          >
            <span class="search-result__name">{{ security.name }}</span>
            <span class="search-result__code mono">
              {{ security.code }} · {{ security.exchange }}
            </span>
            <span class="search-result__action">
              <van-loading v-if="adding === security.id" size="14" />
              <van-icon v-else name="plus" size="14" />
            </span>
          </button>
        </div>
      </div>
    </van-popup>
  </div>
</template>

<style scoped>
.watch-page {
  background:
    linear-gradient(180deg, #0e2439 0, #0e2439 214px, transparent 214px),
    var(--rs-bg);
}

.watch-hero {
  padding-bottom: 20px;
}

.watch-hero__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.watch-hero__add {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 5px 11px;
  border: 1px solid rgba(255, 255, 255, 0.18);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.08);
  color: rgba(255, 255, 255, 0.82);
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
}

.watch-scope {
  display: flex;
  gap: 4px;
  width: fit-content;
  margin-top: 16px;
  padding: 4px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.watch-scope button {
  padding: 7px 15px;
  border: none;
  border-radius: 9px;
  background: transparent;
  font-size: 12px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.6);
  cursor: pointer;
}

.watch-scope button.active {
  background: #fff;
  color: var(--rs-navy);
}

.watch-windows {
  display: flex;
  gap: 6px;
  margin: -8px 12px 0;
  padding: 8px 10px;
  border-radius: 13px;
  background: #fff;
  border: 1px solid rgba(232, 237, 243, 0.9);
  box-shadow: var(--rs-shadow);
}

.watch-windows button {
  flex: 1;
  padding: 6px 0;
  border: none;
  border-radius: 8px;
  background: transparent;
  font-size: 11.5px;
  font-weight: 600;
  color: var(--rs-muted);
  cursor: pointer;
}

.watch-windows button.active {
  background: var(--rs-navy);
  color: #fff;
}

.watch-list {
  padding: 12px;
}

.watch-swipe {
  display: block;
  margin-bottom: 10px;
  border-radius: var(--rs-radius);
  overflow: hidden;
}

.stock-card {
  padding: 15px 16px 13px;
  cursor: pointer;
}

.stock-card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.stock-card__identity h3 {
  margin: 0;
  font-size: 17px;
  font-weight: 700;
  letter-spacing: 0.01em;
}

.stock-card__code {
  margin: 5px 0 0;
  font-size: 11px;
  color: var(--rs-muted);
  letter-spacing: 0.04em;
}

.stock-card__exchange {
  margin-left: 5px;
  padding: 1px 5px;
  border-radius: 4px;
  background: var(--rs-neutral-soft);
  font-size: 9px;
}

.stock-card__delta {
  margin: 6px 0 0;
}

.stock-card__signals {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 11px;
}

.stock-card__evidence {
  flex: none;
}

.stock-card__counts {
  flex: 1;
  min-width: 0;
  flex-wrap: nowrap;
  overflow: hidden;
}

.stock-card__conclusion {
  margin: 12px 0 0;
  padding: 10px 12px;
  border-radius: 10px;
  background: #f8fafc;
  color: var(--rs-ink-soft);
  font-size: 12px;
  line-height: 1.7;
}

.stock-card__conclusion-text {
  display: -webkit-box;
  overflow: hidden;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.stock-card__conclusion.up {
  background: var(--rs-up-soft);
  color: var(--rs-ink-soft);
}

.stock-card__conclusion.down {
  background: var(--rs-down-soft);
  color: var(--rs-ink-soft);
}

.stock-card__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: 9px;
}

.stock-card__gaps {
  font-size: 9.5px;
  color: var(--rs-muted);
}

.stock-card__count {
  flex: none;
  font-size: 10.5px;
  color: var(--rs-muted);
}

.swipe-delete {
  width: 72px;
  height: 100%;
  border: none;
  background: var(--rs-up);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.watch-note {
  margin: 6px 6px 10px;
  font-size: 10.5px;
  line-height: 1.7;
  color: var(--rs-muted);
  text-align: center;
}

.empty-action {
  margin-top: 16px;
  padding: 0 24px;
}

.search-sheet {
  padding: 22px 18px calc(24px + env(safe-area-inset-bottom));
  min-height: 52vh;
}

.search-sheet__title {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
}

.search-sheet__subtitle {
  margin: 6px 0 16px;
  font-size: 11.5px;
  line-height: 1.7;
  color: var(--rs-muted);
}

.search-sheet__input {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 11px 13px;
  border-radius: 12px;
  background: var(--rs-neutral-soft);
  color: var(--rs-muted);
}

.search-sheet__input input {
  flex: 1;
  min-width: 0;
  border: none;
  background: transparent;
  font-size: 14px;
  color: var(--rs-ink);
  outline: none;
}

.search-results {
  margin-top: 8px;
  max-height: 48vh;
  overflow-y: auto;
}

.search-hint {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 40px 0;
  font-size: 12px;
  color: var(--rs-muted);
}

.search-result {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 13px 6px;
  border: none;
  border-bottom: 1px solid var(--rs-line);
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.search-result:active {
  background: #fafcff;
}

.search-result__name {
  font-size: 14px;
  font-weight: 600;
  color: var(--rs-ink);
}

.search-result__code {
  font-size: 11px;
  color: var(--rs-muted);
}

.search-result__action {
  margin-left: auto;
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: var(--rs-accent-soft);
  color: var(--rs-accent);
}
</style>
