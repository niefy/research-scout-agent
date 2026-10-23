<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { showToast } from 'vant'

import { api } from '@/api/client'
import type { ScoreScope } from '@/api/types'
import EvidenceBadge from '@/components/EvidenceBadge.vue'
import ReportCard from '@/components/ReportCard.vue'
import ScoreDelta from '@/components/ScoreDelta.vue'
import ScoreRing from '@/components/ScoreRing.vue'
import { useAuthStore } from '@/stores/auth'
import { useDigestStore } from '@/stores/digest'
import { gapLabel, scopeLabel } from '@/utils/format'

const router = useRouter()
const auth = useAuthStore()
const digestStore = useDigestStore()

const scope = ref<ScoreScope>(
  auth.user?.scoring_config?.default_scope ?? 'hybrid',
)
const followingId = ref<number | null>(null)

const scopes: ScoreScope[] = ['personal', 'hybrid', 'all']
const digest = computed(() => digestStore.digest)

const dateLabel = computed(() => {
  const value = digest.value?.date
  if (!value) return '今日'
  const date = new Date(`${value}T00:00:00`)
  if (Number.isNaN(date.getTime())) return value
  const week = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][date.getDay()]
  return `${date.getMonth() + 1}月${date.getDate()}日 · ${week}`
})

const summary = computed(() => {
  if (!digest.value) return null
  return {
    updates: digest.value.followed_updates.length,
    changes: digest.value.watchlist_changes.length,
    gaps: digest.value.evidence_gaps.length,
    authors: digest.value.recommended_authors.length,
  }
})

async function load(): Promise<void> {
  await digestStore.load({ scope: scope.value })
}

async function changeScope(next: ScoreScope): Promise<void> {
  if (scope.value === next) return
  scope.value = next
  await load()
}

async function followAuthor(id: number): Promise<void> {
  if (followingId.value !== null) return
  followingId.value = id
  try {
    await api.post(`/authors/${id}/follow`, { weight: 1, notify: false })
    showToast('已关注，正在回填近期内容')
    await load()
  } catch (err) {
    showToast(err instanceof Error ? err.message : '关注失败')
  } finally {
    followingId.value = null
  }
}

function openStock(code: string): void {
  void router.push({ name: 'stock', params: { code } })
}

function goBack(): void {
  if (window.history.length > 1) router.back()
  else void router.push('/feed')
}

onMounted(load)
</script>

