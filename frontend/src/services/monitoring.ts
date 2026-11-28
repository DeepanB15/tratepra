import { api, apiPage } from "./api";
import { buildQuery } from "./trends";
import type { MonitorNotification, MonitorPreferences, MonitorSnapshot, MonitoringOverview, MonitoringStatus, TrendEventItem, TrendMonitoring, WatchRow } from "../types";

const J = (body: unknown) => JSON.stringify(body);
export const getOverview = () => api<MonitoringOverview>("/api/monitoring/overview");
export const getStatus = () => api<MonitoringStatus>("/api/monitoring/status");
export const getPreferences = () => api<MonitorPreferences>("/api/monitoring/preferences");
export const savePreferences = (p: Partial<MonitorPreferences>) => api<MonitorPreferences>("/api/monitoring/preferences", { method: "PUT", body: J(p) });
export const listWatchlist = (params: { q?: string; lifecycle?: string; activity?: string; priority?: string; enabled?: boolean; sort?: string; limit?: number; offset?: number } = {}) =>
  apiPage<WatchRow[]>(`/api/monitoring/watchlist${buildQuery(params)}`);
export const follow = (topic_id: string, priority = "normal", user_note = "") => api<WatchRow>("/api/monitoring/watchlist", { method: "POST", body: J({ topic_id, priority, user_note }) });
export const patchWatch = (topicId: string, body: { monitoring_enabled?: boolean; priority?: string; user_note?: string }) =>
  api<WatchRow>(`/api/monitoring/watchlist/${topicId}`, { method: "PATCH", body: J(body) });
export const unfollow = (topicId: string) => api<{ deleted: boolean }>(`/api/monitoring/watchlist/${topicId}`, { method: "DELETE" });
export const getTrendMonitoring = (id: string) => api<TrendMonitoring>(`/api/monitoring/trends/${id}`);
export const getTrendHistory = (id: string) => api<MonitorSnapshot[]>(`/api/monitoring/trends/${id}/history`);
export const listEvents = (params: { event_type?: string; severity?: string; state?: string; topic_id?: string; limit?: number; offset?: number } = {}) =>
  apiPage<TrendEventItem[]>(`/api/monitoring/events${buildQuery(params)}`);
export const getEvent = (id: string) => api<TrendEventItem>(`/api/monitoring/events/${id}`);
export const setEventState = (id: string, state: string) => api<TrendEventItem>(`/api/monitoring/events/${id}`, { method: "PATCH", body: J({ state }) });
export const listNotifications = (params: { status?: string; severity?: string; limit?: number; offset?: number } = {}) =>
  apiPage<MonitorNotification[]>(`/api/monitoring/notifications${buildQuery(params)}`);
export const unreadCount = () => api<{ unread: number; by_severity: Record<string, number> }>("/api/monitoring/notifications/unread-count");
export const patchNotification = (id: string, body: { read?: boolean; dismissed?: boolean }) =>
  api<MonitorNotification>(`/api/monitoring/notifications/${id}`, { method: "PATCH", body: J(body) });
export const markAllRead = () => api<{ marked: number }>("/api/monitoring/notifications/mark-all-read", { method: "POST" });

export const EVENT_LABELS: Record<string, string> = {
  growth_acceleration: "Growth acceleration", growth_slowdown: "Growth slowdown", activity_decline: "Activity decline", lifecycle_transition: "Lifecycle transition",
  new_supporting_evidence: "New evidence", contradictory_evidence: "Possible contradiction", new_related_topic: "New related topic",
  activity_disappearance: "Activity disappeared", activity_spike: "Unusual spike", new_emerging_trend: "New emerging trend", monitoring_failure: "Monitoring failure",
};
