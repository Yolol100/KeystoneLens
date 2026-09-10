from __future__ import annotations

from collections.abc import Iterable

from .constants import CLASS_NAMES, ROLE_NAMES, SPEC_NAMES
from .models import ApplicantView

SCORE_MIN = 0
SCORE_MAX = 100
DEFAULT_SCORE_MIN = 84
DEFAULT_SCORE_MAX = 100
ROLE_FILTERS = ("TANK", "HEALER", "DPS")
SORT_KEYS = ("score", "role", "player", "class", "spec", "rio", "wcl")
DEFAULT_SORT_KEY = "score"
DEFAULT_SORT_DESC = True
MAX_SEARCH_CHARS = 80


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


def normalize_spec_filter(value: int | None) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        spec_id = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return spec_id if spec_id in SPEC_NAMES else None


def normalize_role_filter(value: str | None) -> str:
    role = str(value or "").strip().upper()
    return role if role in ROLE_FILTERS else ""


def normalize_search_query(value: object) -> str:
    if not isinstance(value, str):
        return ""
    # One compact line is enough for applicant/class/spec matching and prevents
    # pasted control characters from becoming persistent UI state.
    clean = " ".join(value.split()).strip()
    return clean[:MAX_SEARCH_CHARS]


def normalize_sort_key(value: object) -> str:
    key = str(value or "").strip().casefold()
    return key if key in SORT_KEYS else DEFAULT_SORT_KEY


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
    Class, role, spec and text filters still apply normally.
    """
    return view.rio_status == "error" or view.wcl_status == "error"


def _matches_search(view: ApplicantView, query: str) -> bool:
    if not query:
        return True
    applicant = view.applicant
    haystack = " ".join((
        applicant.name,
        CLASS_NAMES.get(applicant.class_id, ""),
        SPEC_NAMES.get(applicant.spec_id, ""),
        ROLE_NAMES.get(applicant.role_byte, "DPS"),
    )).casefold()
    return query.casefold() in haystack


def filter_rows(
    rows: Iterable[ApplicantView],
    *,
    score_min: int = DEFAULT_SCORE_MIN,
    score_max: int = DEFAULT_SCORE_MAX,
    class_id: int | None = None,
    role: str = "",
    spec_id: int | None = None,
    search_query: str = "",
) -> list[ApplicantView]:
    """Apply overlay filters without mutating source ranking order or row state."""
    low, high = normalize_score_range(score_min, score_max)
    selected_class = normalize_class_filter(class_id)
    selected_role = normalize_role_filter(role)
    selected_spec = normalize_spec_filter(spec_id)
    query = normalize_search_query(search_query)
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
        if selected_spec is not None and view.applicant.spec_id != selected_spec:
            continue
        if not _matches_search(view, query):
            continue
        out.append(view)
    return out


def _sort_value(view: ApplicantView, sort_key: str):
    applicant = view.applicant
    score = view.score
    if sort_key == "score":
        return int(score.score) if score is not None else None
    if sort_key == "rio":
        return int(score.rio_effective) if score is not None else None
    if sort_key == "wcl":
        return float(score.wcl_score) if score is not None and score.wcl_score is not None else None
    if sort_key == "role":
        return ROLE_NAMES.get(applicant.role_byte, "DPS").casefold()
    if sort_key == "player":
        return applicant.name.split("-", 1)[0].casefold()
    if sort_key == "class":
        return CLASS_NAMES.get(applicant.class_id, "").casefold()
    if sort_key == "spec":
        return SPEC_NAMES.get(applicant.spec_id, "").casefold()
    return None


def sort_rows(
    rows: Iterable[ApplicantView],
    *,
    sort_key: str = DEFAULT_SORT_KEY,
    sort_desc: bool = DEFAULT_SORT_DESC,
) -> list[ApplicantView]:
    """Stable user-facing sort with missing provider values always last."""
    key = normalize_sort_key(sort_key)
    known: list[tuple[object, ApplicantView]] = []
    missing: list[ApplicantView] = []
    for view in rows:
        value = _sort_value(view, key)
        if value is None:
            missing.append(view)
        else:
            known.append((value, view))
    known.sort(key=lambda item: item[0], reverse=bool(sort_desc))
    return [view for _value, view in known] + missing


def unique_spec_rows(rows: Iterable[ApplicantView], *, enabled: bool = False) -> list[ApplicantView]:
    """Keep the first sorted applicant per known spec while preserving error diagnostics.

    Source-error rows remain visible even if another applicant of the same spec is
    already present. This preserves KeystoneLens' fail-visible provider behavior;
    healthy rows still obey one-row-per-spec exactly.
    """
    values = list(rows)
    if not enabled:
        return values
    seen: set[int] = set()
    out: list[ApplicantView] = []
    for view in values:
        spec_id = normalize_spec_filter(view.applicant.spec_id)
        if spec_id is None:
            out.append(view)
            continue
        if has_source_error(view):
            out.append(view)
            continue
        if spec_id in seen:
            continue
        seen.add(spec_id)
        out.append(view)
    return out


def prepare_rows(
    rows: Iterable[ApplicantView],
    *,
    score_min: int = DEFAULT_SCORE_MIN,
    score_max: int = DEFAULT_SCORE_MAX,
    class_id: int | None = None,
    role: str = "",
    spec_id: int | None = None,
    search_query: str = "",
    sort_key: str = DEFAULT_SORT_KEY,
    sort_desc: bool = DEFAULT_SORT_DESC,
    unique_specs: bool = False,
) -> list[ApplicantView]:
    """Compose filtering, sorting and optional one-applicant-per-spec presentation."""
    filtered = filter_rows(
        rows,
        score_min=score_min,
        score_max=score_max,
        class_id=class_id,
        role=role,
        spec_id=spec_id,
        search_query=search_query,
    )
    ordered = sort_rows(filtered, sort_key=sort_key, sort_desc=sort_desc)
    return unique_spec_rows(ordered, enabled=bool(unique_specs))
