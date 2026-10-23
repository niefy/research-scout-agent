<script setup lang="ts">
import { computed } from 'vue'

import type { StockHistoryPoint } from '@/api/types'

const props = withDefaults(
  defineProps<{
    points: StockHistoryPoint[]
    height?: number
  }>(),
  { height: 64 },
)

const WIDTH = 300
const PAD_X = 8
const PAD_Y = 8

const values = computed(() => props.points.map((point) => point.total_points))

const bounds = computed(() => {
  const list = values.value
  if (!list.length) return { min: 0, max: 100 }
  let min = Math.min(...list)
  let max = Math.max(...list)
  if (max - min < 1) {
    min = Math.max(0, min - 0.5)
    max = Math.min(100, max + 0.5)
  }
  return { min, max }
})

const coordinates = computed(() => {
  const list = values.value
  if (!list.length) return []
  const { min, max } = bounds.value
  const span = Math.max(0.0001, max - min)
  const usableWidth = WIDTH - PAD_X * 2
  const usableHeight = props.height - PAD_Y * 2
  return list.map((value, index) => ({
    x: list.length === 1 ? WIDTH / 2 : PAD_X + (index / (list.length - 1)) * usableWidth,
    y: PAD_Y + (1 - (value - min) / span) * usableHeight,
    value,
    point: props.points[index],
  }))
})

const linePath = computed(() => {
  const list = coordinates.value
  if (!list.length) return ''
  return list
    .map((item, index) => `${index === 0 ? 'M' : 'L'} ${item.x.toFixed(2)} ${item.y.toFixed(2)}`)
    .join(' ')
})

const areaPath = computed(() => {
  const list = coordinates.value
  if (!list.length) return ''
  const baseline = props.height - PAD_Y
  const first = list[0]
  const last = list[list.length - 1]
  return `${linePath.value} L ${last.x.toFixed(2)} ${baseline} L ${first.x.toFixed(2)} ${baseline} Z`
})

const last = computed(() => coordinates.value[coordinates.value.length - 1] ?? null)

const summary = computed(() => {
  const list = values.value
  if (!list.length) return '暂无评分快照'
  return `评分趋势，共 ${list.length} 个快照，从 ${list[0].toFixed(1)} 分到 ${list[list.length - 1].toFixed(1)} 分`
})

function pointLabel(point: StockHistoryPoint): string {
  const date = new Date(point.computed_at)
  const stamp = Number.isNaN(date.getTime())
    ? point.computed_at
    : `${date.getMonth() + 1}月${date.getDate()}日`
  return `${stamp} · ${point.total_points.toFixed(1)} 分 · ${point.report_count} 篇`
}
</script>

<template>
  <div class="sparkline">
    <svg
      v-if="points.length"
      :viewBox="`0 0 ${WIDTH} ${height}`"
      preserveAspectRatio="none"
      role="img"
      :aria-label="summary"
      class="sparkline__svg"
      :style="{ height: `${height}px` }"
    >
      <path :d="areaPath" class="sparkline__area" />
      <path :d="linePath" class="sparkline__line" />
      <g v-for="(item, index) in coordinates" :key="index">
        <circle
          v-if="index === coordinates.length - 1"
          :cx="item.x"
          :cy="item.y"
          r="4.5"
          class="sparkline__marker"
        >
          <title>{{ pointLabel(item.point) }}</title>
        </circle>
        <circle :cx="item.x" :cy="item.y" r="10" class="sparkline__hit">
          <title>{{ pointLabel(item.point) }}</title>
        </circle>
      </g>
    </svg>
    <p v-else class="sparkline__empty">评分快照每日生成，积累后显示变化趋势。</p>

    <div v-if="last" class="sparkline__foot">
      <span class="sparkline__latest mono">最新 {{ last.value.toFixed(1) }}</span>
      <span class="sparkline__range mono">
        范围 {{ bounds.min.toFixed(1) }} – {{ bounds.max.toFixed(1) }}
      </span>
    </div>
  </div>
</template>

<style scoped>
.sparkline {
  width: 100%;
}

.sparkline__svg {
  display: block;
  width: 100%;
  overflow: visible;
}

.sparkline__area {
  fill: rgba(194, 65, 12, 0.08);
}

.sparkline__line {
  fill: none;
  stroke: var(--rs-accent);
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.sparkline__marker {
  fill: var(--rs-accent);
  stroke: #fff;
  stroke-width: 2;
}

.sparkline__hit {
  fill: transparent;
  cursor: help;
}

.sparkline__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: 6px;
  font-size: 10px;
  color: var(--rs-muted);
}

.sparkline__latest {
  font-weight: 700;
  color: var(--rs-ink-soft);
}

.sparkline__empty {
  margin: 0;
  padding: 12px 0;
  font-size: 10.5px;
  color: var(--rs-muted);
}
</style>
