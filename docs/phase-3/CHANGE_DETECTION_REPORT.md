# Change Detection Evaluation

**What this is:** 20 synthetic, hand-constructed cases (`data/evaluation/change_cases.json`) with expected event types written from the rules in `PHASE_3_ARCHITECTURE.md` *before* running the detector. Run: `python backend/scripts/evaluate_change_detection.py`.

**Measured result (synthetic):** 20/20 cases passed; event precision 1.0, recall 1.0 (0 false positives, 0 false negatives over those cases).

**Categories:** acceleration, noise (small fluctuation, pp change without volume change), slowdown, decline, lifecycle (forward / unchanged), spike (stable baseline, noisy baseline, short baseline), comparability (formula, window, single snapshot), missing values, gating (volume, sources), disappearance, failure policy (suppression when collection failed), new emerging trend.

**Limits — read before quoting these numbers:**
- The cases were written by the same author as the detector and overlap the unit tests; passing them shows the rules behave as specified, **not** that the thresholds are right for real data.
- No labelled real-world trend history exists here, so real precision/recall is **unknown**.
- Historical replay (`--replay`, read-only, counts only) was run on the isolated e2e database containing 3 synthetic topics: 3 comparisons, 3 lifecycle + 3 growth events, 3 spike evaluations suppressed (baseline too short). This is a behaviour check, not an accuracy measurement.
- Thresholds are configurable (`MONITORING_*`) and should be tuned on a real corpus; false-positive and false-negative review of a week of real events is the recommended protocol.
- Event types without a pure detector case (new_supporting_evidence, contradictory_evidence, new_related_topic) are covered by PostgreSQL integration tests, not this dataset.
