# Phase 2 Architecture — Evidence Intelligence & Research Dossiers

## Pipeline
```
question | topic_id ──► process_query (keywords, phrases, entities, intent, time range, topic ids; original preserved)
   ──► hybrid retrieve (pgvector cosine + FTS ts_rank_cd + topic member docs) ──► rank (S,K,F,Q) ──► select_evidence_explained
   ──► build_excerpt (article sentences if real article text, else RSS description)  ◄── same text is shown to the LLM and used to verify
   ──► synthesize (1 Ollama call, extractive fallback)  [no DB connection held]
   ──► build_dossier (pure): claims → verify (lexical) → roles → sections A–G → evidence quality
   ──► persist in ONE transaction (replace evidence+claims+content, generation+1)
```
## Article evidence states (`documents.article_status`)
`full` · `partial` (short or cut at the 20k cap) · `rss_only` (never fetched) · `unavailable` · `too_short` · `failed` (fetch failure, reason stored). Stored per document: original/canonical URL, title/description, published/collected dates, `article_method`, `article_extracted_at`, `article_text_hash`, `article_failure_reason`, `article_text`. The indexed/embedded `normalized_text` = RSS text + article text (`compose_normalized_text`). Changing it changes the embedding `text_hash`, which marks the embedding stale (`stale_embedding_count`); `embed_pending` re-embeds exactly those rows. `refresh_articles` re-fetches retryable documents (max 5 per dossier refresh) through the unchanged SSRF-safe fetcher, with no DB transaction open during I/O.

## The article-text defect and its fix
Before: article text reached FTS/keyword ranking but the LLM saw only `description[:500]` and citations were verified against title+description. After: `build_excerpt` selects up to 700 chars of query-relevant article sentences; `build_context` shows them and `research_service`/the dossier engine verify against the very same excerpt. RSS-only items keep the old behaviour and are labelled "feed summary". Proven by `test_article_text_is_used_for_excerpt_and_citation_verification`.

## Claim statuses (deterministic; no LLM per claim)
| status | rule |
|---|---|
| supported | valid citation (exists, has URL) and ≥ 60% of the claim's content words appear in the cited excerpt (`dossier_support_overlap`) |
| partially_supported | valid citation, overlap between 20% and 60% |
| contradicted | evidence sentence covering ≥ 50% of the claim's content words with opposite negation/decline polarity |
| unverified | uncited, invalid citation, or overlap < 20% |
| insufficient_evidence | no evidence retrieved, or cited excerpt < 40 chars |

**Limitations (shown in the product):** overlap is lexical, not entailment; a claim can reuse the right words with the wrong meaning; paraphrases can fail; contradiction detection needs explicit cues and will miss most contradictions. When the LLM is unavailable the overview is an extractive list and **no claims are created** (verifying a title against itself would be circular).

## Evidence quality (no single confidence number)
Four separate dimensions with printed rules (`evidence_quality.RULES`): coverage (unique docs after de-duplication), source diversity (publishers + largest share), temporal coverage (distinct days and window fraction), claim support. Labels: Strong / Moderate / Limited / Insufficient evidence coverage. Duplicate/syndicated repeats are collapsed before counting. The response also names the limiting dimension.

## Persistence (migration 004, additive + idempotent)
`documents` +6 columns; `research_dossiers` (unique `dossier_key`, status check, content columns replaced only on success, `versions` JSON for reproducibility), `dossier_evidence` (FK documents, unique per doc, role/excerpt/publisher snapshot), `dossier_claims`, `claim_evidence`. Evidence rows reference documents; article content is not copied.

## Safety and concurrency
- Duplicate creation: insert-on-conflict on `dossier_key`; second POST returns the existing dossier (200).
- One generation at a time: `claim_run` is a conditional UPDATE; a `running` row older than `dossier_running_timeout_minutes` is reclaimable (crash recovery). Refresh while running → 409.
- Failure: sanitized error stored, status `failed`, previous content, evidence and `generation` untouched.
- Background execution: bounded `ThreadPoolExecutor` (`dossier_workers`), `dossier_inline_execution` for tests, `shutdown_workers()` on app shutdown. No queue infrastructure. A single backend process is assumed; the conditional UPDATE keeps multiple processes from double-running a dossier.
- Bounds: retrieval limit 80, evidence ≤ 12, excerpts ≤ 700 chars, Ollama timeout configurable (`OLLAMA_TIMEOUT_SECONDS`).

## API
`POST /api/research/dossiers` (202 started / 200 existing) · `GET /api/research/dossiers` · `GET /{id}` · `GET /{id}/evidence?role&publisher&date_from&date_to&limit&offset` · `GET /{id}/claims?status&section` · `POST /{id}/refresh` (409 if running). Totals in `X-Total-Count`. `/api/research/search|history|{id}` are unchanged (their evidence now uses excerpts).

## Frontend
"Investigate this trend" (TrendDetail → creates dossier from `topic_id`), `/dossiers/:id` (header, polling status, 7 sections, quality cards, Evidence Explorer with role/publisher/date filters, Claim view with a standing limitation notice), Research page: history, recent dossiers, insufficient-evidence state, "Create dossier from this question".
