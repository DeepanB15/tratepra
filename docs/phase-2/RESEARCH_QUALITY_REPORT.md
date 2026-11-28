# Phase 2 Research Quality Report

**Read this first.** No real-corpus or real-LLM evaluation has been run. The development sandbox has no collected production data, no embedding model download and no Ollama. Numbers below are from controlled synthetic fixtures and test the *wiring and rules*, not real-world quality. No manually reviewed dossier sample exists yet.

## What was measured
| Check | Setup | Result |
|---|---|---|
| Hybrid retrieval + ranking + selection regression | 3 synthetic topical clusters × 10 docs, fake bag-of-words embeddings, labels by construction (`test_synthetic_retrieval_regression_metrics`) | P@5 = 1.0, MRR = 1.0, nDCG@5 = 1.0, duplicate rate = 0.0; Recall@5 = 0.5 (5 of 10 relevant, K=5 cap) |
| Article text reaches LLM context and citation checks | Fixture: claim grounded only in article text (not in the RSS blurb) | Before: unverifiable (context/verifier saw title+description only). After: `supported`, excerpt basis `article` |
| Contradiction handling | "X use …" vs "X do not use …" fixture | Detected; previously the near-duplicate-title filter dropped the opposite headline — fixed (opposite polarity is kept) |
| Insufficient evidence | Query with no matching documents | Dossier completes, "Insufficient evidence" overview, coverage label `insufficient`, `no_evidence` gap |
| LLM failure | Synthesizer raising | Dossier completes, `degraded`, no fabricated claims |
| Browser e2e | Isolated DB, seeded trends, no LLM | Trend → Investigate → dossier with all 7 sections, evidence filters, claim view, refresh: passed |

These are pass/fail checks. They say nothing about precision on real news, claim-support accuracy, or how often the lexical heuristic is wrong.

## What is NOT measured (and how to measure it)
`scripts/evaluate_research_quality.py` implements the protocol; it scores only human-labelled cases and reports skipped ones.
1. `python -m scripts.evaluate_research_quality --init` writes 7 candidate questions per recent stored topic (factual, trend explanation, comparative, time-based, entity, insufficient-evidence, contradictory) to `data/evaluation/research_eval.json`.
2. A reviewer reads stored documents and fills `relevant_urls`, `expected_gaps`, `expect_insufficient` / `expect_contradiction`, `reviewed_by`.
3. `python -m scripts.evaluate_research_quality --k 5 --dossiers` reports P@K, R@K, MRR, nDCG@K, publisher diversity, duplicate rate and, per dossier, citation coverage, claim support rate, unsupported claim rate, completeness, gap recall/precision and insufficient-evidence detection.
4. Manually read at least 10 generated dossiers and record claim-level judgments before trusting the support rate: the rate is a lexical overlap rate, not accuracy.

## Known weaknesses to evaluate
- Lexical support check can pass reused vocabulary with the wrong meaning and fail good paraphrases; threshold 0.6 is a judgement, not tuned.
- Contradiction detection needs explicit negation/decline wording.
- Embedding truncation may limit how much article text shapes vectors (unverified); FTS covers the full text.
- Entities are lexical (capitalised phrases, acronyms, product-like tokens); no typing.
- Publisher is metadata or URL host; syndication across hosts is only caught by title/URL/hash duplicates.
