<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import ReportCard from '@/components/ReportCard.vue'
import type { FeedSort, FeedWindow } from '@/api/types'
import { useFeedStore } from '@/stores/feed'

const router = useRouter()
const feed = useFeedStore()

const refreshing = ref(false)
const sentinel = ref<HTMLElement | null>(null)

const sortOptions = computed<Array<{ value: FeedSort; label: string }>>(() =>
  feed.scope === 'following'
    ? [
        { value: 'smart', label: '智能排序' },
        { value: 'latest', label: '最新' },
      ]
    : [
        { value: 'hot', label: '热门' },
        { value: 'latest', label: '最新' },
      ],
)

const windowOptions = computed<FeedWindow[]>(() =>
  feed.scope === 'following' ? ['7d', '30d', 'all'] : ['24h', '72h', '7d', '30d'],
)

const windowLabels: Record<FeedWindow, string> = {
  '24h': '24小时',
  '72h': '72小时',
  '7d': '近7天',
  '30d': '近30天',
  all: '全部',
}

const todayLabel = computed(() => {
  const now = new Date()
  const week = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][now.getDay()]
  return `${now.getMonth() + 1}月${now.getDate()}日 · ${week}`
})

const emptyTitle = computed(() =>
  feed.scope === 'following' ? '关注列表还是空的' : '暂时没有发现新内容',
)

const emptyText = computed(() =>
  feed.scope === 'following'
    ? '去作者页关注几位你信任的博主，他们的研报会出现在这里。'
    : '换个时间窗口看看，或者稍后回来刷新。',
)

async function onRefresh(): Promise<void> {
  await feed.refresh()
  refreshing.value = false
}

function nearBottom(): boolean {
  const element = sentinel.value
  if (!element) return false
  return element.getBoundingClientRect().top < window.innerHeight + 320
}

function maybeLoadMore(): void {
  if (!feed.loading && !feed.finished && nearBottom()) {
    void feed.load()
  }
}

function onScroll(): void {
  maybeLoadMore()
}

watch(
  () => feed.items.length,
  () => {
    void nextTick(maybeLoadMore)
  },
)

onMounted(() => {
  if (feed.items.length === 0) void feed.load(true)
  window.addEventListener('scroll', onScroll, { passive: true })
  void nextTick(maybeLoadMore)
})

onBeforeUnmount(() => {
  window.removeEventListener('scroll', onScroll)
})
</script>

<template>
  <div class="page feed-page">
    <header class="hero feed-hero">
      <div class="feed-hero__top">
        <span class="hero__eyebrow">RESEARCH SCOUT</span>
        <span class="feed-hero__date">{{ todayLabel }}</span>
      </div>
      <h1 class="hero__title">研报雷达</h1>
      <p class="hero__subtitle">关注可信作者，把噪声压缩成可解释的信号</p>

      <div class="feed-scope">
        <button
          type="button"
          :class="{ active: feed.scope === 'following' }"
          @click="feed.setScope('following')"
        >
          关注
        </button>
        <button
          type="button"
          :class="{ active: feed.scope === 'discover' }"
          @click="feed.setScope('discover')"
        >
          发现
        </button>
        <span class="feed-scope__hint">
          {{ feed.scope === 'following' ? '按你的作者权重排序' : '全网热度和共识' }}
        </span>
      </div>
    </header>

    <div class="feed-filters">
      <div class="filter-pills">
        <button
          v-for="option in sortOptions"
          :key="option.value"
          type="button"
          :class="{ active: feed.sort === option.value }"
          @click="feed.setSort(option.value)"
        >
          {{ option.label }}
        </button>
      </div>
      <span class="filter-divider" />
      <div class="filter-windows">
        <button
          v-for="option in windowOptions"
          :key="option"
          type="button"
          :class="{ active: feed.window === option }"
          @click="feed.setWindow(option)"
        >
          {{ windowLabels[option] }}
        </button>
      </div>
    </div>

    <van-pull-refresh v-model="refreshing" @refresh="onRefresh">
      <div class="feed-list">
        <ReportCard v-for="item in feed.items" :key="item.id" :report="item" />

        <div v-if="feed.loading" class="loading-block">
          <van-loading size="20" vertical>正在载入信号…</van-loading>
        </div>

        <div v-if="feed.error" class="empty-state">
          <van-icon name="warning-o" size="30" />
          <p class="empty-state__title">加载失败</p>
          <p class="empty-state__text">{{ feed.error }}</p>
          <van-button size="small" round class="retry-button" @click="feed.load(true)">
            重新加载
          </van-button>
        </div>

        <div
          v-else-if="!feed.loading && feed.finished && feed.items.length === 0"
          class="empty-state"
        >
          <van-icon name="notes-o" size="32" />
          <p class="empty-state__title">{{ emptyTitle }}</p>
          <p class="empty-state__text">{{ emptyText }}</p>
          <van-button
            v-if="feed.scope === 'following'"
            size="small"
            round
            type="primary"
            class="retry-button"
            @click="router.push('/authors')"
          >
            去关注作者
          </van-button>
          <van-button
            v-else
            size="small"
            round
            class="retry-button"
            @click="feed.setWindow('30d')"
          >
            扩大时间窗口
          </van-button>
        </div>

        <div
          v-else-if="!feed.loading && feed.finished && feed.items.length"
          class="list-end"
        >
          — 已经到底了 —
        </div>

        <div ref="sentinel" class="feed-sentinel" />
      </div>
    </van-pull-refresh>
  </div>
