<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { api } from '@/api/client'
import type { ReportDetail } from '@/api/types'
import { categoryLabel, formatDate, formatTime } from '@/utils/format'

const route = useRoute()
const router = useRouter()

const report = ref<ReportDetail | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)

const allTags = computed(() => {
  if (!report.value) return []
  const tags = [
    ...report.value.industry_mentions.map((item) => item.name),
    ...report.value.macro_mentions.map((item) => item.tag),
  ]
  return [...new Set(tags)]
})

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    report.value = await api.get<ReportDetail>(`/reports/${route.params.id}`)
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败'
  } finally {
    loading.value = false
  }
}

function goBack(): void {
  if (window.history.length > 1) router.back()
  else void router.push('/feed')
}

function openStock(code: string | null): void {
  if (code) void router.push({ name: 'stock', params: { code } })
}

onMounted(load)
</script>

<template>
  <div class="page page--plain detail-page">
    <header class="detail-nav">
      <button type="button" class="detail-nav__back" aria-label="返回" @click="goBack">
        <van-icon name="arrow-left" size="18" />
      </button>
      <span class="detail-nav__title">研报详情</span>
      <a
        v-if="report"
        class="detail-nav__link"
        :href="report.url"
        target="_blank"
        rel="noopener noreferrer"
      >
        原文
        <van-icon name="arrow" size="10" />
      </a>
      <span v-else class="detail-nav__link is-placeholder" />
    </header>

    <div v-if="loading" class="detail-loading">
      <van-loading size="24" vertical>正在读取研报…</van-loading>
    </div>

    <div v-else-if="error" class="empty-state">
      <van-icon name="warning-o" size="32" />
      <p class="empty-state__title">无法打开这篇研报</p>
      <p class="empty-state__text">{{ error }}</p>
      <van-button size="small" round class="retry" @click="load">重试</van-button>
    </div>

    <template v-else-if="report">
      <article class="detail-head">
        <div class="detail-head__meta">
          <span class="chip" :class="report.primary_category ? `chip--${report.primary_category}` : 'chip--outline'">
            {{ categoryLabel(report.primary_category) }}
          </span>
          <span v-for="category in report.categories.filter((c) => c !== report?.primary_category)" :key="category" class="chip chip--outline">
            {{ categoryLabel(category) }}
          </span>
          <span v-if="report.is_reprint" class="chip chip--outline">转载 · {{ report.reprint_count + 1 }}</span>
        </div>

        <h1 class="detail-head__title">{{ report.title }}</h1>

        <div class="detail-head__byline">
          <span class="detail-head__author">{{ report.author?.name ?? report.source_name ?? '未知来源' }}</span>
          <span v-if="report.source_name && report.author" class="detail-head__source">
            {{ report.source_name }}
          </span>
          <span class="detail-head__time">{{ formatTime(report.published_at) }}</span>
        </div>
      </article>

      <section v-if="report.summary || report.opinion" class="section">
        <div class="section__head">
          <h2 class="section__title">AI 速读</h2>
          <span class="section__hint">由模型生成，仅供研究参考</span>
        </div>
        <div class="card detail-block">
          <p v-if="report.summary" class="detail-summary">{{ report.summary }}</p>
          <div v-if="report.opinion" class="detail-opinion">
            <span class="detail-opinion__label">观点</span>
            <p>{{ report.opinion }}</p>
          </div>
        </div>
      </section>

      <section v-if="report.key_points.length" class="section">
        <div class="section__head">
          <h2 class="section__title">关键信息</h2>
        </div>
        <ol class="card key-points">
          <li v-for="(point, index) in report.key_points" :key="index">{{ point }}</li>
        </ol>
      </section>

      <section v-if="report.stock_mentions.length || allTags.length" class="section">
        <div class="section__head">
          <h2 class="section__title">关联标的</h2>
        </div>
        <div class="card entity-card">
          <div v-if="report.stock_mentions.length" class="entity-group">
            <span class="entity-group__label">个股</span>
            <div class="tag-row">
              <button
                v-for="mention in report.stock_mentions"
                :key="`${mention.code}-${mention.name}`"
                type="button"
                class="chip chip--stock entity-chip"
                :disabled="!mention.code"
                @click="openStock(mention.code)"
              >
                {{ mention.name }}
                <span v-if="mention.code" class="entity-chip__code">{{ mention.code }}</span>
                <van-icon
                  v-if="mention.sentiment > 0.15"
                  name="arrow-up"
                  size="9"
                  class="up"
                />
                <van-icon
                  v-else-if="mention.sentiment < -0.15"
                  name="arrow-down"
                  size="9"
                  class="down"
                />
              </button>
            </div>
          </div>
          <div v-if="allTags.length" class="entity-group">
            <span class="entity-group__label">行业 / 宏观</span>
            <div class="tag-row">
              <span
                v-for="tag in allTags"
                :key="tag"
                class="chip"
                :class="
                  report.industry_mentions.some((item) => item.name === tag)
                    ? 'chip--industry'
                    : 'chip--macro'
                "
              >
                {{ tag }}
              </span>
            </div>
          </div>
        </div>
      </section>

      <section v-if="report.rationale" class="section">
        <div class="section__head">
          <h2 class="section__title">评分依据</h2>
        </div>
        <div class="card detail-block">
          <p class="detail-rationale">{{ report.rationale }}</p>
        </div>
      </section>

      <section v-if="report.keywords.length" class="section">
        <div class="section__head">
          <h2 class="section__title">关键词</h2>
        </div>
        <div class="tag-row">
          <span v-for="keyword in report.keywords" :key="keyword" class="chip chip--outline">
            {{ keyword }}
          </span>
        </div>
      </section>

      <section class="section">
        <div class="section__head">
          <h2 class="section__title">正文</h2>
          <span v-if="report.analyzed_at" class="section__hint">
            分析于 {{ formatDate(report.analyzed_at) }}
          </span>
        </div>
        <div class="card detail-content">
          <p v-if="!report.content" class="muted">这篇内容没有提供正文，请查看原文。</p>
          <p v-else class="detail-content__text">{{ report.content }}</p>
        </div>
      </section>

      <footer class="detail-footer">
        <p>AI 输出可能存在偏差，请结合原始信息独立判断。</p>
        <p class="detail-footer__source">来源：{{ report.source_name ?? '—' }} · {{ formatDate(report.published_at) }}</p>
      </footer>
    </template>
  </div>
