export type Category = 'stock' | 'industry' | 'macro'
export type Relation = 'stock' | 'industry' | 'macro'
export type ScoreScope = 'personal' | 'hybrid' | 'all'
export type EvidenceLevel = 'direct' | 'industry' | 'macro' | 'none'
export type RelationReason =
  | 'direct_mention'
  | 'stock_code_fallback'
  | 'industry_code'
  | 'macro'
export type Direction = 'bullish' | 'bearish' | 'neutral'
export type FeedScope = 'following' | 'discover'
export type FeedSort = 'smart' | 'time' | 'hot' | 'latest'
export type FeedWindow = '24h' | '72h' | '7d' | '30d' | 'all'
export type StockWindow = '7d' | '30d' | '90d'

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
    relation_weights?: Record<string, number>
    category_weights?: Record<string, number>
    half_life_days?: Record<string, number>
    default_scope?: ScoreScope
  }
  digest_email_enabled: boolean
  created_at: string
}

export interface AuthorBrief {
  id: number | null
  name: string
  weight: number
  followed: boolean
  is_curated: boolean
  source_layer: string | null
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
  relation?: Relation | null
  relation_reason?: RelationReason | null
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
  is_curated: boolean
  curated_rank: number
  crawl_enabled: boolean
  quality_score: number
  sector_tags: string[]
  last_crawled_at: string | null
  crawl_status: string
  crawl_error: string | null
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

export interface RecommendedAuthor {
  id: number
  canonical_name: string
  author_type: string
  quality_score: number
  sector_tags: string[]
  curated_rank: number
  last_crawled_at: string | null
  follower_count: number
}

export interface AuthorImportResult {
  author: Author
  followed: boolean
  created: boolean
  backfill_scheduled: boolean
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

export interface Evidence {
  level: EvidenceLevel
  label: string
  stock_count: number
  industry_count: number
  macro_count: number
  distinct_authors: number
  coverage: Record<string, boolean>
  is_macro_only: boolean
  is_insufficient: boolean
}

export interface ScoreBreakdownItem {
  report_id: number
  title: string
  relation: Relation
  relation_reason: RelationReason
  score: number
  confidence: number
  author_weight: number
  relation_weight: number
  recency_factor: number
  relevance: number
  effective_weight: number
  published_at: string
  author_name: string | null
  source_name: string | null
}

export interface RelationScore {
  relation: Relation
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
  scope: ScoreScope
  window: string
  report_count: number
  raw_score: number
  final_score: number
  total_points: number
  display_score: number | null
  display_label: string
  n_eff: number
  confidence: number
  conclusion: string
  evidence: Evidence
  relation_scores: RelationScore[]
  relation_counts: Record<string, number>
  relation_weights: Record<string, number>
  half_life_days: Record<string, number>
  max_age_days: number
  breakdown: ScoreBreakdownItem[]
  previous_total_points: number | null
  score_delta: number | null
  delta_since: string | null
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

export interface StockHistoryPoint {
  computed_at: string
  total_points: number
  display_score: number | null
  evidence_level: EvidenceLevel
  report_count: number
  relation_counts: Record<string, number>
}

export interface StockHistory {
  security: Security
  scope: ScoreScope
  window: string
  points: StockHistoryPoint[]
  deltas: Record<string, number | null>
}

export interface FeedbackResult {
  message: string
  security_code: string
  report_id: number
  excluded: boolean
}

export interface DigestWatchlistChange {
  security: Security
  display_score: number | null
  display_label: string
  evidence: Evidence
  relation_counts: Record<string, number>
  report_count: number
  previous_total_points: number | null
  score_delta: number | null
  delta_since: string | null
  evidence_gaps: string[]
}

export interface DigestEvidenceGap {
  security: Security
  gaps: string[]
  evidence_level: EvidenceLevel
}

export interface DigestResponse {
  date: string
  generated_at: string
  user: {
    id: number
    nickname: string
    email: string | null
  }
  scope: ScoreScope
  window: string
  followed_updates: ReportItem[]
  watchlist_changes: DigestWatchlistChange[]
  evidence_gaps: DigestEvidenceGap[]
  recommended_authors: RecommendedAuthor[]
  has_content: boolean
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
