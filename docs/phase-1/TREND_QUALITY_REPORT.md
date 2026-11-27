# Trend Quality Report

## Status: real-data evaluation NOT YET RUN

The sandbox that built Phase 1 cannot reach your Supabase database and has no Sentence-Transformers/PyTorch, so **no metric below has been measured on your dataset. No quality claim is made.** Nothing in this document is estimated or invented.

## What was verified (synthetic, labelled as such)
On a deliberately constructed corpus (three keyword clusters, fake hash embeddings, seeded e2e database) the real pipeline produced: 3 topics, 0% noise, sizes 10 / 15 / 28, embedding cohesion ≈ 0.95, a score withheld for the topic with 15% signal coverage, correct flagging of one topic as "overly broad" (53% of clustered docs). This shows the **diagnostics work**; it says nothing about quality on real news/Reddit/YouTube text. Synthetic BERTopic test: reproducible assignments across two fits.

## How to produce the real evaluation (read-only, writes nothing)
```bash
cd backend
python -m scripts.evaluate_trend_quality --out ../docs/phase-1/TREND_QUALITY_REPORT.generated.md
```
It runs the full pipeline with `dry_run=True` and reports: eligible documents and every rejection reason, topic count, noise ratio, size distribution, source distribution, embedding cohesion, name coverage, score coverage / withheld count, identity outcomes against stored topics, plus a **manual-review table** (coherent? too broad? duplicate of #? name OK? explanation accurate?) with empty verdict columns.

## Review protocol (to fill in after running)
1. Review at least the 15 largest topics and every flagged topic by reading their representative titles.
2. Mark coherence / breadth / duplicates / name adequacy by hand; record reviewer and date.
3. Compare each topic's one-line explanation with its stored volumes and signals.
4. Only then copy aggregate counts here. Report "x of n reviewed topics judged coherent", never a metric score.

| Item | Result |
|---|---|
| Eligible documents | _pending_ |
| Topics discovered / noise ratio | _pending_ |
| Topic size distribution | _pending_ |
| Reviewed topics judged coherent / broad / duplicate | _pending_ |
| Names judged adequate | _pending_ |
| Score coverage (withheld share) | _pending_ |
| Explanations judged accurate | _pending_ |

## Known quality risks to look for
- `min_cluster_size = max(5, n//40)` and HDBSCAN `eom` can yield one broad topic or high noise on small/mixed corpora — flagged automatically (`overly_broad`, `high_noise`).
- The English check is a heuristic; non-English text that passes would add noise.
- Name coverage measures term presence, not meaning.
- Cosine-UMAP may attach stray points to clusters (observed on synthetic data), so a low noise % is not evidence of purity.
