from __future__ import annotations

from collections.abc import Iterable

from .constants import CLASS_NAMES, ROLE_NAMES
from .models import ApplicantView

SCORE_MIN = 0
SCORE_MAX = 100
DEFAULT_SCORE_MIN = 84
DEFAULT_SCORE_MAX = 100
ROLE_FILTERS = ("TANK", "HEALER", "DPS")


def normalize_score_range(minimum: int, maximum: int) -> tuple[int, int]:
    """Clamp a user range to the KL 0..100 domain and keep min <= max."""
    try:
        low = int(minimum)
    except (TypeError, ValueError, OverflowError):
        low = SCORE_MIN
    try:
        high = int(maximum)
    except (TypeError, ValueError, OverflowError):
        high = SCORE_MAX
    low = max(SCORE_MIN, min(SCORE_MAX, low))
    high = max(SCORE_MIN, min(SCORE_MAX, high))
    if low > high:
        low, high = high, low
    return low, high


def normalize_class_filter(value: int | None) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        class_id = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return class_id if class_id in CLASS_NAMES else None


def normalize_role_filter(value: str | None) -> str:
    role = str(value or "").strip().upper()
    return role if role in ROLE_FILTERS else ""


def has_final_score(view: ApplicantView) -> bool:
    return bool(
        view.score is not None
        and view.rio_status not in {"queued", "loading"}
        and view.wcl_status not in {"queued", "loading"}
    )


def has_source_error(view: ApplicantView) -> bool:
    """Return whether a finished row contains an online enrichment failure.

    Error rows must remain visible even when their temporary half-score falls
    below the user's score filter. Otherwise an API outage looks exactly like
    "no applicants", hiding the diagnostic the user needs to fix the source.
    Class and role filters still apply normally.
    """
    return view.rio_status == "error" or view.wcl_status == "error"


def filter_rows(
    rows: Iterable[ApplicantView],
    *,
    score_min: int = DEFAULT_SCORE_MIN,
    score_max: int = DEFAULT_SCORE_MAX,
    class_id: int | None = None,
    role: str = "",
) -> list[ApplicantView]:
    """Apply all overlay filters without mutating ranking order or row state."""
    low, high = normalize_score_range(score_min, score_max)
    selected_class = normalize_class_filter(class_id)
    selected_role = normalize_role_filter(role)
    out: list[ApplicantView] = []
    for view in rows:
        if not has_final_score(view) or view.score is None:
            continue
        # A failed source can make a normally strong applicant look artificially
        # weak (for example WCL error => its fixed 50% share is temporarily 0).
        # Keep that row visible so the red source error cannot be hidden by the
        # score slider. Once enrichment succeeds, the normal score range applies.
        if not has_source_error(view) and not (low <= int(view.score.score) <= high):
            continue
        if selected_class is not None and view.applicant.class_id != selected_class:
            continue
        if selected_role and ROLE_NAMES.get(view.applicant.role_byte, "DPS") != selected_role:
            continue
        out.append(view)
    return out
