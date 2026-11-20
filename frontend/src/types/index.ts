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

export interface TrendSummary {
  topic_id: string;
  topic_name: string;
  trend_score: number | null;
  lifecycle: string | null;
  growth: number | null;
  coverage: Record<string, any>;
  sparkline: number[];
  last_updated: string | null;
}

export interface TrendDetail {
  topic_id: string;
  topic_name: string;
  trend_score: number | null;
  lifecycle: string | null;
  signals: Record<string, number | null>;
  coverage: Record<string, any>;
  explanation: TrendExplanation;
  source_distribution: Record<string, number>;
  weekly_volumes: number[];
  previous_score: number | null;
  topic_size: number | null;
  related_topics: string[];
  representative_documents: { id: string; title: string; url: string | null; source: string; published_at: string | null }[];
  terms: string[];
  last_updated: string | null;
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
}

export interface TrendHistoryPoint {
  window_start: string;
  window_end: string;
  document_volume: number;
  growth: number | null;
  trend_score: number | null;
  lifecycle: string | null;
  created_at: string;
  volumes: number[];
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
