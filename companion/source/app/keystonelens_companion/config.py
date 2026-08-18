from __future__ import annotations
from dataclasses import dataclass, asdict
import base64
import binascii
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
from typing import Any

from .filters import DEFAULT_SCORE_MAX, DEFAULT_SCORE_MIN

APP_DIR_NAME = "KeystoneLens"
_PROTECTED_SECRET_KEY = "client_secret_protected"
_DPAPI_PREFIX = "dpapi:v1:"
DEFAULT_CACHE_TTL_SECONDS = 43200
MIN_CACHE_TTL_SECONDS = 300
MAX_CACHE_TTL_SECONDS = 7 * 24 * 60 * 60
MAX_CONFIG_FILE_BYTES = 1 * 1024 * 1024


@dataclass
class Config:
    client_id: str = ""
    client_secret: str = ""
    screenshots_path: str = ""
    cache_ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS
    overlay_x: int | None = None
    overlay_y: int | None = None
    overlay_height: int | None = None
    score_min: int = DEFAULT_SCORE_MIN
    score_max: int = DEFAULT_SCORE_MAX
    class_filter_id: int | None = None
    role_filter: str = ""
    show_role: bool = True
    show_class: bool = True
    show_spec: bool = True
    show_rio: bool = True
    show_wcl: bool = True

    @property
    def ready(self) -> bool:
        """The core Raider.IO overlay only needs the WoW screenshot directory."""
        return bool(self.screenshots_path.strip())

    @property
    def wcl_configured(self) -> bool:
        return bool(self.client_id.strip() and self.client_secret.strip())


def local_app_dir() -> Path:
    root = os.environ.get("LOCALAPPDATA")
    p = Path(root) / APP_DIR_NAME if root else Path.home() / ".keystonelens"
    p.mkdir(parents=True, exist_ok=True)
    return p


def config_path() -> Path:
    return local_app_dir() / "config.json"


def cache_path() -> Path:
    return local_app_dir() / "wcl-cache.json"


def log_path() -> Path:
    return local_app_dir() / "keystonelens.log"


def _dpapi_transform(data: bytes, *, protect: bool) -> bytes:
    """Protect/unprotect bytes with the current Windows user's DPAPI key."""
    if os.name != "nt":
        raise OSError("Windows DPAPI is only available on Windows")

    class DataBlob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

    crypt32 = ctypes.WinDLL("Crypt32.dll", use_last_error=True)
    kernel32 = ctypes.WinDLL("Kernel32.dll", use_last_error=True)
    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(DataBlob), wintypes.LPCWSTR, ctypes.POINTER(DataBlob),
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DataBlob),
    ]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(DataBlob), ctypes.c_void_p, ctypes.POINTER(DataBlob),
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DataBlob),
    ]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p

    input_buffer = ctypes.create_string_buffer(data or b"\0")
    input_blob = DataBlob(len(data), ctypes.cast(input_buffer, ctypes.POINTER(ctypes.c_byte)))
    output_blob = DataBlob()
    flags = 0x01  # CRYPTPROTECT_UI_FORBIDDEN
    if protect:
        ok = crypt32.CryptProtectData(
            ctypes.byref(input_blob), "KeystoneLens WCL Client Secret", None,
            None, None, flags, ctypes.byref(output_blob),
        )
    else:
        ok = crypt32.CryptUnprotectData(
            ctypes.byref(input_blob), None, None, None, None, flags, ctypes.byref(output_blob),
        )
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        if output_blob.pbData:
            kernel32.LocalFree(ctypes.cast(output_blob.pbData, ctypes.c_void_p))


def _protect_secret(secret: str) -> str:
    protected = _dpapi_transform(secret.encode("utf-8"), protect=True)
    return _DPAPI_PREFIX + base64.b64encode(protected).decode("ascii")


def _unprotect_secret(value: str) -> str:
    if not value.startswith(_DPAPI_PREFIX):
        raise ValueError("unsupported protected-secret format")
    raw = base64.b64decode(value[len(_DPAPI_PREFIX):], validate=True)
    return _dpapi_transform(raw, protect=False).decode("utf-8")


def _clean_text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _clean_optional_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return max(-100000, min(100000, value))
    if isinstance(value, float) and value.is_integer():
        return max(-100000, min(100000, int(value)))
    return None


def _clean_ttl(value: Any) -> int:
    if isinstance(value, bool):
        return DEFAULT_CACHE_TTL_SECONDS
    try:
        ttl = int(value)
    except (TypeError, ValueError, OverflowError):
        return DEFAULT_CACHE_TTL_SECONDS
    if ttl < MIN_CACHE_TTL_SECONDS or ttl > MAX_CACHE_TTL_SECONDS:
        return DEFAULT_CACHE_TTL_SECONDS
    return ttl


