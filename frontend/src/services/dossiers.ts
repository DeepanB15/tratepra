import { api, apiPage } from "./api";
import { buildQuery } from "./trends";
import type { Dossier, DossierClaim, DossierEvidenceItem, DossierListItem } from "../types";

export const createDossier = (body: { topic_id?: string; query?: string; time_range?: string; sources?: string[] }) =>
  api<Dossier>("/api/research/dossiers", { method: "POST", body: JSON.stringify(body) });
export const getDossier = (id: string) => api<Dossier>(`/api/research/dossiers/${id}`);
export const refreshDossier = (id: string) => api<Dossier>(`/api/research/dossiers/${id}/refresh`, { method: "POST" });
export const listDossiers = (params: { topic_id?: string; limit?: number; offset?: number } = {}) =>
  apiPage<DossierListItem[]>(`/api/research/dossiers${buildQuery(params)}`);
export const listDossierEvidence = (id: string, params: { role?: string; publisher?: string; date_from?: string; date_to?: string; limit?: number; offset?: number } = {}) =>
  apiPage<DossierEvidenceItem[]>(`/api/research/dossiers/${id}/evidence${buildQuery(params)}`);
export const listDossierClaims = (id: string, params: { status?: string; limit?: number; offset?: number } = {}) =>
  apiPage<DossierClaim[]>(`/api/research/dossiers/${id}/claims${buildQuery(params)}`);
