from __future__ import annotations

import math

from .constants import HEALER_SPECS
from .models import ApplicantView


def safe_percentile(value: float | int | None) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return max(0.0, min(100.0, number))


def role_metric(view: ApplicantView) -> tuple[str, float] | None:
    """Return the one public metric KeystoneLens is allowed to surface."""
    wcl = view.wcl
    if not wcl or wcl.error or wcl.not_found:
        return None

    metric_key = "hps" if view.applicant.spec_id in HEALER_SPECS else "dps"
    bracket = wcl.metric_brackets.get(metric_key)
    if bracket is None:
        return None

    percentile = (
        bracket.average_percentile
        if bracket.run_count >= 2
        else bracket.best_percentile
    )
    percentile = safe_percentile(percentile)
    if percentile is None:
        return None

    return ("HPS" if metric_key == "hps" else "DPS"), percentile


def percentile_hex(percentile: float) -> str:
    value = safe_percentile(percentile) or 0.0
    if value >= 100:
        return "#e6cc80"
    if value >= 99:
        return "#e369a8"
    if value >= 95:
        return "#ff8000"
    if value >= 75:
        return "#a335ee"
    if value >= 50:
        return "#0070dd"
    if value >= 25:
        return "#1eff00"
    return "#666666"
