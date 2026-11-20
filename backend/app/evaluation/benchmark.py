"""Timing helper for performance baselines."""
import statistics
import time
from typing import Callable


def time_it(fn: Callable[[], object], repeat: int = 5) -> dict:
    samples = []
    for _ in range(repeat):
        t = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t) * 1000)
    samples.sort()
    return {
        "runs": repeat,
        "min_ms": round(samples[0], 2),
        "median_ms": round(statistics.median(samples), 2),
        "max_ms": round(samples[-1], 2),
    }
