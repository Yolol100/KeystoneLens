from __future__ import annotations

from dataclasses import asdict, dataclass
import base64
import binascii
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
from typing import Any

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

    @property
    def ready(self) -> bool:
        return bool(self.screenshots_path.strip())

    @property
    def wcl_configured(self) -> bool:
        return bool(self.client_id.strip() and self.client_secret.strip())


def local_app_dir() -> Path:
    root = os.environ.get("LOCALAPPDATA")
    path = Path(root) / APP_DIR_NAME if root else Path.home() / ".keystonelens"
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path() -> Path:
    return local_app_dir() / "config.json"


def cache_path() -> Path:
    return local_app_dir() / "wcl-cache-prod55.json"


def log_path() -> Path:
    return local_app_dir() / "keystonelens.log"


def _is_windows() -> bool:
    return os.name == "nt"


def _dpapi_transform(data: bytes, *, protect: bool) -> bytes:
    if not _is_windows():
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
    flags = 0x01
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


def _normalize_config(raw: dict[str, Any]) -> Config:
    return Config(
        client_id=_clean_text(raw.get("client_id")),
        client_secret=_clean_text(raw.get("client_secret")),
        screenshots_path=_clean_text(raw.get("screenshots_path")),
        cache_ttl_seconds=_clean_ttl(raw.get("cache_ttl_seconds", DEFAULT_CACHE_TTL_SECONDS)),
    )


def _atomic_write_config(path: Path, data: dict[str, Any]) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _config_payload(cfg: Config) -> dict[str, Any]:
    safe = _normalize_config(asdict(cfg))
    data = asdict(safe)
    secret = data.pop("client_secret", "")
    if secret and _is_windows():
        data[_PROTECTED_SECRET_KEY] = _protect_secret(secret)
    return data


def _scrub_persisted_secret(path: Path, cfg: Config) -> None:
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

        had_plaintext_secret = "client_secret" in raw
        protected = raw.get(_PROTECTED_SECRET_KEY)
        protected_present = isinstance(protected, str) and bool(protected)
        windows = _is_windows()

        if protected_present:
            try:
                raw["client_secret"] = _unprotect_secret(protected)
            except (OSError, ValueError, UnicodeDecodeError, binascii.Error):
                raw["client_secret"] = ""
        elif not windows:
            raw["client_secret"] = ""

        cfg = _normalize_config(raw)
        if not cfg.screenshots_path:
            cfg.screenshots_path = autodetect_screenshots_path()

        if had_plaintext_secret:
            try:
                if windows and cfg.client_secret:
                    _atomic_write_config(path, _config_payload(cfg))
                elif windows and protected_present and cfg.client_secret:
                    _atomic_write_config(path, _config_payload(cfg))
                else:
                    cfg.client_secret = ""
                    _scrub_persisted_secret(path, cfg)
            except (OSError, ValueError):
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

    found: dict[str, Path] = {}
    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            key = os.path.normcase(os.path.abspath(str(candidate)))
            found.setdefault(key, candidate)
    return str(next(iter(found.values()))) if len(found) == 1 else ""