</template>

<style scoped>
.detail-page {
  background: var(--rs-bg);
}

.detail-nav {
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

.detail-nav__back {
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

.detail-nav__title {
  flex: 1;
  font-size: 14px;
  font-weight: 700;
  letter-spacing: 0.04em;
}

.detail-nav__link {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 12px;
  font-weight: 600;
  color: var(--rs-accent);
}

.detail-nav__link.is-placeholder {
  width: 34px;
}

.detail-loading {
  padding: 90px 0;
}

.detail-head {
  padding: 20px 18px 16px;
  background:
    radial-gradient(600px 200px at 110% -30%, rgba(194, 65, 12, 0.1), transparent 65%),
    #fff;
  border-bottom: 1px solid var(--rs-line);
}

.detail-head__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.detail-head__title {
  margin: 12px 0 12px;
  font-size: 22px;
  line-height: 1.45;
  font-weight: 700;
  letter-spacing: 0.01em;
}

.detail-head__byline {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 12px;
  color: var(--rs-muted);
}

.detail-head__author {
  font-weight: 600;
  color: var(--rs-ink-soft);
}

.detail-head__source {
  padding-left: 8px;
  border-left: 1px solid var(--rs-line);
}

.detail-head__time {
  margin-left: auto;
}

.detail-block {
  padding: 16px;
}

.detail-summary {
  margin: 0;
  font-size: 14px;
  line-height: 1.85;
  color: var(--rs-ink-soft);
}

.detail-opinion {
  display: flex;
  gap: 10px;
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px dashed var(--rs-line);
}

.detail-opinion__label {
  flex: none;
  padding: 1px 7px;
  height: fit-content;
  border-radius: 6px;
  background: var(--rs-accent-soft);
  color: var(--rs-accent);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.detail-opinion p {
  margin: 0;
  font-size: 13px;
  line-height: 1.8;
  color: var(--rs-ink-soft);
}

.key-points {
  margin: 0;
  padding: 14px 18px 14px 34px;
  font-size: 13px;
  line-height: 1.85;
  color: var(--rs-ink-soft);
}

.key-points li {
  padding-left: 2px;
}

.key-points li + li {
  margin-top: 6px;
}

.key-points li::marker {
  color: var(--rs-accent);
  font-weight: 700;
}

.entity-card {
  padding: 15px 16px;
}

.entity-group + .entity-group {
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px dashed var(--rs-line);
}

.entity-group__label {
  display: block;
  margin-bottom: 8px;
  font-size: 11px;
  font-weight: 600;
  color: var(--rs-muted);
  letter-spacing: 0.06em;
}

.entity-chip {
  border: none;
  cursor: pointer;
}

.entity-chip:disabled {
  cursor: default;
}

.entity-chip__code {
  font-weight: 400;
  opacity: 0.65;
  font-size: 10px;
}

.detail-rationale {
  margin: 0;
  font-size: 13px;
  line-height: 1.85;
  color: var(--rs-ink-soft);
}

.detail-content {
  padding: 18px 16px;
}

.detail-content__text {
  margin: 0;
  font-size: 14px;
  line-height: 1.95;
  color: var(--rs-ink-soft);
  white-space: pre-wrap;
  word-break: break-word;
}

.detail-footer {
  padding: 26px 20px calc(30px + env(safe-area-inset-bottom));
  text-align: center;
  font-size: 10.5px;
  line-height: 1.8;
  color: var(--rs-muted);
}

.detail-footer p {
  margin: 0;
}

.detail-footer__source {
  margin-top: 4px !important;
  opacity: 0.75;
}

.retry {
  margin-top: 16px;
}
</style>