<template>
  <div class="page page--plain digest-page">
    <header class="digest-nav">
      <button type="button" class="digest-nav__back" aria-label="返回" @click="goBack">
        <van-icon name="arrow-left" size="18" />
      </button>
      <span class="digest-nav__title">每日简报</span>
      <span class="digest-nav__date">{{ dateLabel }}</span>
    </header>

    <section class="digest-hero">
      <p class="digest-hero__eyebrow">YOUR RESEARCH BRIEF</p>
      <h1 class="digest-hero__title">{{ auth.user?.nickname ?? '研究用户' }}，早上好</h1>
      <p class="digest-hero__subtitle">
        关注作者的新观点、自选股的证据变化，以及今天值得补齐的信息缺口。
      </p>

      <div class="digest-scope">
        <button
          v-for="option in scopes"
          :key="option"
          type="button"
          :class="{ active: scope === option }"
          @click="changeScope(option)"
        >
          {{ scopeLabel(option) }}
        </button>
      </div>
    </section>

    <div v-if="summary" class="digest-summary">
      <div class="card digest-summary__item">
        <span class="digest-summary__value mono">{{ summary.updates }}</span>
        <span class="digest-summary__label">关注更新</span>
      </div>
      <div class="card digest-summary__item">
        <span class="digest-summary__value mono">{{ summary.changes }}</span>
        <span class="digest-summary__label">自选变化</span>
      </div>
      <div class="card digest-summary__item">
        <span class="digest-summary__value mono">{{ summary.gaps }}</span>
        <span class="digest-summary__label">证据缺口</span>
      </div>
      <div class="card digest-summary__item">
        <span class="digest-summary__value mono">{{ summary.authors }}</span>
        <span class="digest-summary__label">推荐作者</span>
      </div>
    </div>

    <div v-if="digestStore.loading" class="loading-block">
      <van-loading size="22" vertical>正在整理简报…</van-loading>
    </div>

    <div v-else-if="digestStore.error" class="empty-state">
      <van-icon name="warning-o" size="30" />
      <p class="empty-state__title">简报加载失败</p>
      <p class="empty-state__text">{{ digestStore.error }}</p>
      <van-button size="small" round class="digest-retry" @click="load">重试</van-button>
    </div>

    <template v-else-if="digest">
      <section class="section">
        <div class="section__head">
          <h2 class="section__title">关注作者更新</h2>
          <span class="section__hint">{{ digest.followed_updates.length }} 篇</span>
        </div>
        <div v-if="digest.followed_updates.length" class="digest-list">
          <ReportCard
            v-for="report in digest.followed_updates"
            :key="report.id"
            :report="report"
          />
        </div>
        <div v-else class="card digest-empty">
          <van-icon name="friends-o" size="22" />
          <div>
            <p class="digest-empty__title">今天关注作者还没有新内容</p>
            <p class="digest-empty__text">
              去作者页关注更多你信任的博主，新的观点会自动进入这里。
            </p>
          </div>
        </div>
      </section>

      <section class="section">
        <div class="section__head">
          <h2 class="section__title">自选股评分变化</h2>
          <span class="section__hint">{{ digest.watchlist_changes.length }} 只</span>
        </div>
        <div v-if="digest.watchlist_changes.length" class="card change-list">
          <button
            v-for="change in digest.watchlist_changes"
            :key="change.security.id"
            type="button"
            class="change-row"
            @click="openStock(change.security.code)"
          >
            <div class="change-row__identity">
              <h3>{{ change.security.name }}</h3>
              <p class="mono">{{ change.security.code }}</p>
              <EvidenceBadge :evidence="change.evidence" />
            </div>
            <div class="change-row__score">
              <ScoreRing
                :value="change.display_score"
                :size="52"
                :stroke="4.5"
                :caption="change.display_label"
              />
              <ScoreDelta
                :value="change.score_delta"
                :since="change.delta_since"
              />
            </div>
          </button>
        </div>
        <div v-else class="card digest-empty">
          <van-icon name="star-o" size="22" />
          <div>
            <p class="digest-empty__title">还没有自选股</p>
            <p class="digest-empty__text">添加股票后，每天会在这里显示评分与证据变化。</p>
          </div>
        </div>
      </section>

      <section class="section">
        <div class="section__head">
          <h2 class="section__title">证据缺口</h2>
          <span class="section__hint">{{ digest.evidence_gaps.length }} 项</span>
        </div>
        <div v-if="digest.evidence_gaps.length" class="card gap-list">
          <div
            v-for="gap in digest.evidence_gaps"
            :key="gap.security.id"
            class="gap-row"
            @click="openStock(gap.security.code)"
          >
            <div class="gap-row__identity">
              <span class="gap-row__name">{{ gap.security.name }}</span>
              <span class="gap-row__code mono">{{ gap.security.code }}</span>
            </div>
            <div class="tag-row">
              <span
                v-for="item in gap.gaps"
                :key="item"
                class="chip chip--outline"
              >
                {{ gapLabel(item) }}
              </span>
            </div>
          </div>
        </div>
        <div v-else class="card digest-empty">
          <van-icon name="passed" size="22" />
          <div>
            <p class="digest-empty__title">证据覆盖完整</p>
            <p class="digest-empty__text">自选股都有个股或行业层面的直接证据。</p>
          </div>
        </div>
      </section>

      <section class="section">
        <div class="section__head">
          <h2 class="section__title">推荐作者</h2>
          <span class="section__hint">系统精选</span>
        </div>
        <div v-if="digest.recommended_authors.length" class="card author-list">
          <div
            v-for="author in digest.recommended_authors"
            :key="author.id"
            class="author-row"
          >
            <div class="author-row__body">
              <div class="author-row__name">
                <h3>{{ author.canonical_name }}</h3>
                <span class="chip chip--outline">精选</span>
              </div>
              <p class="author-row__meta">
                质量 {{ Math.round(author.quality_score * 100) }}%
                <span v-if="author.sector_tags.length">
                  · {{ author.sector_tags.join(' / ') }}
                </span>
              </p>
            </div>
            <button
              type="button"
              class="author-row__follow"
              :disabled="followingId !== null"
              @click="followAuthor(author.id)"
            >
              {{ followingId === author.id ? '关注中…' : '+ 关注' }}
            </button>
          </div>
        </div>
        <div v-else class="card digest-empty">
          <van-icon name="award-o" size="22" />
          <div>
            <p class="digest-empty__title">暂时没有新的推荐</p>
            <p class="digest-empty__text">你已经关注了当前所有系统精选作者。</p>
          </div>
        </div>
      </section>

      <section class="digest-mail">
        <p>
          <van-icon name="envelop-o" size="12" />
          想每天收到邮件简报？在「我的」中开启每日邮件。
        </p>
        <button type="button" @click="router.push('/settings')">前往设置</button>
      </section>
    </template>
  </div>
</template>

