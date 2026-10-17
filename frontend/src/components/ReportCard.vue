<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'

import type { ReportItem } from '@/api/types'
import { categoryLabel, directionLabel, directionClass, formatTime } from '@/utils/format'

const props = defineProps<{ report: ReportItem }>()
const router = useRouter()

const chipClass = computed(() => {
  const category = props.report.primary_category
  return category ? `chip--${category}` : 'chip--outline'
})

function open(): void {
  void router.push({ name: 'report', params: { id: props.report.id } })
}
</script>

<template>
  <article class="report-card card" @click="open">
    <header class="report-card__meta">
      <span class="chip" :class="chipClass">{{ categoryLabel(report.primary_category) }}</span>
      <span class="report-card__author">{{ report.author?.name ?? report.source_name ?? '未知来源' }}</span>
      <span class="report-card__sep">·</span>
      <span>{{ formatTime(report.published_at) }}</span>
      <span v-if="report.is_reprint" class="chip chip--outline report-card__flag">转载</span>
    </header>

    <div class="report-card__main">
      <div class="report-card__text">
        <h3 class="report-card__title">{{ report.title }}</h3>
        <p v-if="report.summary" class="report-card__summary">{{ report.summary }}</p>
      </div>
    </div>

    <footer class="report-card__footer">
      <div class="tag-row">
        <span v-for="code in report.stock_codes.slice(0, 2)" :key="code" class="chip chip--stock">
          {{ code }}
        </span>
        <span
          v-for="keyword in report.keywords.slice(0, 3)"
          :key="keyword"
          class="chip chip--outline"
        >
          {{ keyword }}
        </span>
      </div>
      <span class="report-card__direction" :class="directionClass(report.score)">
        {{ directionLabel(report.direction) }}
      </span>
    </footer>
  </article>
</template>

<style scoped>
.report-card {
  padding: 14px 15px 12px;
  cursor: pointer;
  transition:
    transform 0.15s ease,
    box-shadow 0.15s ease;
}

.report-card:active {
  transform: scale(0.99);
  box-shadow: 0 4px 14px rgba(16, 35, 58, 0.08);
}

.report-card + .report-card {
  margin-top: 10px;
}

.report-card__meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--rs-muted);
}

.report-card__author {
  max-width: 40%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 600;
  color: var(--rs-ink-soft);
}

.report-card__sep {
  opacity: 0.5;
}

.report-card__flag {
  margin-left: auto;
}

.report-card__main {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-top: 10px;
}

.report-card__text {
  flex: 1;
  min-width: 0;
}

.report-card__title {
  margin: 0;
  font-size: 15.5px;
  font-weight: 700;
  line-height: 1.45;
  color: var(--rs-ink);
  display: -webkit-box;
  overflow: hidden;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.report-card__summary {
  margin: 7px 0 0;
  font-size: 12.5px;
  line-height: 1.65;
  color: var(--rs-muted);
  display: -webkit-box;
  overflow: hidden;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.report-card__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: 11px;
  padding-top: 10px;
  border-top: 1px dashed var(--rs-line);
}

.report-card__footer .tag-row {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  flex-wrap: nowrap;
}

.report-card__direction {
  flex: none;
  font-size: 11px;
  font-weight: 700;
}
</style>
