"""Momentum: change in growth between the latest and previous consecutive windows."""
from dataclasses import dataclass

from app.intelligence.growth import series_growths


@dataclass
class MomentumResult:
    value: float | None  # percentage-point change in growth
    direction: str  # accelerating | decelerating | steady | unknown


def momentum(volumes: list[int], steady_band: float = 5.0) -> MomentumResult:
    """Needs >= 3 consistent windows (two growth values). Growth values with zero/absent
    baselines are unusable, so momentum is then reported as unknown rather than guessed."""
    if len(volumes) < 3:
        return MomentumResult(None, "unknown")
    growths = series_growths(volumes)
    prev, cur = growths[-2], growths[-1]
    if prev.value is None or cur.value is None:
        return MomentumResult(None, "unknown")
    delta = cur.value - prev.value
    if delta > steady_band:
        direction = "accelerating"
    elif delta < -steady_band:
        direction = "decelerating"
    else:
        direction = "steady"
    return MomentumResult(delta, direction)


def normalize_momentum(m: float | None) -> float | None:
    """-100pp -> 0, 0pp -> 50, +100pp -> 100."""
    if m is None:
        return None
    return max(0.0, min(100.0, 50.0 + m / 2.0))
