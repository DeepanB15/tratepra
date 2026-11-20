# Evaluation

Run `cd backend && python -m scripts.evaluate [--k 5]`. The report has two parts.

## 1. Lifecycle rules (synthetic regression check)
`data/evaluation/trend_cases.json` holds seven **synthetic** weekly-volume series with the label a reviewer expects (steady noise, flat plateau, tiny-base spike, steady growth, acceleration, rise-then-plateau, steep fall). It guards the rule set against regressions. It is **not** a measurement on real data. Building these cases already exposed one defect (a flat series was labelled "peaking"), which is fixed.

## 2. Retrieval quality (needs your labels)
`data/evaluation/research_queries.json` is an intentionally **unlabelled template**. Ground truth cannot be invented:
1. Collect data for each query (`scripts.collect_data`).
2. Review the retrieved documents by hand and list the URLs that truly answer the query in `relevant_urls`.
3. Run `scripts.evaluate`. Reported: precision@k, recall@k, MRR, nDCG@k averaged over labelled queries. Unlabelled queries are listed as skipped, never scored.

Until labels exist, **no retrieval-quality number is claimed** and the ranking weights (0.45/0.25/0.20/0.10) remain untuned heuristics.

## Other metrics available (`backend/app/evaluation/`)
- `citations.py`: verified-claim rate, invalid references, evidence coverage for an answer. The check is lexical overlap plus URL validity: it catches uncited, invented-reference and unrelated claims, but cannot detect a claim that reuses the right words with the wrong meaning.
- `trend_quality.py`: BERTopic noise rate, topic stability between runs (best-Jaccard), a cheap coherence proxy (not NPMI), lifecycle accuracy on labelled cases.
- `benchmark.py`: timing helper.

## Known limits
- Language guard: English function-word ratio, not a language identifier.
- Trend validity depends on collection spanning the analysis windows (42 days by default).
- Needs at least 20 documents for BERTopic to run.
