from __future__ import annotations

import math

from .constants import HEALER_SPECS
from .models import Applicant, Listing, ScoreBreakdown, WCLBracket, WCLResult
from .rio import RIOResult
from .registries import is_season1_carryover_source, use_season1_carryover

# KeystoneLens deliberately has only two scoring pillars.
# Nothing else can add or subtract points from the displayed KL Score.
BASE_RIO_WEIGHT = 0.50
BASE_WCL_WEIGHT = 0.50

# Raider.IO publishes the base run score for a key completed exactly on time.
# The official run score already combines key level and timer performance, so
# KeystoneLens uses it as the primary exact-dungeon evidence instead of
# separately double-counting key level and clear-time quality.
RIO_BASE_RUN_SCORE_BY_KEY: dict[int, float] = {
    2: 155.0, 3: 170.0, 4: 200.0, 5: 215.0, 6: 230.0, 7: 260.0,
    8: 275.0, 9: 290.0, 10: 320.0, 11: 335.0, 12: 365.0, 13: 380.0,
    14: 395.0, 15: 410.0, 16: 425.0, 17: 440.0, 18: 455.0,
    19: 470.0, 20: 485.0, 21: 500.0, 22: 515.0, 23: 530.0,
    24: 545.0, 25: 560.0, 26: 575.0, 27: 590.0, 28: 605.0,
    29: 620.0, 30: 635.0,
}


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    """Clamp numeric evidence without ever promoting NaN/Inf to a high score."""
    try:
        value = float(v)
    except (TypeError, ValueError, OverflowError):
        return float(lo)
    if not math.isfinite(value):
        return float(lo)
    return max(float(lo), min(float(hi), value))


def _key_fit(done: int, target: int) -> float:
    if target <= 0 or done <= 0:
        return 0.0
    delta = done - target
    if delta >= 2:
        return 100.0
    if delta == 1:
        return 98.0
    if delta == 0:
        return 94.0
    if delta == -1:
        return 82.0
    if delta == -2:
        return 68.0
    if delta == -3:
        return 54.0
    if delta == -4:
        return 40.0
    return _clamp(40.0 - 9.0 * (-delta - 4), 5.0, 40.0)


def _usable_rio(rio: RIOResult | None) -> bool:
    return bool(rio and not rio.error and not rio.not_found)


def effective_rio_rating(a: Applicant, rio: RIOResult | None = None) -> int:
    """Use Raider.IO only: live profile, local character score, then RIO main score."""
    if _usable_rio(rio) and rio and rio.role_score > 0:
        return rio.role_score
    if _usable_rio(rio) and rio and rio.score > 0:
        return rio.score
    if _usable_rio(rio) and rio and use_season1_carryover(region=rio.region):
        if rio.previous_role_score > 0:
            return rio.previous_role_score
        if rio.previous_score > 0:
            return rio.previous_score
    return a.rio_score if a.rio_score > 0 else max(0, a.rio_main_score)


def _best_overall_key(a: Applicant, rio: RIOResult | None = None) -> int:
    online = rio.best_key if _usable_rio(rio) and rio else 0
    return max(online, a.rio_best_key)


def _same_dungeon_key(a: Applicant, rio: RIOResult | None = None) -> int:
    online = rio.best_dungeon_key if _usable_rio(rio) and rio else 0
    return max(online, a.rio_best_dungeon_key)


def _rio_has_evidence(a: Applicant, rio: RIOResult | None = None) -> bool:
    return bool(
        _same_dungeon_key(a, rio) > 0
        or a.rio_timed_at_or_above_minus2 > 0
        or (_usable_rio(rio) and rio and rio.recent_dungeon_runs > 0)
    )


def _dungeon_recent_score(rio: RIOResult | None, target: int) -> float:
    if not _usable_rio(rio) or not rio or rio.recent_dungeon_runs <= 0:
        return 0.0
    targetish = max(0, rio.recent_dungeon_targetish)
    timed = max(0, rio.recent_dungeon_timed)
    runs = max(0, rio.recent_dungeon_runs)
    return _clamp(min(targetish, 3) * 25.0 + min(timed, 4) * 5.0 + min(runs, 5) * 1.0)


