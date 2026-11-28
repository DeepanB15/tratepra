# Phase 1 Architecture

Modular monolith unchanged. No new services, dependencies or providers were added to the runtime.

## Pipeline
```
documents + stored embeddings
  → load window (anchor = start of next UTC day, lookback = window_days × n_windows)
  → validate (reasons recorded)            preprocessor.prepare
  → run key = SHA-256(doc fingerprint, window_end, full configuration)
  → claim TrendRun (idempotency / concurrency)          trend_run_service._claim_run
  → BERTopic (existing pipeline)                          topic_model.fit_topics
  → naming + identity + signals + score + lifecycle       topic_naming / topic_identity / trend_score
  → ONE transaction: topics, memberships, observations, run=completed
  → read side derives activity state                       trend_service + freshness
```

## Idempotency (`run_key`)
Key = hash of: eligible documents `(id, content_hash, embedding text_hash, published_at)`, window end, and the **entire** configuration (BERTopic/UMAP/HDBSCAN/vectorizer parameters, window sizes, embedding model + dimension, match thresholds, signal weights, lifecycle thresholds, formula version). Window end is the start of the next UTC day, so same-day reruns over unchanged data are identical while a later day (genuinely different temporal state) is a new run.
- completed key → returns the stored run (`status: "unchanged"`), writes nothing
- running key (not timed out) → `already_running`; timed out (`trend_running_timeout_minutes`) or failed → retried on the same row (`attempts` incremented)
- race on insert → unique constraint; loser re-reads and reports
- DB: `uq_trend_runs_run_key`, status CHECK, partial unique `(topic_id, run_id)` on observations.
Limitation: an identical completed key returns its original result even if stored topics changed in between (documented trade-off).

## Failure safety
All topic/observation/membership writes and the `completed` mark are a single commit. On any exception: rollback, then a separate commit records `failed` + a **sanitized** error (credentials/URLs scrubbed). `Topic.last_observed_at` moves only on completion, so failures never age topics.

## Validation (Stage 2.1)
Rejections with counts and ≤5 sample ids per reason: empty text, too short, non-English heuristic, duplicate content, invalid embedding (NaN/inf/zero/ndim), dimension mismatch, embedding-model mismatch. Window accounting also records non-text, undated, future-dated and without-embedding documents. Invariant tested: `input = kept + rejected`.

## Topic diagnostics (Stage 2.3)
Persisted in `trend_runs.diagnostics.topic_quality`: eligible/clustered/noise counts, noise %, topic count, size min/mean/median/max/histogram, per-source distribution (incl. per-source noise), language note, flags (`overly_broad` > `topic_broad_share`, `no_representation`, `high_noise`, `single_topic`), per-topic naming/cohesion rows. **Cohesion** = mean cosine of members to centroid — an embedding-tightness measure; no semantic-coherence claim is made.

## Naming (Stage 2.4)
Terms come only from c-TF-IDF of the topic's own documents (no LLM). Generic terms are dropped; overlapping terms deduplicated; bigram lead caps the name at 2 terms. `coverage` = share of member documents containing ≥1 name term (measured). `confidence = 0.7·coverage + 0.3·distinctiveness`. Names are flagged `needs_review` for generic-only terms, no terms, or coverage < `topic_name_min_coverage`.

## Identity (Stage 3)
Existing one-to-one greedy centroid match retained. On top: `new`, `matched`, `potential_merge` (matched, but another unclaimed stored topic is ≥ floor-similar), `potential_split` (unmatched but ≥ floor-similar to a stored topic another new topic claimed; gets a **new** id), `uncertain` (between floor and threshold). Decisions + model-version change are stored in `diagnostics.identity`; review reasons surface on the topic. These are geometric signals, not proof.

## Activity state (Stage 4)
Derived at read time, relative to the latest **completed** run: `missed_runs` = completed runs finishing after the topic's last observation; `age` = days between that observation and the latest completed run. `stale` at ≥1 missed run or ≥14 d; `inactive` at ≥4 missed runs or ≥45 d (all configurable). Legacy topics fall back to their latest observation time. Lifecycle (emerging/growing/peaking/declining) is untouched and separate. Failed runs and outages do not age anything.

## Explainability (Stage 5)
Scoring unchanged. Added `acceleration_assessment` (sustained acceleration / single-window spike / rising / flat / insufficient history, from stored per-window volumes only) and `short_summary` (one line from stored values). Detail exposes signals, contributions, missing signals with reasons, coverage, identity and run.

## API contracts
| Endpoint | Notes |
|---|---|
| `GET /api/trends` | Array body (unchanged shape, new optional fields). Params: `q, lifecycle, activity_state (default active; all), min_sources, min_score, max_age_days, momentum, is_new, score_withheld, sort (score|growth|momentum|documents|recent|name), order, limit 1–200, offset`. Totals in `X-Total-Count`, `X-Limit`, `X-Offset` (CORS-exposed). Nulls sort last. Invalid enum → 422. |
| `GET /api/trends/{id}` | Adds terms, activity state, coverage, signals, contributions, acceleration, representative docs (nearest to centroid), related topics with similarity, run + model info, identity, review flags. 404 on unknown/invalid id. |
| `GET /api/trends/{id}/history` | Ordered by `window_end`; run id, `legacy` flag, momentum, growth, score, lifecycle; `limit`. |
| `GET /api/trends/overview` | Active/emerging/rising(=lifecycle growing)/peaking/declining/accelerating/new/withheld/review/stale/inactive counts, latest run & latest successful run, documents analysed, topic-model diagnostics, data freshness. |
| `GET /api/trends/runs`, `/runs/{id}` | Read-only; status filter, pagination; config holds model parameters only; errors scrubbed. |
| `GET /ready` | Now includes a `schema` component (fails if migration 003 not applied). |
Recompute stays on the existing token-protected internal endpoint; no admin controls were added to the UI.

## Frontend
Top bar (Discover / Investigate / Monitor + freshness indicator); Discovery Home (metrics, five sections); filterable, sortable, paginated Trends list with URL-state filters; Trend Detail (explanations under every metric, contribution chart, history, representative articles, related topics, model/run info); Analysis Runs (read-only, expandable diagnostics); Sources page with data-health strip. All data from the backend; no mock trend data in production components.
