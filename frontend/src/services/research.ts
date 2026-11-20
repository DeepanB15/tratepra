import { api } from "./api";
import type { CollectionLogEntry, HistoryItem, Overview, ResearchResult, SavedItem, SourceInfo } from "../types";

export const searchResearch = (query: string, sources: string[], time_range: string) =>
  api<ResearchResult>("/api/research/search", {
    method: "POST",
    body: JSON.stringify({ query, sources, time_range }),
  });

export const getResearch = (id: string) => api<ResearchResult>(`/api/research/${id}`);
export const getHistory = () => api<HistoryItem[]>("/api/research/history");
export const getSources = () => api<SourceInfo[]>("/api/sources");
export const getSourceLogs = (limit = 50) => api<CollectionLogEntry[]>(`/api/sources/logs?limit=${limit}`);
export const getOverview = () => api<Overview>("/api/dashboard/overview");

export const listSaved = () => api<SavedItem[]>("/api/saved");
export const saveItem = (item_type: "research" | "trend", item_id: string, title = "") =>
  api<SavedItem>("/api/saved", { method: "POST", body: JSON.stringify({ item_type, item_id, title }) });
export const removeSaved = (id: string) => api<{ deleted: boolean }>(`/api/saved/${id}`, { method: "DELETE" });
