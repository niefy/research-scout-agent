<script setup lang="ts">
import { computed } from 'vue'

import { formatTime } from '@/utils/format'

const props = defineProps<{
  value: number | null | undefined
  since?: string | null
  prefix?: string
}>()

const tone = computed(() => {
  if (props.value === null || props.value === undefined) return 'neutral'
  if (props.value > 0.04) return 'up'
  if (props.value < -0.04) return 'down'
  return 'neutral'
})

const text = computed(() => {
  if (props.value === null || props.value === undefined) return '—'
  const sign = props.value > 0 ? '+' : ''
  return `${sign}${props.value.toFixed(1)}`
})

const sinceText = computed(() => (props.since ? `较 ${formatTime(props.since)}` : '较上次'))
</script>

<template>
  <span class="score-delta" :class="tone">
    <span v-if="prefix" class="score-delta__prefix">{{ prefix }}</span>
    <span class="score-delta__value mono">{{ text }}</span>
    <span class="score-delta__since">{{ sinceText }}</span>
  </span>
</template>

<style scoped>
.score-delta {
  display: inline-flex;
  align-items: baseline;
  gap: 4px;
  font-size: 11px;
  font-weight: 700;
}

.score-delta__prefix {
  font-size: 10px;
  font-weight: 500;
  color: var(--rs-muted);
}

.score-delta__value {
  font-size: 12px;
}

.score-delta__since {
  font-size: 9.5px;
  font-weight: 500;
  color: var(--rs-muted);
}
</style>
