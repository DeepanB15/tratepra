"""Lifecycle classification with configurable thresholds."""
from app.core.config import Settings, get_settings
from app.intelligence.growth import MIN_RELIABLE_BASELINE, series_growths

EMERGING, GROWING, PEAKING, DECLINING = "emerging", "growing", "peaking", "declining"


def classify(volumes: list[int], s: Settings | None = None) -> str | None:
    """Return a lifecycle label or None when evidence is insufficient or activity is stable.

    volumes: documents per consistent window, oldest first.
    """
    s = s or get_settings()
    if len(volumes) < 2 or sum(volumes) < s.lifecycle_min_documents:
        return None

    growths = series_growths(volumes)
    latest = growths[-1]
    prev = growths[-2] if len(growths) >= 2 else None
    cur_v, prev_v = volumes[-1], volumes[-2]
    peak = max(volumes)
    nonzero_history = sum(1 for v in volumes[:-1] if v > 0)

    # Declining: sustained reduction (two consecutive negative windows when history allows).
    if latest.value is not None and latest.value <= s.lifecycle_declining_max_growth:
        if prev is None or prev.value is None or prev.value < 0:
            return DECLINING

    # Emerging: new topic (almost no prior activity) or strongly accelerating, with enough evidence.
    new_topic = prev_v < MIN_RELIABLE_BASELINE and cur_v >= s.lifecycle_min_documents
    strong = latest.value is not None and latest.value >= s.lifecycle_emerging_min_growth and (
        prev is not None and prev.value is not None and latest.value > prev.value
    )
    # Spike guard: a relative jump on a tiny base (1 -> 2 documents is +100%) is noise, so a growth-based
    # label needs a minimum absolute increase. A genuinely new topic is judged by its own volume rule.
    meaningful = (cur_v - prev_v) >= s.lifecycle_min_abs_increase
    if (new_topic and nonzero_history <= 2) or (strong and meaningful):
        return EMERGING

    # Peaking: at/near local maximum but no longer growing meaningfully.
    # A flat series is a plateau, not a peak: the current level must also stand clearly above earlier activity.
    earlier_mean = sum(volumes[:-1]) / (len(volumes) - 1)
    risen = cur_v >= 1.3 * earlier_mean
    if cur_v >= 0.9 * peak and risen and (latest.value is None or latest.value < s.lifecycle_growing_min_growth) and len(volumes) >= 3:
        return PEAKING

    # Growing: sustained increase.
    if latest.value is not None and latest.value >= s.lifecycle_growing_min_growth and meaningful:
        return GROWING

    return None
