import type { Category, Direction } from '@/api/types'

const CATEGORY_LABELS: Record<Category, string> = {
  stock: '个股',
  industry: '行业',
  macro: '宏观',
}

export function categoryLabel(category: string | null | undefined): string {
  if (!category) return '未分类'
  return CATEGORY_LABELS[category as Category] ?? category
}

export function directionLabel(direction: Direction | null | undefined): string {
  if (direction === 'bullish') return '偏多'
  if (direction === 'bearish') return '偏空'
  return '中性'
}

export function directionClass(score: number | null | undefined): string {
  if (score === null || score === undefined) return 'neutral'
  if (score >= 0.12) return 'up'
  if (score <= -0.12) return 'down'
  return 'neutral'
}

export function formatTime(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  const diffMs = Date.now() - date.getTime()
  const diffMin = Math.floor(diffMs / 60000)
  if (diffMin < 1) return '刚刚'
  if (diffMin < 60) return `${diffMin}分钟前`
  const diffHour = Math.floor(diffMin / 60)
  if (diffHour < 24) return `${diffHour}小时前`
  const diffDay = Math.floor(diffHour / 24)
  if (diffDay < 7) return `${diffDay}天前`
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${month}-${day}`
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(
    date.getDate(),
  ).padStart(2, '0')} ${String(date.getHours()).padStart(2, '0')}:${String(
    date.getMinutes(),
  ).padStart(2, '0')}`
}

export function formatWindow(value: string): string {
  const map: Record<string, string> = {
    '7d': '近7天',
    '30d': '近30天',
    '90d': '近3月',
    all: '近3月',
    '24h': '24小时',
    '72h': '72小时',
  }
  return map[value] ?? value
}

export function truncate(value: string, limit: number): string {
  return value.length > limit ? `${value.slice(0, limit)}…` : value
}

export function scoreTone(score: number | null | undefined): string {
  if (score === null || score === undefined) return 'neutral'
  if (score >= 55) return 'up'
  if (score <= 45) return 'down'
  return 'neutral'
}
