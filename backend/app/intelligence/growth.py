"""Growth: G = (V_t - V_{t-1}) / max(V_{t-1}, eps) * 100, with explicit baseline flags."""
from dataclasses import dataclass

EPSILON = 1.0
MIN_RELIABLE_BASELINE = 3  # below this, percentage growth is not reliable


@dataclass
class GrowthResult:
    value: float | None  # percent; None when baseline is zero (not infinite)
    flag: str  # ok | sparse_baseline | zero_baseline | insufficient_history


def growth_pct(current: float, previous: float | None) -> GrowthResult:
    if previous is None:
        return GrowthResult(None, "insufficient_history")
    if previous <= 0:
        # A zero baseline must not become an "infinite" growth rate.
        return GrowthResult(None, "zero_baseline")
    g = (current - previous) / max(previous, EPSILON) * 100.0
    flag = "ok" if previous >= MIN_RELIABLE_BASELINE else "sparse_baseline"
    return GrowthResult(g, flag)


def normalize_growth(g: float | None) -> float | None:
    """Map percent growth to 0-100: -100% -> 0, 0% -> 50, +100% (or more) -> 100."""
    if g is None:
        return None
    return max(0.0, min(100.0, 50.0 + g / 2.0))


def series_growths(volumes: list[int]) -> list[GrowthResult]:
    """Growth for each consecutive window pair (len = len(volumes) - 1)."""
    return [growth_pct(volumes[i], volumes[i - 1]) for i in range(1, len(volumes))]
