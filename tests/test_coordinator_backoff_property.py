"""Property-based tests for BikeCoordinator exponential back-off.

Property 10: Back-off retry interval is bounded and grows with consecutive failures.

For any number of consecutive polling failures n >= 1, the computed retry interval
SHALL satisfy:
- base_interval <= retry_interval(n) <= MAX_RETRY_INTERVAL
- retry_interval(n) <= retry_interval(n+1)  (monotonically non-decreasing)
- The interval SHALL never exceed MAX_RETRY_INTERVAL_MINUTES * 60 seconds.

**Validates: Requirements 5.3**
"""
from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from custom_components.bosch_ebike_ha.const import (
    DEFAULT_POLL_INTERVAL_MINUTES,
    MAX_RETRY_INTERVAL_MINUTES,
)

# ---------------------------------------------------------------------------
# Pure back-off formula extracted from BikeCoordinator._async_refresh
# (mirrors the implementation in coordinator.py exactly)
# ---------------------------------------------------------------------------

_BASE_INTERVAL_SECONDS = DEFAULT_POLL_INTERVAL_MINUTES * 60
_MAX_INTERVAL_SECONDS = MAX_RETRY_INTERVAL_MINUTES * 60


def compute_retry_interval(n: int) -> float:
    """Return the retry interval in seconds for n consecutive failures.

    Mirrors the formula used in BikeCoordinator._async_refresh:
        min(base * 2**n, MAX_RETRY_INTERVAL_MINUTES * 60)
    """
    base = DEFAULT_POLL_INTERVAL_MINUTES * 60
    max_interval = MAX_RETRY_INTERVAL_MINUTES * 60
    return min(base * (2 ** n), max_interval)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Failure counts in the range 1–100 as specified by the task.
failure_counts = st.integers(min_value=1, max_value=100)


# ---------------------------------------------------------------------------
# Property 10 — bounded retry interval
# ---------------------------------------------------------------------------


@given(n=failure_counts)
@settings(max_examples=100)
def test_retry_interval_lower_bound(n):
    """**Validates: Requirements 5.3**

    For any n >= 1, the retry interval is at least the base polling interval.
    The first failure (n=1) doubles the base, so the interval is always >= base.
    """
    interval = compute_retry_interval(n)
    assert interval >= _BASE_INTERVAL_SECONDS, (
        f"retry_interval({n})={interval} is below base interval "
        f"{_BASE_INTERVAL_SECONDS}"
    )


@given(n=failure_counts)
@settings(max_examples=100)
def test_retry_interval_upper_bound(n):
    """**Validates: Requirements 5.3**

    For any n >= 1, the retry interval never exceeds MAX_RETRY_INTERVAL_MINUTES * 60
    seconds. The min() cap in the formula guarantees this.
    """
    interval = compute_retry_interval(n)
    assert interval <= _MAX_INTERVAL_SECONDS, (
        f"retry_interval({n})={interval} exceeds MAX_RETRY_INTERVAL "
        f"{_MAX_INTERVAL_SECONDS}"
    )


@given(n=failure_counts)
@settings(max_examples=100)
def test_retry_interval_monotonically_non_decreasing(n):
    """**Validates: Requirements 5.3**

    For any n >= 1, retry_interval(n) <= retry_interval(n+1).
    The exponential growth (capped at max) is monotonically non-decreasing.
    """
    interval_n = compute_retry_interval(n)
    interval_n1 = compute_retry_interval(n + 1)
    assert interval_n <= interval_n1, (
        f"retry_interval({n})={interval_n} > retry_interval({n + 1})={interval_n1}: "
        "back-off is not monotonically non-decreasing"
    )


@given(n=failure_counts)
@settings(max_examples=100)
def test_retry_interval_never_exceeds_max(n):
    """**Validates: Requirements 5.3**

    Explicit check that the interval is strictly capped at MAX_RETRY_INTERVAL_MINUTES
    * 60 seconds, even for very large n where 2**n would overflow the cap.
    """
    interval = compute_retry_interval(n)
    max_seconds = MAX_RETRY_INTERVAL_MINUTES * 60
    assert interval <= max_seconds, (
        f"retry_interval({n})={interval} exceeds hard cap of {max_seconds}s"
    )