def _clean_bool(value: Any, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if value in (0, 1):
        return bool(value)
    return default


def _clean_score(value: Any, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        score = int(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return max(0, min(100, score))


def _clean_class_filter(value: Any) -> int | None:
    class_id = _clean_optional_int(value)
    return class_id if class_id is not None and 1 <= class_id <= 13 else None


def _clean_role_filter(value: Any) -> str:
    role = _clean_text(value).strip().upper()
    return role if role in {"TANK", "HEALER", "DPS"} else ""


def _normalize_config(raw: dict[str, Any]) -> Config:
    score_min = _clean_score(raw.get("score_min", DEFAULT_SCORE_MIN), DEFAULT_SCORE_MIN)
    score_max = _clean_score(raw.get("score_max", DEFAULT_SCORE_MAX), DEFAULT_SCORE_MAX)
    if score_min > score_max:
        score_min, score_max = score_max, score_min
    return Config(
        client_id=_clean_text(raw.get("client_id")),
        client_secret=_clean_text(raw.get("client_secret")),
        screenshots_path=_clean_text(raw.get("screenshots_path")),
        cache_ttl_seconds=_clean_ttl(raw.get("cache_ttl_seconds", DEFAULT_CACHE_TTL_SECONDS)),
        overlay_x=_clean_optional_int(raw.get("overlay_x")),
        overlay_y=_clean_optional_int(raw.get("overlay_y")),
        overlay_height=_clean_optional_int(raw.get("overlay_height")),
        score_min=score_min,
        score_max=score_max,
        class_filter_id=_clean_class_filter(raw.get("class_filter_id")),
        role_filter=_clean_role_filter(raw.get("role_filter")),
        show_role=_clean_bool(raw.get("show_role"), True),
        show_class=_clean_bool(raw.get("show_class"), True),
        show_spec=_clean_bool(raw.get("show_spec"), True),
        show_rio=_clean_bool(raw.get("show_rio"), True),
        show_wcl=_clean_bool(raw.get("show_wcl"), True),
    )


def _atomic_write_config(path: Path, data: dict[str, Any]) -> None:
    """Replace config.json only after a complete temporary JSON file exists."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _config_payload(cfg: Config) -> dict[str, Any]:
    # Normalize even programmatic callers so malformed state never becomes the
    # persistent source of truth.
    safe = _normalize_config(asdict(cfg))
    data = asdict(safe)
    secret = data.pop("client_secret", "")
    if secret and os.name == "nt":
        data[_PROTECTED_SECRET_KEY] = _protect_secret(secret)
    # KeystoneLens is a Windows product. On unsupported source/demo hosts the
    # in-memory secret is never written back in plaintext.
    return data


def _scrub_persisted_secret(path: Path, cfg: Config) -> None:
    """Remove every persisted secret field without needing DPAPI to succeed."""
    safe = _normalize_config(asdict(cfg))
    safe.client_secret = ""
    data = asdict(safe)
    data.pop("client_secret", None)
    data.pop(_PROTECTED_SECRET_KEY, None)
    _atomic_write_config(path, data)


def load_config() -> Config:
    path = config_path()
    if not path.exists():
        return Config(screenshots_path=autodetect_screenshots_path())
    try:
        if path.stat().st_size > MAX_CONFIG_FILE_BYTES:
            raise ValueError("config file is too large")
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("config root is not an object")

        # DPAPI is authoritative whenever present. Plaintext `client_secret` is
        # accepted only as a one-way legacy migration input and is removed from
        # disk during this load.
        had_plaintext_secret_field = "client_secret" in raw
        protected = raw.get(_PROTECTED_SECRET_KEY)
        protected_present = isinstance(protected, str) and bool(protected)
        if protected_present:
            try:
                raw["client_secret"] = _unprotect_secret(protected)
            except (OSError, ValueError, UnicodeDecodeError, binascii.Error):
                # Never fall back to a stray legacy plaintext field when a DPAPI
                # value exists but cannot be authenticated/decrypted.
                raw["client_secret"] = ""
        elif os.name != "nt":
            # Unsupported source/demo hosts must not activate a credential that
            # was found in an old plaintext config file.
            raw["client_secret"] = ""

        cfg = _normalize_config(raw)
        if not cfg.screenshots_path:
            cfg.screenshots_path = autodetect_screenshots_path()

        if had_plaintext_secret_field:
            try:
                if os.name == "nt" and cfg.client_secret:
                    # Successful legacy migration: protect for the current user
                    # and atomically replace the old plaintext file.
                    _atomic_write_config(path, _config_payload(cfg))
                elif os.name == "nt" and protected_present:
                    # DPAPI remains authoritative; rewrite to remove a stale
                    # duplicate plaintext field (or remove both if DPAPI failed).
                    if cfg.client_secret:
                        _atomic_write_config(path, _config_payload(cfg))
                    else:
                        _scrub_persisted_secret(path, cfg)
                else:
                    # No safe DPAPI destination is available. Fail closed by
                    # removing the legacy secret from disk and memory.
                    cfg.client_secret = ""
                    _scrub_persisted_secret(path, cfg)
            except (OSError, ValueError):
                # If protection itself fails, do not keep using a secret that is
                # still persisted in plaintext. Best-effort scrub it without
                # encryption; a read-only/locked file may still require the user
                # to re-save settings after permissions are corrected.
                cfg.client_secret = ""
                try:
                    _scrub_persisted_secret(path, cfg)
                except OSError:
                    pass
        return cfg
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return Config(screenshots_path=autodetect_screenshots_path())


def save_config(cfg: Config) -> None:
    _atomic_write_config(config_path(), _config_payload(cfg))


def autodetect_screenshots_path() -> str:
    candidates: list[Path] = []
    for base in [
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramFiles(x86)"),
        r"C:\Program Files (x86)",
        r"C:\Program Files",
    ]:
        if base:
            candidates.append(Path(base) / "World of Warcraft" / "_retail_" / "Screenshots")
    candidates.append(Path(r"C:\Games\World of Warcraft\_retail_\Screenshots"))

    # Autodetection is only safe when it is unambiguous. If multiple known
    # Retail installations exist, require the user to select the intended
    # Screenshots folder instead of silently picking the first candidate.
    found: dict[str, Path] = {}
    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            key = os.path.normcase(os.path.abspath(str(candidate)))
            found.setdefault(key, candidate)
    if len(found) == 1:
        return str(next(iter(found.values())))
    return ""
