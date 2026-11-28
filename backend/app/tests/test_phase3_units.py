from datetime import datetime, timedelta, timezone

from app.monitoring.config import MonitoringConfig
from app.monitoring.detection import detect
from app.monitoring.explanations import explain, finalize, guard_rewrite
from app.monitoring.pipeline import cosine
from app.monitoring.snapshots import Snapshot, comparable, comparable_history

T0 = datetime(2026, 10, 1, tzinfo=timezone.utc)
CFG = MonitoringConfig()


def snap(i, vol=20, growth=10.0, lifecycle="growing", sources=3, formula="v1.0", days=14, topic="t1"):
    end = T0 + timedelta(days=7 * i)
    return Snapshot(
        observation_id=f"o{i}", run_id=f"r{i}", topic_id=topic, observed_at=end, window_start=end - timedelta(days=days), window_end=end,
        trend_score=50.0 + i, score_coverage=0.9, growth=growth, momentum_pp=1.0, momentum_direction="steady", novelty=0.2,
        document_volume=vol, sources=sources, lifecycle=lifecycle, formula_version=formula, model_version="m",
    )


def types(d):
    return [e.event_type for e in d.events]


def run(history, **kw):
    return detect(history, CFG, topic_name="AI coding", **kw)


# ---- growth / decline ---------------------------------------------------------------------
def test_genuine_acceleration_fires_with_values_and_thresholds():
    d = run([snap(0, 20, 10), snap(1, 31, 45)])
    (e,) = [e for e in d.events if e.event_type == "growth_acceleration"]
    assert (e.previous_value, e.current_value) == (10, 45) and e.details["change_points"] == 35 and e.details["volume_change"] == 11
    assert e.severity == "important" and e.details["thresholds"]["min_growth_change_pp"] == 15.0
    assert e.previous_observation_id == "o0" and e.current_observation_id == "o1"


def test_small_fluctuation_creates_no_event():
    assert run([snap(0, 20, 10), snap(1, 22, 14)]).events == []


def test_acceleration_requires_real_volume_change():
    assert "growth_acceleration" not in types(run([snap(0, 20, 10), snap(1, 22, 40)]))


def test_slowdown_only_when_still_growing():
    assert types(run([snap(0, 20, 60), snap(1, 22, 30)])) == ["growth_slowdown"]
    assert types(run([snap(0, 20, 60), snap(1, 22, -5)])) == []  # shrinking is not a slowdown of growth


def test_missing_growth_is_not_treated_as_zero():
    d = run([snap(0, 20, None), snap(1, 40, 80)])
    assert "growth_acceleration" not in types(d) and any("not measured" in s["reason"] for s in d.suppressed)


def test_decline_needs_relative_and_absolute_drop():
    assert types(run([snap(0, 40, 5), snap(1, 24, 5)])) == ["activity_decline"]
    assert types(run([snap(0, 10, 5), snap(1, 8, 5)])) == []  # small absolute change
    e = run([snap(0, 40, 5), snap(1, 12, 5)]).events[0]
    assert e.severity == "important" and e.change_percentage == -70.0


def test_decline_not_raised_when_collection_failed():
    d = run([snap(0, 40, 5), snap(1, 10, 5)], collection_failed=True)
    assert "activity_decline" not in types(d) and any("collection failed" in s["reason"] for s in d.suppressed)


def test_low_volume_or_low_source_diversity_is_suppressed_with_reason():
    d = run([snap(0, 3, 5), snap(1, 7, 90)])
    assert d.events == [] and any("below the minimum" in s["reason"] for s in d.suppressed)
    d = run([snap(0, 20, 10, sources=1), snap(1, 40, 80, sources=1)])
    assert d.events == [] and any("source(s) observed" in s["reason"] for s in d.suppressed)


# ---- lifecycle ----------------------------------------------------------------------------
def test_lifecycle_forward_important_backward_informational_and_unchanged_silent():
    f = run([snap(0, 20, 10, "emerging"), snap(1, 21, 10, "growing")]).events
    assert [e.event_type for e in f] == ["lifecycle_transition"] and f[0].severity == "important" and f[0].details["forward"]
    b = run([snap(0, 20, 10, "declining"), snap(1, 21, 10, "growing")]).events
    assert b[0].severity == "informational" and not b[0].details["forward"]
    assert run([snap(0, 20, 10, "growing"), snap(1, 21, 10, "growing")]).events == []


# ---- comparability ------------------------------------------------------------------------
def test_incompatible_formula_or_window_is_never_compared():
    d = run([snap(0, 20, 10, "emerging", formula="v1.0"), snap(1, 60, 90, "growing", formula="v2.0")])
    assert d.events == [] and any("formula changed" in s["reason"] for s in d.suppressed)
    d = run([snap(0, 20, 10, days=14), snap(1, 60, 90, days=30)])
    assert d.events == [] and any("window length differs" in s["reason"] for s in d.suppressed)
    ok, why = comparable(snap(1), snap(0))
    assert not ok and "not older" in why


def test_comparison_skips_incompatible_snapshots_and_uses_the_comparable_one():
    hist = [snap(0, 5, 1, formula="v0"), snap(1, 20, 10), snap(2, 31, 45)]
    cur, prior, note = comparable_history(hist)
    assert cur.observation_id == "o2" and [p.observation_id for p in prior] == ["o1"]
    assert "growth_acceleration" in types(run(hist))