def _rio_role_evidence_score(rio: RIOResult | None, fallback: float) -> float:
    """How strongly Raider.IO confirms the applicant in the queued role.

    Raider.IO publishes both all-role and per-role Mythic+ scores. The ratio is
    season-independent and answers a useful question the raw rating alone does
    not: was the score actually earned in the role the applicant is offering?
    When live role data is unavailable, use the exact-dungeon evidence instead
    of penalising a player for an API omission.
    """
    if not _usable_rio(rio) or not rio:
        return _clamp(fallback)
    overall = max(0, int(rio.score or 0))
    role_score = max(0, int(rio.role_score or 0))
    if overall <= 0:
        return _clamp(fallback)
    if role_score <= 0 and not rio.role_score_available:
        return _clamp(fallback)
    return _clamp(100.0 * role_score / max(overall, role_score, 1))


def _rio_target_base_run_score(target: int) -> float:
    """Official on-time Raider.IO run-score baseline for the target key.

    Raider.IO's published table currently covers +2 through +30. Above +30 we
    continue the documented +15-point high-key step only as a defensive runtime
    fallback; normal current-season keys resolve directly from the table.
    """
    target = int(target or 0)
    if target in RIO_BASE_RUN_SCORE_BY_KEY:
        return RIO_BASE_RUN_SCORE_BY_KEY[target]
    if target > 30:
        return RIO_BASE_RUN_SCORE_BY_KEY[30] + 15.0 * (target - 30)
    return 0.0


def _rio_official_run_score_component(
    rio: RIOResult | None, target: int, fallback_key_score: float
) -> float:
    """Normalize Raider.IO's own best exact-dungeon run score to 0..100.

    A run scoring exactly the published on-time baseline for the requested key
    maps to 94/100. This leaves a small amount of headroom for a faster run or a
    stronger key while preserving Raider.IO's own key/timer weighting.
    """
    if not _usable_rio(rio) or not rio or rio.best_dungeon_run_score <= 0:
        return _clamp(fallback_key_score)
    baseline = _rio_target_base_run_score(target)
    if baseline <= 0:
        return _clamp(fallback_key_score)
    return _clamp(94.0 * float(rio.best_dungeon_run_score) / baseline, 5.0, 100.0)


def rio_subscore(a: Applicant, listing: Listing | None, rio: RIOResult | None = None) -> float:
    """0..100 Raider.IO half for this dungeon and the applicant's queued role.

    70% is Raider.IO's own highest-scoring known run in this exact dungeon,
    normalized against Raider.IO's published on-time score for the requested
    key. That official run score already encodes both key strength and timing.
    The remaining 30% rewards repeat evidence in the same dungeon and confirms
    that the season score was actually earned in the applicant's queued role.
    """
    target = listing.key_level if listing else 0
    same_key = _same_dungeon_key(a, rio)

    key_fallback = _key_fit(same_key, target) if same_key > 0 and target > 0 else 0.0
    official_run = _rio_official_run_score_component(rio, target, key_fallback)
    recent = _dungeon_recent_score(rio, target)
    role_evidence = _rio_role_evidence_score(rio, official_run)

    return _clamp(
        0.70 * official_run
        + 0.20 * recent
        + 0.10 * role_evidence
    )


def _bracket_percentile(bracket: WCLBracket | None) -> float | None:
    if not bracket:
        return None
    # The visible WCL number is explicitly an average. For multiple parses use
    # the arithmetic mean of the selected dungeon/key bracket; with one parse
    # the single available percentile is the average by definition.
    value = bracket.average_percentile if bracket.run_count >= 2 else bracket.best_percentile
    return _clamp(float(value))


def wcl_metric_scores(a: Applicant, wcl: WCLResult | None) -> list[tuple[str, float]]:
    """All usable Warcraft Logs percentile metrics for the current dungeon.

    WCLResult.bracket contains playerscore. metric_brackets contains every other
    ranking metric returned by the client (speed, role throughput, DPS, ...).
    All usable metrics remain visible; correlated metrics are grouped before the final role-aware average.
    """
    if not wcl or wcl.error or wcl.not_found:
        return []

    values: list[tuple[str, float]] = []
    primary = _bracket_percentile(wcl.bracket)
    if primary is not None:
        values.append(("playerscore", primary))
    for metric_name in sorted(wcl.metric_brackets):
        value = _bracket_percentile(wcl.metric_brackets.get(metric_name))
        if value is not None:
            values.append((metric_name, value))
    return values


