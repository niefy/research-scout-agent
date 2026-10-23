<script setup lang="ts">
import { computed } from 'vue'

import type { Evidence } from '@/api/types'

const props = withDefaults(
  defineProps<{
    evidence: Evidence
    counts?: boolean
  }>(),
  { counts: false },
)

const tone = computed(() => {
  if (props.evidence.level === 'direct') return 'chip--stock'
  if (props.evidence.level === 'industry') return 'chip--industry'
  if (props.evidence.level === 'macro') return 'chip--macro'
  return 'chip--outline'
})

const countText = computed(() => {
  const { stock_count, industry_count, macro_count } = props.evidence
  return `个股 ${stock_count} · 行业 ${industry_count} · 宏观 ${macro_count}`
})
</script>

<template>
  <span class="evidence-badge">
    <span class="chip" :class="tone">{{ evidence.label }}</span>
    <span v-if="counts" class="evidence-badge__counts">{{ countText }}</span>
  </span>
</template>

<style scoped>
.evidence-badge {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
}

.evidence-badge__counts {
  font-size: 10px;
  color: var(--rs-muted);
  white-space: nowrap;
}
</style>
