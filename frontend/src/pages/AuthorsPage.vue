<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { showConfirmDialog, showToast } from 'vant'

import { api } from '@/api/client'
import type { Author, AuthorDetail, FollowedAuthor, Page } from '@/api/types'

const tab = ref<'following' | 'all'>('following')
const q = ref('')
const loading = ref(false)
const following = ref<FollowedAuthor[]>([])
const allAuthors = ref<Author[]>([])
const allTotal = ref(0)
const page = ref(1)
const pageSize = 30
const hasMore = computed(() => allAuthors.value.length < allTotal.value)

const followMap = computed<Record<number, FollowedAuthor>>(() => {
  const map: Record<number, FollowedAuthor> = {}
  for (const item of following.value) map[item.author.id] = item
  return map
})

const filteredFollowing = computed(() => {
  const needle = q.value.trim()
  if (!needle) return following.value
  return following.value.filter((item) =>
    item.author.canonical_name.toLowerCase().includes(needle.toLowerCase()),
  )
})

const typeLabels: Record<string, string> = {
  analyst: '分析师',
  blogger: '博主',
  institution: '机构',
  media: '媒体',
  other: '作者',
}

const avatarPalette = ['#2855a8', '#6941c6', '#9a6700', '#0b8f63', '#c2410c', '#0e7490']

function avatarColor(name: string): string {
  let sum = 0
  for (const char of name) sum += char.charCodeAt(0)
  return avatarPalette[sum % avatarPalette.length]
}

function initial(name: string): string {
  return name.trim().slice(0, 1) || '?'
}

let searchTimer: number | undefined

async function loadFollowing(): Promise<void> {
  following.value = await api.get<FollowedAuthor[]>('/authors/following')
}

async function loadAll(reset = false): Promise<void> {
  if (reset) {
    page.value = 1
    allAuthors.value = []
  }
  const response = await api.get<Page<Author>>('/authors', {
    q: q.value.trim() || undefined,
    page: page.value,
    page_size: pageSize,
  })
  allAuthors.value = reset ? response.items : [...allAuthors.value, ...response.items]
  allTotal.value = response.total
}

async function refreshCurrent(): Promise<void> {
  loading.value = true
  try {
    if (tab.value === 'following') await loadFollowing()
    else await loadAll(true)
  } catch (error) {
    showToast(error instanceof Error ? error.message : '加载失败')
  } finally {
    loading.value = false
  }
}

function switchTab(next: 'following' | 'all'): void {
  if (tab.value === next) return
  tab.value = next
  q.value = ''
  void refreshCurrent()
}

async function loadMore(): Promise<void> {
  page.value += 1
  try {
    await loadAll(false)
  } catch (error) {
    page.value -= 1
    showToast(error instanceof Error ? error.message : '加载失败')
  }
}

async function toggleFollow(author: Author): Promise<void> {
  const existing = followMap.value[author.id]
  try {
    if (existing) {
      await showConfirmDialog({
        title: '取消关注',
        message: `确定不再关注「${author.canonical_name}」吗？`,
        confirmButtonText: '取消关注',
        cancelButtonText: '再想想',
      })
      await api.delete(`/authors/${author.id}/follow`)
      showToast('已取消关注')
    } else {
      await api.post(`/authors/${author.id}/follow`, {
        weight: author.default_weight,
        notify: false,
      })
      showToast('已关注')
    }
    await loadFollowing()
    if (tab.value === 'all') await loadAll(true)
  } catch (error) {
    if (error === 'cancel' || (error instanceof Error && error.message.includes('cancel'))) return
    showToast(error instanceof Error ? error.message : '操作失败')
  }
}

/* ---------- weight / follow popup ---------- */

const weightPopup = ref(false)
const weightAuthor = ref<Author | null>(null)
const weightValue = ref(1)
const weightSaving = ref(false)

function openWeight(author: Author): void {
  weightAuthor.value = author
  weightValue.value = followMap.value[author.id]?.weight ?? author.default_weight ?? 1
  weightPopup.value = true
}

