import { api, apiPage } from "./api";
import type { DiscoveryOverview, RunDetail, RunSummary, TrendDetail, TrendHistoryPoint, TrendSummary } from "../types";

export interface TrendQuery {
  q?: string;
  lifecycle?: string;
  activity_state?: string;
  min_sources?: number;
  min_score?: number;
  max_age_days?: number;
  momentum?: string;
  is_new?: boolean;
  score_withheld?: boolean;
  sort?: string;
  order?: "asc" | "desc";
  limit?: number;
  offset?: number;
}

export function buildQuery(params: object): string {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => v !== undefined && v !== null && v !== "" && v !== 0 && qs.set(k, String(v)));
  const s = qs.toString();
  return s ? `?${s}` : "";
}

export const searchTrends = (params: TrendQuery = {}) => apiPage<TrendSummary[]>(`/api/trends${buildQuery(params)}`);
export const listTrends = async (params: TrendQuery = {}) => (await searchTrends(params)).data;
export const getTrend = (id: string) => api<TrendDetail>(`/api/trends/${id}`);
export const getTrendHistory = (id: string) => api<TrendHistoryPoint[]>(`/api/trends/${id}/history`);
export const getDiscoveryOverview = () => api<DiscoveryOverview>("/api/trends/overview");
export const listRuns = (params: { status?: string; limit?: number; offset?: number } = {}) => apiPage<RunSummary[]>(`/api/trends/runs${buildQuery(params)}`);
export const getRun = (id: string) => api<RunDetail>(`/api/trends/runs/${id}`);