def test_single_snapshot_never_compares():
    d = run([snap(0, 50, 90)])
    assert d.events == [] and any("comparable observation" in s["reason"] for s in d.suppressed)


# ---- spike --------------------------------------------------------------------------------
def spike_history(cur_vol, base=(20, 21, 19, 20, 20)):
    return [snap(i, v, 5) for i, v in enumerate(base)] + [snap(len(base), cur_vol, 5)]


def test_spike_vs_stable_baseline_and_critical_ratio():
    e = [e for e in run(spike_history(40)).events if e.event_type == "activity_spike"][0]
    assert e.severity == "important" and e.details["baseline_n"] == 5 and e.details["ratio"] == 2.0 and "not a significance test" in e.details["statistical_test"]
    assert [e for e in run(spike_history(70)).events if e.event_type == "activity_spike"][0].severity == "critical"


def test_no_spike_inside_normal_range_or_noisy_baseline_or_short_baseline():
    assert "activity_spike" not in types(run(spike_history(23)))
    assert "activity_spike" not in types(run(spike_history(36, base=(10, 40, 12, 38, 15))))  # noisy: 36 is not unusual
    d = run([snap(0, 20, 5), snap(1, 20, 5), snap(2, 60, 5)])
    assert "activity_spike" not in types(d) and any("baseline observation" in s["reason"] for s in d.suppressed)


def test_flat_baseline_uses_ratio_and_absolute_rules():
    e = [e for e in run(spike_history(32, base=(20, 20, 20, 20, 20))).events if e.event_type == "activity_spike"]
    assert e and e[0].details["z"] is None


# ---- activity disappearance / emerging ----------------------------------------------------
def test_stale_and_inactive_events_use_completed_run_state_and_respect_collection_failure():
    hist = [snap(0), snap(1)]
    act = {"state": "stale", "missed_runs": 1, "last_observed_at": T0}
    e = run(hist, activity=act).events[0]
    assert e.event_type == "activity_disappearance" and e.severity == "informational" and e.details["missed_runs"] == 1
    assert run(hist, activity={**act, "state": "inactive"}).events[0].severity == "important"
    assert run(hist, activity={"state": "active", "missed_runs": 0, "last_observed_at": T0}).events == []
    d = run(hist, activity=act, collection_failed=True)
    assert d.events == [] and any("collection failed" in s["reason"] for s in d.suppressed)


def test_new_emerging_trend_only_for_first_snapshot_and_gated():
    d = run([snap(0, 15, 50, "emerging")], is_new_topic=True)
    assert types(d) == ["new_emerging_trend"]
    assert run([snap(0, 15, 50, "emerging")], is_new_topic=False).events == []
    assert run([snap(0, 4, 50, "emerging")], is_new_topic=True).events == []
    assert run([snap(0, 15, 50, "growing")], is_new_topic=True).events == []


def test_dedup_keys_are_deterministic_and_observation_scoped():
    a = [e.dedup_key for e in run([snap(0, 20, 10), snap(1, 31, 45)]).events]
    b = [e.dedup_key for e in run([snap(0, 20, 10), snap(1, 31, 45)]).events]
    assert a == b and all(k.startswith("t1:") and "o1" in k for k in a)
    assert a != [e.dedup_key for e in run([snap(0, 20, 10), snap(2, 31, 45)]).events]


# ---- explanations -------------------------------------------------------------------------
def test_explanation_uses_only_stored_values_and_states_reliability_and_evidence():
    e = run([snap(0, 18, 10, "emerging"), snap(1, 31, 45, "growing")]).events
    acc = next(x for x in e if x.event_type == "growth_acceleration")
    text = explain(acc)
    assert "from 10% to 45%" in text and "18 to 31" in text and "+35 points" in text
    assert "compared with the previous observation window ending" in text and "3 source(s)" in text and "90% score signal coverage" in text
    assert "none attached; this event is based on aggregate observations only" in text
    acc.evidence_document_ids = ["d1", "d2"]
    assert "2 document(s) attached: Doc A; Doc B." in explain(acc, ["Doc A", "Doc B"])
    lc = next(x for x in e if x.event_type == "lifecycle_transition")
    assert "from emerging to growing" in explain(lc)


def test_spike_explanation_does_not_claim_significance():
    e = next(x for x in run(spike_history(40)).events if x.event_type == "activity_spike")
    t = explain(e)
    assert "not a statistical significance test" in t and "significant" not in t.replace("significance", "")


def test_llm_rewrite_cannot_change_numbers_and_failures_keep_the_original():
    orig = "Volume rose from 18 to 31 across 3 publishers."
    assert guard_rewrite(orig, "Volume went from 18 up to 31 across 3 publishers.")
    assert not guard_rewrite(orig, "Volume rose from 18 to 35 across 3 publishers.")
    assert not guard_rewrite(orig, "Volume rose by 13 documents.")
    assert finalize(orig, lambda t: "Volume rose by 99.") == (orig, False)
    assert finalize(orig, lambda t: (_ for _ in ()).throw(TimeoutError("down"))) == (orig, False)
    assert finalize(orig, lambda t: "Volume climbed from 18 to 31 over 3 publishers.")[1] is True
    assert finalize(orig, None) == (orig, False)


def test_cosine():
    assert cosine([1, 0], [1, 0]) == 1.0 and cosine([1, 0], [0, 1]) == 0.0 and cosine(None, [1]) is None and cosine([0, 0], [1, 1]) is None