def wcl_subscore(a: Applicant, wcl: WCLResult | None) -> float | None:
    """Role-aware arithmetic mean built from all usable WCL evidence.

    Highly correlated throughput metrics are first averaged into one throughput
    category so DPS is not accidentally counted three times just because WCL
    exposes DPS, boss DPS and weighted DPS separately. The final WCL number is
    the arithmetic mean of stable WCL ranking categories, keeping the visible
    0..100 value fast, deterministic and understandable. Expensive raw-report
    event scans deliberately do not block or alter the applicant ranking.
    """
    values = dict(wcl_metric_scores(a, wcl))
    if not values:
        return None

    categories: list[float] = []
    for primary in ("playerscore", "playerspeed"):
        if primary in values:
            categories.append(values[primary])

    if a.spec_id in HEALER_SPECS:
        healing = [values[k] for k in ("hps", "tankhps") if k in values]
        if healing:
            categories.append(sum(healing) / len(healing))
        damage = [values[k] for k in ("dps", "bossdps") if k in values]
        if damage:
            categories.append(sum(damage) / len(damage))
    else:
        throughput = [values[k] for k in ("wdps", "dps", "bossdps") if k in values]
        if throughput:
            categories.append(sum(throughput) / len(throughput))

    return _clamp(sum(categories) / len(categories)) if categories else None


def calculate_score(
    a: Applicant,
    listing: Listing | None,
    wcl: WCLResult | None,
    rio: RIOResult | None = None,
) -> ScoreBreakdown:
    """Final KL Score = exactly 50% Raider.IO + 50% Warcraft Logs.

    Missing WCL evidence contributes 0 until public WCL data is found; it is
    never silently replaced by unrelated signals.
    """
    target = listing.key_level if listing else 0
    rio_score = rio_subscore(a, listing, rio)
    wcl_score = wcl_subscore(a, wcl)
    wcl_value = wcl_score if wcl_score is not None else 0.0
    combined = int(round(_clamp(BASE_RIO_WEIGHT * rio_score + BASE_WCL_WEIGHT * wcl_value)))
    label = "TOP" if combined >= 85 else "STRONG" if combined >= 70 else "OK" if combined >= 55 else "LOW"

    metric_brackets = list(wcl.metric_brackets.values()) if wcl else []
    bracket = wcl.bracket if wcl else None
    context_bracket = bracket or (metric_brackets[0] if metric_brackets else None)
    run_count = max([b.run_count for b in ([bracket] if bracket else []) + metric_brackets], default=0)
    same = _same_dungeon_key(a, rio)
    best = _best_overall_key(a, rio)
    has_rio = _rio_has_evidence(a, rio)
    if has_rio and wcl_score is not None and run_count >= 3:
        confidence = "high"
    elif has_rio and wcl_score is not None:
        confidence = "medium"
    else:
        confidence = "low"

    if wcl_score is not None:
        metrics = wcl_metric_scores(a, wcl)
        metric_names = ", ".join(name.upper() for name, _value in metrics)
        carryover = bool(
            wcl
            and listing
            and is_season1_carryover_source(listing.dungeon_name, wcl.source_season)
        )
        context = (
            " from Midnight Season 1 carry-over"
            if carryover
            else " in this dungeon" if context_bracket else ""
        )
        wcl_text = (
            f"WCL average {wcl_score:.0f}/100{context} "
            f"({run_count} parse{'s' if run_count != 1 else ''}; {metric_names or '1 metric'})"
        )
    else:
        wcl_text = "no public WCL ranking: WCL half 0/100"

    if has_rio:
        score_text = ""
        if _usable_rio(rio) and rio and rio.best_dungeon_run_score > 0:
            score_key = rio.best_dungeon_score_key or same
            score_text = f", best run +{score_key}"
        rio_text = f"RIO dungeon highest key +{same}{score_text}"
    else:
        rio_text = "no usable Raider.IO data"
    reason = f"{rio_text}; {wcl_text}; fixed weighting 50% RIO / 50% WCL"

    return ScoreBreakdown(
        score=combined,
        label=label,
        rio_score=rio_score,
        wcl_score=wcl_score,
        wcl_weight=BASE_WCL_WEIGHT,
        confidence=confidence,
        reason=reason,
        rio_effective=effective_rio_rating(a, rio),
        target_key=target,
        same_dungeon_key=same,
        best_key=best,
        wcl_bracket=bracket,
        rio_weight=BASE_RIO_WEIGHT,
        dungeon_score=None,
        dungeon_weight=0.0,
    )
