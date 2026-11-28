export interface SourceInfo {
  key: string;
  name: string;
  available: boolean;
  reason: string | null;
  last_status: string | null;
  last_error: string | null;
  last_run_at: string | null;
  state: SourceState;
  document_count: number;
  latest_document_at: string | null;
  last_fetched: number | null;
  last_accepted: number | null;
  last_duration_ms: number | null;
}

/** unavailable = not configured; configured = credentials present but never verified by a run;
 *  operational = last run succeeded; failing = last run failed. */
export type SourceState = "unavailable" | "configured" | "operational" | "failing";

export interface CollectionLogEntry {
  run_id: string;
  source: string;
  query: string;
  status: string;
  fetched: number;
  accepted: number;
  duplicates: number;
  out_of_window: number;
  undated: number;
  rejected: number;
  error: string | null;
  duration_ms: number | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface EvidenceItem {
  document_id: string;
  title: string;
  url: string | null;
  source: string;
  published_at: string | null;
  relevance: number | null;
  cited: boolean;
}

export interface SourceStatus {
  source: string;
  status: string;
  fetched?: number;
  inserted?: number;
  error: string | null;
}

export interface ResearchResult {
  research_id: string;
  query: string;
  answer: string;
  key_findings: string[];
  sources_used: string[];
  source_status: Record<string, SourceStatus>;
  source_distribution: Record<string, number>;
  evidence: EvidenceItem[];
  related_topics: string[];
  model: string;
  degraded: boolean;
  transparency: Transparency;
  unverified_claims: { text: string; reason: string; section: string }[];
  execution_ms: number;
  created_at: string;
}

export interface Transparency {
  sources_searched?: number;
  sources_failed?: Record<string, string | null>;
  results_collected?: number;
  out_of_window?: number;
  rejected?: number;
  duplicates_removed?: number;
  accepted?: number;
  candidates_retrieved?: number;
  evidence_selected?: number;
  claims?: { claims_total?: number; claims_verified?: number; claims_unverified?: number };
  timing_ms?: Record<string, number>;
}

export interface HistoryItem {
  research_id: string;
  query: string;
  sources: string[];
  created_at: string;
}

export type Lifecycle = "emerging" | "growing" | "peaking" | "declining";
export type ActivityState = "active" | "stale" | "inactive";
export type MomentumDirection = "accelerating" | "decelerating" | "steady" | "unknown";

export interface TrendSummary {
  topic_id: string;
  topic_name: string;
  trend_score: number | null;
  score_withheld: boolean;
  score_coverage: number | null;
  lifecycle: Lifecycle | null;
  activity_state: ActivityState;
  growth: number | null;
  momentum_direction: MomentumDirection | null;
  momentum_pp: number | null;
  document_volume: number | null;
  supporting_documents: number | null;
  source_count: number;
  source_distribution: Record<string, number>;
  coverage: Record<string, any>;
  sparkline: number[];
  is_new: boolean;
  needs_review: boolean;
  explanation: string;
  last_updated: string | null;
  last_observed_at: string | null;
  first_seen_at: string | null;
}

export interface RunInfo {
  run_id: string;
  status: string;
  completed_at: string | null;
  model_version: string;
  formula_version: string;
  documents_processed: number;
}

export interface TrendDetail {
  topic_id: string;
  topic_name: string;
  terms: string[];
  trend_score: number | null;
  score_withheld: boolean;
  lifecycle: Lifecycle | null;
  activity_state: ActivityState;
  signals: Record<string, number | null>;
  coverage: Record<string, any>;
  explanation: TrendExplanation;
  growth_pct: number | null;
  growth_flag: string | null;
  momentum_direction: MomentumDirection | null;
  momentum_pp: number | null;
  document_volume: number | null;
  source_distribution: Record<string, number>;
  weekly_volumes: number[];
  previous_score: number | null;
  topic_size: number | null;
  related_topics: string[];
  related_topic_details: { topic_id: string; name: string; similarity: number }[];
  representative_documents: { id: string; title: string; url: string | null; source: string; published_at: string | null }[];
  needs_review: boolean;
  review_reasons: string[];
  name_confidence: number | null;
  first_seen_at: string | null;
  last_observed_at: string | null;
  last_updated: string | null;
  model_version: string | null;
  formula_version: string | null;
  last_run: RunInfo | null;
  identity: Record<string, any> | null;
}

export interface TrendExplanation {
  summary?: string;
  contributions?: {
    signal: string;
    label: string;
    value: number | null;
    weight: number;
    points: number | null;
    reason_missing: string | null;
  }[];
  missing?: { signal: string; label: string; reason: string }[];
  acceleration?: { label: string; text: string };
}

export interface TrendHistoryPoint {
  window_start: string;
  window_end: string;
  observed_at: string | null;
  document_volume: number;
  growth: number | null;
  momentum: number | null;
  momentum_direction: string | null;
  trend_score: number | null;
  score_withheld: boolean;
  lifecycle: string | null;
  run_id: string | null;
  run_completed_at: string | null;
  legacy: boolean;
  created_at: string;
  volumes: number[];
}

export interface RunSummary {
  run_id: string;
  run_key: string;
  status: "pending" | "running" | "completed" | "failed";
  started_at: string | null;
  completed_at: string | null;
  window_end: string | null;
  documents_available: number;
  documents_processed: number;
  documents_rejected: number;
  noise_documents: number;
  noise_percentage: number | null;
  topics_discovered: number;
  topics_created: number;
  topics_matched: number;
  model_version: string;
  formula_version: string;
  error_message: string | null;
  attempts: number | null;
  topic_quality: Record<string, any> | null;
}

export interface RunDetail extends RunSummary {
  configuration: Record<string, any>;
  rejection: Record<string, any>;
  input: Record<string, any> | null;
  identity: Record<string, any> | null;
}

export interface DiscoveryOverview {
  total_active_trends: number;
  emerging_trends: number;
  rising_trends: number;
  peaking_trends: number;
  declining_trends: number;
  accelerating_trends: number;
  new_trends: number;
  withheld_score_trends: number;
  needs_review_trends: number;
  stale_trends: number;
  inactive_trends: number;
  activity_state_counts: Record<string, number>;
  latest_successful_run: RunDetail | null;
  latest_run: RunSummary | null;
  latest_run_status: string | null;
  documents_analyzed: number | null;
  topic_model_diagnostics: Record<string, any> | null;
  data_freshness: { latest_successful_analysis_at: string | null; age_hours: number | null; overdue: boolean; overdue_after_days: number };
  generated_at: string;
}

export interface Overview {
  research_query_count: number;
  emerging_trend_count: number;
  sources_analyzed: number;
  document_count: number;
  average_trend_score: number | null;
  active_topic_count: number;
  lifecycle_distribution: Record<string, number>;
  sources: SourceInfo[];
  recent_collections: CollectionLogEntry[];
  trending: TrendSummary[];
  recent_activity: { research_id: string; query: string; created_at: string; sources: string[] }[];
}

export interface SavedItem {
  id: string;
  item_type: "research" | "trend";
  item_id: string;
  title: string;
  created_at: string;
}

// ---- Phase 2: research dossiers ----
export type DossierStatus = "pending" | "running" | "completed" | "failed";
export type EvidenceRole = "supporting" | "contradictory" | "context";
export type ClaimStatus = "supported" | "partially_supported" | "contradicted" | "unverified" | "insufficient_evidence";
export interface QualityDimension {
  label: "strong" | "moderate" | "limited" | "insufficient";
  text: string;
  explanation: string;
  [k: string]: unknown;
}
export interface Dossier {
  id: string;
  topic_id: string | null;
  title: string;
  query: string;
  time_range: string;
  sources: string[];
  processing: { status: DossierStatus; error: string | null; started_at: string | null; completed_at: string | null; interrupted: boolean; has_content: boolean };
  generated_at: string | null;
  generation: number;
  model: string;
  sections: {
    overview?: { text: string; degraded: boolean; claims_total: number; claims_flagged: number; note: string };
    key_developments?: { items: { date: string | null; title: string; publisher: string; document_id: string; citation: number; summary: string; article_status: string }[] };
    supporting_evidence?: { items: DossierEvidenceItem[] };
    contradictory_evidence?: { items: DossierEvidenceItem[]; text: string | null; method: string };
    key_entities?: { items: { name: string; origin: string; documents: number; publishers: number }[]; method: string };
    evidence_gaps?: { items: { code: string; text: string; severity: string }[] };
    research_questions?: { items: string[]; note: string };
  };
  evidence_quality: {
    dimensions?: Record<string, QualityDimension>;
    summary?: string;
    rules?: Record<string, string>;
    note?: string;
  };
  diagnostics: Record<string, unknown>;
  versions: Record<string, unknown>;
  evidence_count: number;
  claim_count: number;
  limitations: string[];
  created?: boolean;
}
export interface DossierEvidenceItem {
  id: string;
  document_id: string;
  rank: number;
  role: EvidenceRole;
  role_reason: string;
  relevance: number;
  title: string;
  url: string | null;
  publisher: string;
  source: string;
  published_at: string | null;
  excerpt: string;
  excerpt_basis: "article" | "rss";
  article_status: string;
}
export interface DossierClaim {
  id: string;
  claim_no: number;
  section: string;
  text: string;
  claim_type: string;
  status: ClaimStatus;
  explanation: string;
  overlap: number | null;
  source_coverage: number;
  supporting_evidence_ids: string[];
  contradictory_evidence_ids: string[];
}
export interface DossierListItem {
  id: string;
  topic_id: string | null;
  title: string;
  status: DossierStatus;
  generated_at: string | null;
  time_range: string;
}
