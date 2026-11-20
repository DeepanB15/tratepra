# Trend scoring

Experimental formula (`formula_version v1.0`):

`T = 0.30G + 0.20M + 0.15E + 0.15N + 0.10S + 0.10C`, each component 0-100. Weights live in config; they are initial heuristics, not validated.

| Signal | Definition | Normalisation |
| --- | --- | --- |
| Growth G | `(V_t - V_{t-1}) / max(V_{t-1}, eps) * 100` over consecutive 7-day windows | -100% -> 0, 0% -> 50, +100% -> 100 |
| Momentum M | growth(latest) - growth(previous), needs >= 3 windows | -100pp -> 0, 0 -> 50, +100pp -> 100 |
| Engagement E | log-scaled views/likes/comments (YouTube) and score/comments (Reddit), topic mean, percentile-ranked across topics | percentile 0-100 |
| Novelty N | `1 - max cosine similarity` to topic centroids from previous runs | x100 |
| Search interest S | last-third vs first-third mean of Google Trends series for a query whose terms overlap the topic | like growth |
| Cross-source C | distinct text sources observed / configured text sources | x100 |

## Missing data
- A zero baseline gives `growth = None` (flagged `zero_baseline`), never infinity; baselines below 3 are flagged `sparse_baseline`.
- Missing signals are `None`, never 0. The score renormalises over available weights. If less than `TREND_MIN_COVERAGE` (default 50%) of the weight has data, the score is **withheld** (`null`).
- Novelty is `None` on the first run (no history). Cross-source is `None` when fewer than two text connectors are configured.
- Coverage (`sources_available`, `sources_observed`, available/missing signals) is stored with every observation.

## Lifecycle (`lifecycle.py`, thresholds configurable)
Emerging: new topic with enough documents, or strong growth that is accelerating. Growing: growth above threshold. Peaking: near the window maximum with flat growth. Declining: sustained negative growth. `null` when evidence is insufficient or activity is stable.

## Caveats
Historical windows are reconstructed from document `published_at`, so they are only meaningful if collection covered the window. Documents without a publication date are excluded from windows. Novelty indicates relative distinctiveness in the observed dataset only.
