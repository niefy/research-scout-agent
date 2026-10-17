export type Category = 'stock' | 'industry' | 'macro'
export type Direction = 'bullish' | 'bearish' | 'neutral'
export type FeedScope = 'following' | 'discover'
export type FeedSort = 'smart' | 'time' | 'hot' | 'latest'
export type FeedWindow = '24h' | '72h' | '7d' | '30d' | 'all'

export interface TokenPair {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
}

export interface User {
  id: number
  email: string | null
  phone: string | null
  nickname: string
  role: string
  status: string
  scoring_config: {
    category_weights?: Record<string, number>
    half_life_days?: Record<string, number>
  }
  created_at: string
}

export interface AuthorBrief {
  id: number | null
  name: string
  weight: number
  followed: boolean
}

export interface ReportItem {
  id: number
  channel_id: number
  url: string
  title: string
  summary: string | null
  opinion: string | null
  published_at: string
  source_name: string | null
  author: AuthorBrief | null
  primary_category: Category | null
  categories: Category[]
  stock_codes: string[]
  industry_codes: string[]
  macro_tags: string[]
  keywords: string[]
  score: number | null
  display_score: number | null
  confidence: number | null
  direction: Direction | null
  horizon: string | null
  cluster_id: number | null
  reprint_count: number
  is_reprint: boolean
}

export interface ReportDetail extends ReportItem {
  content: string
  key_points: string[]
  rationale: string | null
  stock_mentions: Array<{
    code: string | null
    name: string
    relevance: number
    sentiment: number
  }>
  industry_mentions: Array<{ code: string | null; name: string; relevance: number }>
  macro_mentions: Array<{ tag: string; relevance: number }>
  analysis_model: string | null
  analyzed_at: string | null
}

export interface FeedResponse {
  items: ReportItem[]
  next_cursor: string | null
  has_more: boolean
  scope: FeedScope
  sort: string
  generated_at: string
}

export interface Author {
  id: number
  canonical_name: string
  author_type: string
  default_weight: number
  status: string
  meta: Record<string, unknown>
  created_at: string
}

export interface AuthorDetail extends Author {
  aliases: string[]
  identities: Array<{
    id: number
    channel_id: number
    external_id: string
    display_name: string | null
    profile_url: string | null
  }>
  follower_count: number
  report_count: number
}

export interface FollowedAuthor {
  author: Author
  weight: number
  notify: boolean
  followed_at: string
}

export interface Security {
  id: number
  code: string
  symbol: string
  name: string
  exchange: string
  industry_code: string | null
  aliases: string[]
}

export interface ScoreBreakdownItem {
  report_id: number
  title: string
  category: Category
  score: number
  confidence: number
  author_weight: number
  category_weight: number
  recency_factor: number
  relevance: number
  effective_weight: number
  published_at: string
}

export interface CategoryScore {
  category: Category
  budget_share: number
  budget_points: number
  article_count: number
  weighted_signal: number
  points: number
  weight_sum: number
  confidence: number
}

export interface StockScore {
  security: Security
  scope: 'all' | 'followed'
  window: string
  report_count: number
  raw_score: number
  final_score: number
  total_points: number
  display_score: number | null
  n_eff: number
  confidence: number
  conclusion: string
  category_scores: CategoryScore[]
  category_weights: Record<string, number>
  half_life_days: Record<string, number>
  max_age_days: number
  breakdown: ScoreBreakdownItem[]
  category_counts: Record<string, number>
  computed_at: string | null
}

export interface WatchlistItem {
  id: number
  security: Security
  note: string | null
  sort_order: number
  score: StockScore | null
  added_at: string
}

export interface StockDetail {
  security: Security
  score: StockScore
  related_reports: ReportItem[]
}

export interface Page<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  has_more: boolean
}

export interface Message {
  message: string
}

export interface Channel {
  id: number
  code: string
  name: string
  adapter_key: string
  enabled: boolean
  config: Record<string, unknown>
  crawl_interval_seconds: number
  last_cursor: Record<string, unknown>
  updated_at: string
}

export interface SystemStats {
  reports_total: number
  reports_analyzed: number
  authors_total: number
  users_total: number
  channels_enabled: number
  llm_calls_today: number
  llm_tokens_today: number
  llm_fallbacks_today: number
}
