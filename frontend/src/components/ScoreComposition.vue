<script setup lang="ts">
import { computed } from 'vue'

import type { Category, CategoryScore } from '@/api/types'
import { categoryLabel } from '@/utils/format'

const props = defineProps<{
  categories: CategoryScore[]
  total: number
  reportCount: number
}>()

const ORDER: Category[] = ['stock', 'industry', 'macro']
const COLORS: Record<Category, string> = {
  stock: '#2a78d6',
  industry: '#eb6834',
  macro: '#1baf7a',
}

const rows = computed(() =>
  ORDER.map((category) => {
    const score = props.categories.find((item) => item.category === category)
    return {
      category,
      label: categoryLabel(category),
      color: COLORS[category],
      score,
      points: score?.points ?? 0,
      budget: score?.budget_points ?? 0,
      count: score?.article_count ?? 0,
      signal: score?.weighted_signal ?? 0,
      missing: !score,
    }
  }),
)

const visibleRows = computed(() => rows.value.filter((row) => !row.missing))

const remainder = computed(() => Math.max(0, 100 - props.total))

const segments = computed(() => {
  let cursor = 0
  return visibleRows.value.map((row) => {
    const width = Math.max(0, row.points)
    const segment = {
      key: row.category,
      color: row.color,
      x: cursor,
      width: Math.max(0, width - 2),
    }
    cursor += width
    return segment
  })
})

const meterWidth = (points: number, budget: number): number => {
  if (budget <= 0) return 0
  return Math.max(0, Math.min(100, (points / budget) * 100))
}

function signalText(value: number): string {
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}`
}
</script>

<template>
  <section class="section">
    <div class="section__head">
      <h2 class="section__title">评分构成</h2>
      <span class="section__hint">{{ reportCount }} 篇研报</span>
    </div>

    <div class="card composition">
      <div class="composition__summary">
        <div>
          <p class="composition__eyebrow">综合得分</p>
          <p class="composition__total mono">
            {{ total.toFixed(1) }}
            <span>/ 100</span>
          </p>
        </div>
        <p class="composition__note">
          未得分 {{ remainder.toFixed(1) }}
        </p>
      </div>

      <svg
        class="composition__bar"
        viewBox="0 0 300 18"
        preserveAspectRatio="none"
        role="img"
        :aria-label="`得分构成：${visibleRows.map((row) => `${row.label}${row.points.toFixed(1)}分`).join('，')}，未得分${remainder.toFixed(1)}分`"
      >
        <rect x="0" y="0" width="300" height="18" rx="5" fill="#e8edf3" />
        <rect
          v-for="segment in segments"
          :key="segment.key"
          :x="segment.x"
          y="0"
          :width="segment.width"
          height="18"
          rx="4"
          :fill="segment.color"
        />
        <rect
          v-if="remainder > 0"
          :x="Math.min(300, Math.max(0, total))"
          y="0"
          :width="Math.max(0, 300 - total - 2)"
          height="18"
          rx="4"
          fill="#dfe7f0"
        />
      </svg>

      <div class="composition__legend">
        <div v-for="row in rows" :key="row.category" class="composition__legend-row">
          <span
            class="composition__dot"
            :style="{ background: row.missing ? '#cbd5e1' : row.color }"
          />
          <span class="composition__legend-label">{{ row.label }}</span>
          <span v-if="row.missing" class="composition__missing">
            无相关研报 · 配额已并入其他板块
          </span>
          <template v-else>
            <span class="composition__legend-value mono">
              {{ row.points.toFixed(1) }}
              <small>/ {{ row.budget.toFixed(0) }}</small>
            </span>
            <span class="composition__legend-count">{{ row.count }} 篇</span>
          </template>
        </div>
        <div class="composition__legend-row composition__legend-row--remainder">
          <span class="composition__dot" style="background: #dfe7f0" />
          <span class="composition__legend-label">未得分</span>
          <span class="composition__legend-value mono">{{ remainder.toFixed(1) }}</span>
        </div>
      </div>

      <div class="composition__meters">
        <div v-for="row in visibleRows" :key="row.category" class="composition__meter-row">
          <div class="composition__meter-head">
            <span>{{ row.label }}板块</span>
            <span class="mono">加权信号 {{ signalText(row.signal) }}</span>
          </div>
          <div class="composition__meter">
            <span
              class="composition__meter-fill"
              :style="{
                width: `${meterWidth(row.points, row.budget)}%`,
                background: row.color,
              }"
            />
          </div>
        </div>
      </div>

      <p class="composition__formula">
        板块配额默认 40 / 40 / 20；缺失板块按比例并入其余板块。板块得分 =
        (加权信号 + 1) ÷ 2 × 板块配额。
      </p>
    </div>
  </section>
</template>

<style scoped>
.composition {
  padding: 16px;
}

.composition__summary {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
}

.composition__eyebrow {
  margin: 0;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.14em;
  color: var(--rs-muted);
}

.composition__total {
  margin: 4px 0 0;
  font-size: 34px;
  font-weight: 800;
  line-height: 1;
  letter-spacing: -0.02em;
  color: var(--rs-ink);
}

.composition__total span {
  font-size: 12px;
  font-weight: 600;
  color: var(--rs-muted);
  letter-spacing: 0;
}

.composition__note {
  margin: 0;
  font-size: 10.5px;
  color: var(--rs-muted);
}

.composition__bar {
  display: block;
  width: 100%;
  height: 18px;
  margin-top: 16px;
  overflow: visible;
}

.composition__legend {
  margin-top: 12px;
}

.composition__legend-row {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 6px 0;
  font-size: 11.5px;
}

.composition__legend-row + .composition__legend-row {
  border-top: 1px solid var(--rs-line);
}

.composition__dot {
  flex: none;
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.composition__legend-label {
  flex: none;
  width: 44px;
  white-space: nowrap;
  font-weight: 600;
  color: var(--rs-ink-soft);
}

.composition__legend-value {
  margin-left: auto;
  font-size: 12.5px;
  font-weight: 700;
  color: var(--rs-ink);
}

.composition__legend-value small {
  font-size: 10px;
  font-weight: 500;
  color: var(--rs-muted);
}

.composition__legend-count {
  flex: none;
  width: 38px;
  text-align: right;
  font-size: 10px;
  color: var(--rs-muted);
}

.composition__missing {
  margin-left: auto;
  font-size: 10px;
  color: var(--rs-muted);
}

.composition__legend-row--remainder {
  color: var(--rs-muted);
}

.composition__meters {
  margin-top: 14px;
  padding-top: 13px;
  border-top: 1px dashed var(--rs-line);
}

.composition__meter-row + .composition__meter-row {
  margin-top: 11px;
}

.composition__meter-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 10.5px;
  color: var(--rs-muted);
}

.composition__meter {
  height: 5px;
  margin-top: 6px;
  border-radius: 99px;
  background: #eef2f7;
  overflow: hidden;
}

.composition__meter-fill {
  display: block;
  height: 100%;
  border-radius: 99px;
}

.composition__formula {
  margin: 14px 0 0;
  padding-top: 12px;
  border-top: 1px dashed var(--rs-line);
  font-size: 10px;
  line-height: 1.7;
  color: var(--rs-muted);
}
</style>