<style scoped>
.digest-page {
  background:
    linear-gradient(180deg, #0e2439 0, #0e2439 226px, transparent 226px),
    var(--rs-bg);
}

.digest-nav {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  color: #fff;
}

.digest-nav__back {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border: 1px solid rgba(255, 255, 255, 0.18);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.07);
  color: #fff;
  cursor: pointer;
}

.digest-nav__title {
  flex: 1;
  font-size: 14px;
  font-weight: 700;
  letter-spacing: 0.04em;
}

.digest-nav__date {
  font-size: 10.5px;
  color: rgba(255, 255, 255, 0.55);
}

.digest-hero {
  padding: 10px 18px 20px;
  color: #fff;
}

.digest-hero__eyebrow {
  margin: 0;
  font-size: 9.5px;
  letter-spacing: 0.24em;
  color: rgba(255, 255, 255, 0.45);
}

.digest-hero__title {
  margin: 8px 0 0;
  font-size: 24px;
  font-weight: 700;
  letter-spacing: 0.02em;
}

.digest-hero__subtitle {
  margin: 7px 0 0;
  font-size: 11.5px;
  line-height: 1.65;
  color: rgba(255, 255, 255, 0.62);
}

.digest-scope {
  display: flex;
  gap: 3px;
  width: fit-content;
  margin-top: 16px;
  padding: 4px;
  border-radius: 11px;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.digest-scope button {
  padding: 6px 11px;
  border: none;
  border-radius: 8px;
  background: transparent;
  font-size: 10.5px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.6);
  cursor: pointer;
}

.digest-scope button.active {
  background: #fff;
  color: var(--rs-navy);
}

.digest-summary {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 7px;
  margin: -9px 12px 0;
}

.digest-summary__item {
  padding: 10px 6px;
  text-align: center;
}

.digest-summary__value {
  display: block;
  font-size: 18px;
  font-weight: 700;
  color: var(--rs-ink);
  line-height: 1.1;
}

.digest-summary__label {
  display: block;
  margin-top: 4px;
  font-size: 9px;
  color: var(--rs-muted);
}

.digest-retry {
  margin-top: 16px;
}

.digest-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.digest-empty {
  display: flex;
  align-items: flex-start;
  gap: 11px;
  padding: 15px 16px;
  color: var(--rs-muted);
}

.digest-empty__title {
  margin: 0;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--rs-ink-soft);
}

.digest-empty__text {
  margin: 4px 0 0;
  font-size: 10.5px;
  line-height: 1.6;
}

.change-list,
.gap-list,
.author-list {
  overflow: hidden;
}

.change-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  padding: 13px 15px;
  border: none;
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.change-row + .change-row,
.gap-row + .gap-row,
.author-row + .author-row {
  border-top: 1px solid var(--rs-line);
}

.change-row:active,
.gap-row:active {
  background: #fafcff;
}

.change-row__identity {
  min-width: 0;
}

.change-row__identity h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
}

.change-row__identity p {
  margin: 3px 0 6px;
  font-size: 10px;
  color: var(--rs-muted);
}

.change-row__score {
  display: flex;
  align-items: center;
  gap: 9px;
  flex: none;
}

.gap-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 12px 15px;
  cursor: pointer;
}

.gap-row__identity {
  display: flex;
  align-items: baseline;
  gap: 6px;
  min-width: 0;
}

.gap-row__name {
  font-size: 13px;
  font-weight: 600;
  color: var(--rs-ink-soft);
}

.gap-row__code {
  font-size: 9.5px;
  color: var(--rs-muted);
}

.gap-row .tag-row {
  flex: none;
  justify-content: flex-end;
}

.author-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 15px;
}

.author-row__body {
  flex: 1;
  min-width: 0;
}

.author-row__name {
  display: flex;
  align-items: center;
  gap: 6px;
}

.author-row__name h3 {
  margin: 0;
  font-size: 13.5px;
  font-weight: 700;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.author-row__meta {
  margin: 4px 0 0;
  font-size: 10px;
  color: var(--rs-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.author-row__follow {
  flex: none;
  padding: 5px 12px;
  border: 1px solid var(--rs-accent);
  border-radius: 999px;
  background: var(--rs-accent);
  color: #fff;
  font-size: 10.5px;
  font-weight: 600;
  cursor: pointer;
}

.author-row__follow:disabled {
  opacity: 0.6;
}

.digest-mail {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 22px 18px calc(30px + env(safe-area-inset-bottom));
  font-size: 10.5px;
  color: var(--rs-muted);
}

.digest-mail p {
  display: flex;
  align-items: center;
  gap: 5px;
  margin: 0;
}

.digest-mail button {
  flex: none;
  padding: 0;
  border: none;
  background: transparent;
  font-size: 10.5px;
  font-weight: 600;
  color: var(--rs-accent);
  cursor: pointer;
}
</style>