</template>

<style scoped>
.feed-page {
  background:
    linear-gradient(180deg, #0e2439 0, #0e2439 210px, transparent 210px),
    var(--rs-bg);
}

.feed-hero {
  padding-bottom: 22px;
}

.feed-hero__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.feed-hero__date {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.5);
  letter-spacing: 0.06em;
}

.feed-hero .hero__title {
  font-size: 26px;
  letter-spacing: 0.04em;
}

.feed-scope {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 18px;
  padding: 4px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(6px);
}

.feed-scope button {
  padding: 8px 18px;
  border: none;
  border-radius: 9px;
  background: transparent;
  font-size: 13px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.62);
  cursor: pointer;
  transition: all 0.2s ease;
}

.feed-scope button.active {
  background: #fff;
  color: var(--rs-navy);
  box-shadow: 0 3px 10px rgba(0, 0, 0, 0.22);
}

.feed-scope__hint {
  margin-left: auto;
  padding-right: 10px;
  font-size: 10.5px;
  color: rgba(255, 255, 255, 0.42);
  white-space: nowrap;
}

.feed-filters {
  position: sticky;
  top: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  gap: 8px;
  margin: -6px 10px 0;
  padding: 9px 10px;
  border-radius: 13px;
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid rgba(232, 237, 243, 0.9);
  box-shadow: 0 6px 20px rgba(16, 35, 58, 0.07);
  backdrop-filter: blur(10px);
  overflow-x: auto;
  scrollbar-width: none;
}

.feed-filters::-webkit-scrollbar {
  display: none;
}

.filter-pills,
.filter-windows {
  display: flex;
  gap: 4px;
  flex: none;
}

.filter-pills button,
.filter-windows button {
  padding: 5px 11px;
  border: none;
  border-radius: 8px;
  background: transparent;
  font-size: 11.5px;
  font-weight: 600;
  color: var(--rs-muted);
  white-space: nowrap;
  cursor: pointer;
}

.filter-pills button.active {
  background: var(--rs-navy);
  color: #fff;
}

.filter-windows button.active {
  background: var(--rs-accent-soft);
  color: var(--rs-accent);
}

.filter-divider {
  width: 1px;
  height: 14px;
  background: var(--rs-line);
  flex: none;
}

.feed-list {
  padding: 12px 12px 8px;
}

.feed-sentinel {
  height: 1px;
}

.retry-button {
  margin-top: 16px;
  padding: 0 22px;
}
</style>
