<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    value: number | null | undefined
    size?: number
    stroke?: number
    caption?: string
  }>(),
  { size: 56, stroke: 4.5, caption: '分' },
)

const radius = computed(() => (props.size - props.stroke) / 2)
const circumference = computed(() => 2 * Math.PI * radius.value)
const percent = computed(() => Math.max(0, Math.min(100, props.value ?? 50)))
const dashOffset = computed(() => circumference.value * (1 - percent.value / 100))
const tone = computed(() => {
  if (props.value === null || props.value === undefined) return 'neutral'
  if (props.value >= 55) return 'up'
  if (props.value <= 45) return 'down'
  return 'neutral'
})
const color = computed(() => {
  if (tone.value === 'up') return '#d92d20'
  if (tone.value === 'down') return '#0b8f63'
  return '#94a3b8'
})
const display = computed(() =>
  props.value === null || props.value === undefined ? '—' : props.value.toFixed(1),
)
</script>

<template>
  <div class="score-ring" :style="{ width: `${size}px`, height: `${size}px` }">
    <svg :width="size" :height="size" :viewBox="`0 0 ${size} ${size}`">
      <circle
        :cx="size / 2"
        :cy="size / 2"
        :r="radius"
        fill="none"
        stroke="#e9eef4"
        :stroke-width="stroke"
      />
      <circle
        :cx="size / 2"
        :cy="size / 2"
        :r="radius"
        fill="none"
        :stroke="color"
        :stroke-width="stroke"
        stroke-linecap="round"
        :stroke-dasharray="circumference"
        :stroke-dashoffset="dashOffset"
        :transform="`rotate(-90 ${size / 2} ${size / 2})`"
        class="score-ring__arc"
      />
    </svg>
    <div class="score-ring__center">
      <span class="score-ring__value mono" :class="tone">{{ display }}</span>
      <span v-if="caption" class="score-ring__caption">{{ caption }}</span>
    </div>
  </div>
</template>

<style scoped>
.score-ring {
  position: relative;
  flex: none;
}

.score-ring__arc {
  transition: stroke-dashoffset 0.5s ease;
}

.score-ring__center {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  line-height: 1;
}

.score-ring__value {
  font-size: 15px;
  font-weight: 700;
}

.score-ring__caption {
  margin-top: 2px;
  font-size: 8px;
  color: var(--rs-muted);
  letter-spacing: 0.08em;
}
</style>
