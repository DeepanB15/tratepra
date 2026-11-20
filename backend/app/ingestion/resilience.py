"""Retry / backoff / failure classification for provider HTTP calls.

Rules:
- Timeouts and transient network errors, 5xx: retry with exponential backoff + jitter.
- 429: honour Retry-After when it is short; give up (rate_limit) when it is long or retries run out.
- 401/403 (including YouTube quota 403): permanent, never retried.
- Other 4xx: permanent, never retried.
- Never retries indefinitely; the final failure is raised as a ConnectorError so it is recorded, not hidden.
"""
import random
import time
from typing import Any, Callable

import httpx

from app.core.exceptions import ConnectorError

MAX_RETRY_AFTER_SECONDS = 30.0


def backoff_delay(attempt: int, base: float = 0.5, cap: float = 8.0, jitter: bool = True) -> float:
    delay = min(cap, base * (2**attempt))
    return delay * random.uniform(0.5, 1.0) if jitter else delay


def parse_retry_after(value: str | None) -> float | None:
    """Seconds from a numeric Retry-After header; HTTP-date form is ignored (-> None)."""
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def request_with_retry(
    method: str,
    url: str,
    *,
    source: str,
    timeout: float,
    max_retries: int,
    sleep: Callable[[float], Any] = time.sleep,
    request_fn: Callable[..., httpx.Response] | None = None,
    **kwargs: Any,
) -> httpx.Response:
    request_fn = request_fn or httpx.request
    for attempt in range(max_retries + 1):
        last_attempt = attempt >= max_retries
        try:
            resp = request_fn(method, url, timeout=timeout, **kwargs)
        except httpx.HTTPError as exc:
            if last_attempt:
                raise ConnectorError(source, f"Request failed after {attempt + 1} attempt(s): {type(exc).__name__}: {exc}")
            sleep(backoff_delay(attempt))
            continue

        status = resp.status_code
        if status < 400:
            return resp
        if status in (401, 403):
            if status == 403 and "quota" in resp.text.lower():
                raise ConnectorError(source, "API quota exceeded", kind="quota")
            raise ConnectorError(source, f"Authentication failed ({status})", kind="auth")
        if status == 429:
            wait = parse_retry_after(resp.headers.get("Retry-After"))
            if last_attempt or (wait is not None and wait > MAX_RETRY_AFTER_SECONDS):
                raise ConnectorError(source, "Rate limit exceeded", kind="rate_limit")
            sleep(wait if wait is not None else backoff_delay(attempt))
            continue
        if status >= 500:
            if last_attempt:
                raise ConnectorError(source, f"Provider error HTTP {status} after {attempt + 1} attempt(s)")
            sleep(backoff_delay(attempt))
            continue
        raise ConnectorError(source, f"HTTP {status}: {resp.text[:200]}")
    raise ConnectorError(source, "Request failed")  # unreachable; keeps type-checkers happy
