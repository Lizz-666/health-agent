"""Pure deterministic weight-trend helpers (Phase 2 Task 4).

Design constraints (mirror ``app.health.risk``):
- PURE functions only: no HTTP, no DB session, no LLM, no I/O.
- The moving trend is a simple, point-based moving average. It is descriptive
  only: Phase 2 NEVER emits plan / diet adjustments, warnings, or pass/fail
  judgment from single-day changes (spec Weight Record And Trend, Safety).

``compute_weight_trend`` consumes an already user-scoped, range-filtered,
ascending-by-recorded_at list of weight records plus a ``window`` size, and
returns the raw records, the moving-average series, the window, and a
``sufficient`` flag. When fewer than ``window`` records exist, ``sufficient``
is false and ``trend`` is empty (the explicit ``insufficient_data`` state).
"""

from typing import List

from app.health.schemas import (
    WeightRecordResponse,
    WeightTrendPoint,
    WeightTrendResponse,
)

# Decimal places the moving average is rounded to for deterministic output.
_TREND_PRECISION = 2


def _moving_average(values: List[float], start: int, end: int) -> float:
    """Arithmetic mean of ``values[start:end]`` (``end`` exclusive), rounded to
    ``_TREND_PRECISION`` decimals for deterministic output."""
    window = values[start:end]
    avg = sum(window) / len(window)
    return round(avg, _TREND_PRECISION)


def compute_weight_trend(
    records: List[WeightRecordResponse], window: int
) -> WeightTrendResponse:
    """Build the deterministic weight trend for an ascending-by-recorded_at
    list of records.

    A trend point is emitted for each record from index ``window - 1`` onward:
    the simple moving average of the trailing ``window`` records up to and
    including the current one. When ``len(records) < window`` the trend is
    empty and ``sufficient`` is false (insufficient data).

    No recommendation / adjustment / warning text is ever produced.
    """
    count = len(records)

    if count < window:
        return WeightTrendResponse(
            records=list(records),
            trend=[],
            window=window,
            sufficient=False,
        )

    values = [r.weight_kg for r in records]
    trend: List[WeightTrendPoint] = []
    for i in range(window - 1, count):
        trend.append(
            WeightTrendPoint(
                recorded_at=records[i].recorded_at,
                weight_kg=_moving_average(values, i - window + 1, i + 1),
            )
        )

    return WeightTrendResponse(
        records=list(records),
        trend=trend,
        window=window,
        sufficient=True,
    )
