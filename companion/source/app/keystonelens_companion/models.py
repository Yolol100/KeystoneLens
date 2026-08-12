from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .rio import RIOResult


@dataclass(frozen=True)
class Listing:
    activity_id: int = 0
    key_level: int = 0
    dungeon_name: str = ""
    listing_name: str = ""
    comment: str = ""
    category_id: int = 0
    difficulty_id: int = 0


@dataclass(frozen=True)
class VersionInfo:
    addon_version: str = ""
    game_version: str = ""
    region_id: int = 3
    player_name: str = ""


@dataclass(frozen=True)
class Applicant:
    applicant_id: int
    member_idx: int
    class_id: int
    spec_id: int
    ilvl: int
    rio_score: int
    rio_main_score: int
    role_byte: int
    name: str
    rio_profile: bool = False
    rio_best_key: int = 0
    rio_best_dungeon_key: int = 0
    rio_timed_at_or_above: int = 0
    rio_timed_at_or_above_minus1: int = 0
    rio_timed_at_or_above_minus2: int = 0
    rio_completed_at_or_above_minus1: int = 0
    rio_dungeon_count: int = 0
    application_member_count: int = 1
    blizzard_score: int = 0
    blizzard_best_dungeon_key: int = 0
    blizzard_best_key: int = 0

    @property
    def identity(self) -> str:
        return f"{self.applicant_id}:{self.member_idx}"

    @property
    def application_identity(self) -> str:
        return str(self.applicant_id)


@dataclass(frozen=True)
class PartyMember:
    unit_index: int
    flags: int
    subgroup: int
    class_id: int
    spec_id: int
    ilvl: int
    rio_score: int
    rio_main_score: int
    role_byte: int
    name: str
    rio_profile: bool = False
    rio_best_key: int = 0
    rio_best_dungeon_key: int = 0
    rio_timed_at_or_above: int = 0
    rio_timed_at_or_above_minus1: int = 0
    rio_timed_at_or_above_minus2: int = 0
    rio_completed_at_or_above_minus1: int = 0
    rio_dungeon_count: int = 0

    @property
    def is_self(self) -> bool:
        return bool(self.flags & 0x01)

    @property
    def identity(self) -> str:
        return self.name.casefold()


@dataclass(frozen=True)
class Snapshot:
    listing: Optional[Listing]
    version: Optional[VersionInfo]
    applicants: tuple[Applicant, ...]
    party: tuple[PartyMember, ...] = ()
    # 1..255 listing-instance marker emitted by the Bridge. 0 means an older
    # Bridge that predates this marker. The marker lets the Companion separate
    # two consecutive LFG listings even when dungeon/key/title are identical.
    listing_generation: int = 0
    terminal_clear: bool = False
    lfg_unavailable: bool = False
    roster_unavailable: bool = False
    applicants_unavailable: bool = False


@dataclass(frozen=True)
class WCLBracket:
    key_level: int
    best_percentile: float
    median_percentile: float
    run_count: int
    average_percentile: float = 0.0


@dataclass(frozen=True)
class WCLResult:
    name: str
    realm: str
    dungeon_name: str
    spec_id: int
    bracket: Optional[WCLBracket]
    fetched_at: float
    target_key: int = 0
    not_found: bool = False
    error: str = ""
    quota_spent: float | None = None
    quota_limit: float | None = None
    quota_reset: float | None = None
    metric_brackets: dict[str, WCLBracket] = field(default_factory=dict)


@dataclass(frozen=True)
class ScoreBreakdown:
    score: int
    label: str
    rio_score: float
    wcl_score: float | None
    wcl_weight: float
    confidence: str
    reason: str
    rio_effective: int
    target_key: int
    same_dungeon_key: int
    best_key: int
    wcl_bracket: Optional[WCLBracket] = None
    rio_weight: float = 0.0
    dungeon_score: float | None = None
    dungeon_weight: float = 0.0


@dataclass
class ApplicantView:
    applicant: Applicant
    snapshot_listing: Optional[Listing]
    region: str
    wcl: Optional[WCLResult] = None
    wcl_status: str = "queued"
    score: Optional[ScoreBreakdown] = None
    updated_at: float = 0.0
    revision: int = 0
    rio: Optional["RIOResult"] = None
    rio_status: str = "queued"


@dataclass(frozen=True)
class EngineState:
    listing: Optional[Listing]
    rows: tuple[ApplicantView, ...]
    party: tuple[PartyMember, ...]
    status: str
    revision: int = 0
    lfg_unavailable: bool = False
    applicants_unavailable: bool = False
    roster_unavailable: bool = False
