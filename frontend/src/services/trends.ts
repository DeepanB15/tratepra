import { api } from "./api";
import type { TrendDetail, TrendHistoryPoint, TrendSummary } from "../types";

export const listTrends = (params: { lifecycle?: string; q?: string; min_sources?: number } = {}) => {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => v !== undefined && v !== "" && qs.set(k, String(v)));
  const s = qs.toString();
  return api<TrendSummary[]>(`/api/trends${s ? `?${s}` : ""}`);
};
export const getTrend = (id: string) => api<TrendDetail>(`/api/trends/${id}`);
export const getTrendHistory = (id: string) => api<TrendHistoryPoint[]>(`/api/trends/${id}/history`);