async function saveWeight(): Promise<void> {
  if (!weightAuthor.value) return
  weightSaving.value = true
  try {
    await api.post(`/authors/${weightAuthor.value.id}/follow`, {
      weight: weightValue.value,
      notify: followMap.value[weightAuthor.value.id]?.notify ?? false,
    })
    weightPopup.value = false
    showToast('权重已更新')
    await loadFollowing()
    if (tab.value === 'all') await loadAll(true)
  } catch (error) {
    showToast(error instanceof Error ? error.message : '保存失败')
  } finally {
    weightSaving.value = false
  }
}

/* ---------- create author popup ---------- */

const createPopup = ref(false)
const creating = ref(false)
const createForm = reactive({
  canonical_name: '',
  author_type: 'analyst',
  default_weight: 1,
})

function openCreate(): void {
  createForm.canonical_name = ''
  createForm.author_type = 'analyst'
  createForm.default_weight = 1
  createPopup.value = true
}

async function createAuthor(): Promise<void> {
  if (!createForm.canonical_name.trim()) {
    showToast('请填写作者名称')
    return
  }
  creating.value = true
  try {
    const created = await api.post<AuthorDetail>('/authors', {
      canonical_name: createForm.canonical_name.trim(),
      author_type: createForm.author_type,
      default_weight: createForm.default_weight,
    })
    await api.post(`/authors/${created.id}/follow`, {
      weight: createForm.default_weight,
      notify: false,
    })
    createPopup.value = false
    showToast('作者已创建并关注')
    await Promise.all([loadFollowing(), loadAll(true)])
  } catch (error) {
    showToast(error instanceof Error ? error.message : '创建失败')
  } finally {
    creating.value = false
  }
}

watch(q, () => {
  if (tab.value !== 'all') return
  window.clearTimeout(searchTimer)
  searchTimer = window.setTimeout(() => {
    void loadAll(true)
  }, 350)
})

onMounted(async () => {
  loading.value = true
  try {
    await Promise.all([loadFollowing(), loadAll(true)])
  } catch (error) {
    showToast(error instanceof Error ? error.message : '加载失败')
  } finally {
    loading.value = false
  }
})

onBeforeUnmount(() => {
  window.clearTimeout(searchTimer)
})
</script>

