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


def percentile_grade(percentile: float | int | None) -> str:
    """Compact display-only tier derived directly from the WCL percentile."""
    value = safe_percentile(percentile)
    if value is None:
        return "—"
    if value >= 95:
        return "S"
    if value >= 85:
        return "A"
    if value >= 75:
        return "B"
    if value >= 50:
        return "C"
    if value >= 25:
        return "D"
    if value >= 10:
        return "E"
    return "F"


def applicant_board_rows(rows) -> list[tuple[str, str, str]]:
    """Return current applicants sorted by live WCL percentile, highest first."""
    prepared: list[tuple[float, str, str, str]] = []
    for view in rows:
        name = str(view.applicant.name or "").strip() or "Onbekend"
        metric = role_metric(view)
        if metric is not None:
            metric_name, percentile = metric
            label = "Healing" if metric_name == "HPS" else "DPS"
            prepared.append((
                float(percentile),
                name,
                f"{label} {percentile:.0f}%",
                percentile_grade(percentile),
            ))
            continue

        status = {
            "queued": "Wachten…",
            "loading": "Laden…",
            "none": "Geen WCL-data",
            "error": "WCL fout",
            "disabled": "Niet verbonden",
        }.get(str(view.wcl_status or ""), "—")
        prepared.append((-1.0, name, status, "—"))

    prepared.sort(key=lambda item: (item[0] < 0, -item[0], item[1].casefold()))
    return [(name, metric_text, grade) for _percentile, name, metric_text, grade in prepared]

