"""Detection thresholds as one immutable object so detectors are pure and tests can vary them."""
from dataclasses import dataclass

DETECTION_VERSION = "cd-1"  # bump when any rule changes; stored on every event


@dataclass(frozen=True)
class MonitoringConfig:
    min_observations: int = 2
    min_documents: int = 8
    min_sources: int = 2
    min_growth_change_pp: float = 15.0
    min_volume_change: int = 5
    decline_pct: float = 30.0
    spike_baseline_window: int = 5
    spike_z: float = 3.0
    spike_min_ratio: float = 1.5
    critical_spike_ratio: float = 3.0
    new_documents_min: int = 3
    related_similarity: float = 0.75
    emerging_min_score: float = 0.0
    emerging_important_score: float = 70.0
    cooldown_hours: float = 24.0
    window_tolerance_days: float = 1.0
    new_topic_days: float = 14.0

    @classmethod
    def from_settings(cls, s) -> "MonitoringConfig":
        return cls(
            min_observations=s.monitoring_min_observations, min_documents=s.monitoring_min_documents, min_sources=s.monitoring_min_sources,
            min_growth_change_pp=s.monitoring_min_growth_change_pp, min_volume_change=s.monitoring_min_volume_change,
            decline_pct=s.monitoring_decline_pct, spike_baseline_window=s.monitoring_spike_baseline_window, spike_z=s.monitoring_spike_z,
            spike_min_ratio=s.monitoring_spike_min_ratio, critical_spike_ratio=s.monitoring_critical_spike_ratio,
            new_documents_min=s.monitoring_new_documents_min, related_similarity=s.monitoring_related_similarity,
            emerging_min_score=s.monitoring_emerging_min_score, emerging_important_score=s.monitoring_emerging_important_score,
            cooldown_hours=s.monitoring_cooldown_hours, window_tolerance_days=s.monitoring_window_tolerance_days, new_topic_days=s.trend_new_topic_days,
        )