<template>
  <div class="page authors-page">
    <header class="hero authors-hero">
      <div class="authors-hero__top">
        <span class="hero__eyebrow">AUTHOR GRAPH</span>
        <button type="button" class="authors-hero__add" @click="openCreate">
          <van-icon name="plus" size="12" />
          添加作者
        </button>
      </div>
      <h1 class="hero__title">作者</h1>
      <p class="hero__subtitle">你信任谁，决定你看到什么</p>
    </header>

    <div class="authors-toolbar">
      <div class="authors-search">
        <van-icon name="search" size="15" class="authors-search__icon" />
        <input
          v-model="q"
          type="search"
          placeholder="搜索作者名称"
          class="authors-search__input"
        />
        <button v-if="q" type="button" class="authors-search__clear" @click="q = ''">
          <van-icon name="cross" size="12" />
        </button>
      </div>

      <div class="authors-tabs">
        <button
          type="button"
          :class="{ active: tab === 'following' }"
          @click="switchTab('following')"
        >
          已关注
          <span class="authors-tabs__count">{{ following.length }}</span>
        </button>
        <button
          type="button"
          :class="{ active: tab === 'all' }"
          @click="switchTab('all')"
        >
          发现作者
        </button>
      </div>
    </div>

    <div class="authors-list">
      <div v-if="loading" class="loading-block">
        <van-loading size="20" vertical>载入作者…</van-loading>
      </div>

      <template v-else-if="tab === 'following'">
        <div v-if="!filteredFollowing.length" class="empty-state">
          <van-icon name="friends-o" size="32" />
          <p class="empty-state__title">
            {{ q ? '没有匹配的作者' : '还没有关注任何作者' }}
          </p>
          <p class="empty-state__text">
            {{ q ? '换个关键词试试。' : '去「发现作者」关注你信任的博主，系统会按权重聚合他们的观点。' }}
          </p>
          <van-button
            v-if="!q"
            size="small"
            round
            type="primary"
            class="empty-action"
            @click="switchTab('all')"
          >
            发现作者
          </van-button>
        </div>

        <article
          v-for="item in filteredFollowing"
          :key="item.author.id"
          class="card author-card"
        >
          <div
            class="author-card__avatar"
            :style="{ background: avatarColor(item.author.canonical_name) }"
          >
            {{ initial(item.author.canonical_name) }}
          </div>
          <div class="author-card__body">
            <div class="author-card__name-row">
              <h3>{{ item.author.canonical_name }}</h3>
              <span class="chip chip--outline">
                {{ typeLabels[item.author.author_type] ?? item.author.author_type }}
              </span>
            </div>
            <p class="author-card__meta">
              权重 {{ item.weight.toFixed(1) }}
              <span class="author-card__dot">·</span>
              {{ item.notify ? '已开启提醒' : '关注中' }}
            </p>
          </div>
          <div class="author-card__actions">
            <button type="button" class="weight-pill" @click="openWeight(item.author)">
              权重 {{ item.weight.toFixed(1) }}
            </button>
            <button type="button" class="text-button" @click="toggleFollow(item.author)">
              取消关注
            </button>
          </div>
        </article>
      </template>

      <template v-else>
        <div v-if="!allAuthors.length && !loading" class="empty-state">
          <van-icon name="search" size="32" />
          <p class="empty-state__title">没有找到作者</p>
          <p class="empty-state__text">换个关键词，或手动添加一位作者。</p>
          <van-button size="small" round type="primary" class="empty-action" @click="openCreate">
            添加作者
          </van-button>
        </div>

        <article
          v-for="author in allAuthors"
          :key="author.id"
          class="card author-card"
        >
          <div
            class="author-card__avatar"
            :style="{ background: avatarColor(author.canonical_name) }"
          >
            {{ initial(author.canonical_name) }}
          </div>
          <div class="author-card__body">
            <div class="author-card__name-row">
              <h3>{{ author.canonical_name }}</h3>
              <span class="chip chip--outline">
                {{ typeLabels[author.author_type] ?? author.author_type }}
              </span>
            </div>
            <p class="author-card__meta">
              默认权重 {{ author.default_weight.toFixed(1) }}
              <span v-if="followMap[author.id]" class="author-card__dot">·</span>
              <span v-if="followMap[author.id]" class="up">
                已关注 · {{ followMap[author.id].weight.toFixed(1) }}
              </span>
            </p>
          </div>
          <div class="author-card__actions">
            <button
              v-if="followMap[author.id]"
              type="button"
              class="weight-pill"
              @click="openWeight(author)"
            >
              调权重
            </button>
            <button
              type="button"
              class="follow-button"
              :class="{ 'is-followed': followMap[author.id] }"
              @click="toggleFollow(author)"
            >
              {{ followMap[author.id] ? '已关注' : '+ 关注' }}
            </button>
          </div>
        </article>

        <div v-if="allAuthors.length" class="authors-more">
          <van-button
            v-if="hasMore"
            size="small"
            round
            plain
            :loading="loading"
            @click="loadMore"
          >
            加载更多（{{ allAuthors.length }} / {{ allTotal }}）
          </van-button>
          <p v-else class="list-end">—— 共 {{ allTotal }} 位作者 ——</p>
        </div>
      </template>
    </div>

    <!-- weight popup -->
    <van-popup v-model:show="weightPopup" position="bottom" round closeable>
      <div class="sheet">
        <h3 class="sheet__title">
          {{ weightAuthor?.canonical_name }}
        </h3>
        <p class="sheet__subtitle">
          权重越高，这位作者的观点在自选股聚合中影响越大。
        </p>
        <div class="weight-value">
          <span class="mono">{{ weightValue.toFixed(1) }}</span>
          <span class="weight-value__unit">x</span>
        </div>
        <van-slider
          v-model="weightValue"
          :min="0.1"
          :max="5"
          :step="0.1"
          bar-height="6px"
          active-color="#c2410c"
        />
        <div class="weight-ticks">
          <button
            v-for="value in [0.5, 1, 1.5, 2, 3]"
            :key="value"
            type="button"
            :class="{ active: Math.abs(weightValue - value) < 0.05 }"
            @click="weightValue = value"
          >
            {{ value }}x
          </button>
        </div>
        <van-button
          block
          round
          type="primary"
          :loading="weightSaving"
          class="sheet__submit"
          @click="saveWeight"
        >
          保存权重
        </van-button>
      </div>
    </van-popup>

    <!-- create author popup -->
    <van-popup v-model:show="createPopup" position="bottom" round closeable>
      <div class="sheet">
        <h3 class="sheet__title">添加作者</h3>
        <p class="sheet__subtitle">
          系统会自动把不同渠道的同名作者归并到一起；创建后会立即关注。
        </p>

        <label class="sheet-label">
          作者名称
          <input
            v-model="createForm.canonical_name"
            type="text"
            maxlength="128"
            placeholder="例如：某位分析师 / 博主"
            class="sheet-input"
          />
        </label>

        <span class="sheet-label">类型</span>
        <div class="type-options">
          <button
            v-for="(label, value) in typeLabels"
            :key="value"
            type="button"
            :class="{ active: createForm.author_type === value }"
            @click="createForm.author_type = value"
          >
            {{ label }}
          </button>
        </div>

        <span class="sheet-label">默认权重 · {{ createForm.default_weight.toFixed(1) }}x</span>
        <van-slider
          v-model="createForm.default_weight"
          :min="0.1"
          :max="5"
          :step="0.1"
          bar-height="6px"
          active-color="#c2410c"
        />

        <van-button
          block
          round
          type="primary"
          :loading="creating"
          class="sheet__submit"
          @click="createAuthor"
        >
          创建并关注
        </van-button>
      </div>
    </van-popup>
  </div>
</template>

<style scoped>
.authors-page {
  background:
    linear-gradient(180deg, #0e2439 0, #0e2439 196px, transparent 196px),
    var(--rs-bg);
}

.authors-hero {
  padding-bottom: 20px;
}

.authors-hero__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.authors-hero__add {
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

.authors-toolbar {
  margin: -8px 12px 0;
  padding: 12px;
  border-radius: 16px;
  background: #fff;
  box-shadow: var(--rs-shadow);
  border: 1px solid rgba(232, 237, 243, 0.9);
}

.authors-search {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 12px;
  border-radius: 11px;
  background: var(--rs-neutral-soft);
}

.authors-search__icon {
  color: var(--rs-muted);
}

.authors-search__input {
  flex: 1;
  min-width: 0;
  border: none;
  background: transparent;
  font-size: 13px;
  color: var(--rs-ink);
  outline: none;
}

.authors-search__input::placeholder {
  color: #a3afbf;
}

.authors-search__clear {
  display: grid;
  place-items: center;
  width: 18px;
  height: 18px;
  border: none;
  border-radius: 50%;
  background: #dbe2ea;
  color: #fff;
  cursor: pointer;
}

.authors-tabs {
  display: flex;
  gap: 4px;
  margin-top: 10px;
  padding: 3px;
  border-radius: 10px;
  background: var(--rs-neutral-soft);
}

.authors-tabs button {
  flex: 1;
  padding: 7px 0;
  border: none;
  border-radius: 8px;
  background: transparent;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--rs-muted);
  cursor: pointer;
}

.authors-tabs button.active {
  background: #fff;
  color: var(--rs-ink);
  box-shadow: 0 2px 6px rgba(16, 35, 58, 0.08);
}

.authors-tabs__count {
  margin-left: 4px;
  font-size: 10px;
  opacity: 0.6;
}

.authors-list {
  padding: 12px;
}

.author-card {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 13px 14px;
}

.author-card + .author-card {
  margin-top: 9px;
}

.author-card__avatar {
  display: grid;
  place-items: center;
  flex: none;
  width: 42px;
  height: 42px;
  border-radius: 13px;
  color: #fff;
  font-size: 17px;
  font-weight: 700;
  box-shadow: inset 0 -8px 14px rgba(0, 0, 0, 0.12);
}

.author-card__body {
  flex: 1;
  min-width: 0;
}

.author-card__name-row {
  display: flex;
  align-items: center;
  gap: 7px;
}

.author-card__name-row h3 {
  margin: 0;
  font-size: 14.5px;
  font-weight: 700;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.author-card__meta {
  margin: 5px 0 0;
  font-size: 11px;
  color: var(--rs-muted);
}

.author-card__dot {
  margin: 0 2px;
  opacity: 0.6;
}

.author-card__actions {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 5px;
  flex: none;
}

.weight-pill {
  padding: 4px 9px;
  border: 1px solid var(--rs-line);
  border-radius: 999px;
  background: #fbfcfe;
  color: var(--rs-ink-soft);
  font-size: 10.5px;
  font-weight: 600;
  cursor: pointer;
}

.text-button {
  padding: 0;
  border: none;
  background: transparent;
  font-size: 10.5px;
  color: var(--rs-muted);
  cursor: pointer;
}

.follow-button {
  padding: 5px 12px;
  border: 1px solid var(--rs-accent);
  border-radius: 999px;
  background: var(--rs-accent);
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
}

.follow-button.is-followed {
  background: var(--rs-up-soft);
  border-color: transparent;
  color: var(--rs-up);
}

.empty-action {
  margin-top: 16px;
  padding: 0 24px;
}

.authors-more {
  display: flex;
  justify-content: center;
  padding: 16px 0 8px;
}

.sheet {
  padding: 22px 20px calc(24px + env(safe-area-inset-bottom));
}

.sheet__title {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
}

.sheet__subtitle {
  margin: 6px 0 20px;
  font-size: 11.5px;
  line-height: 1.7;
  color: var(--rs-muted);
}

.weight-value {
  display: flex;
  align-items: baseline;
  justify-content: center;
  gap: 3px;
  margin-bottom: 10px;
  color: var(--rs-accent);
}

.weight-value .mono {
  font-size: 34px;
  font-weight: 700;
  letter-spacing: -0.02em;
}

.weight-value__unit {
  font-size: 15px;
  font-weight: 600;
  opacity: 0.7;
}

.weight-ticks {
  display: flex;
  justify-content: space-between;
  gap: 6px;
  margin: 16px 0 22px;
}

.weight-ticks button {
  flex: 1;
  padding: 6px 0;
  border: 1px solid var(--rs-line);
  border-radius: 8px;
  background: #fff;
  font-size: 11px;
  color: var(--rs-muted);
  cursor: pointer;
}

.weight-ticks button.active {
  border-color: var(--rs-accent);
  background: var(--rs-accent-soft);
  color: var(--rs-accent);
  font-weight: 700;
}

.sheet__submit {
  height: 44px;
  font-size: 14px;
  font-weight: 600;
}

.sheet-label {
  display: block;
  margin: 18px 0 8px;
  font-size: 12px;
  font-weight: 600;
  color: var(--rs-ink-soft);
}

.sheet-input {
  display: block;
  width: 100%;
  margin-top: 8px;
  padding: 11px 13px;
  border: 1px solid var(--rs-line);
  border-radius: 10px;
  background: #fbfcfe;
  font-size: 14px;
  outline: none;
}

.sheet-input:focus {
  border-color: var(--rs-accent);
  background: #fff;
}

.type-options {
  display: flex;
  gap: 7px;
  flex-wrap: wrap;
}

.type-options button {
  padding: 7px 14px;
  border: 1px solid var(--rs-line);
  border-radius: 999px;
  background: #fff;
  font-size: 12px;
  color: var(--rs-muted);
  cursor: pointer;
}

.type-options button.active {
  border-color: var(--rs-navy);
  background: var(--rs-navy);
  color: #fff;
  font-weight: 600;
}
</style>
