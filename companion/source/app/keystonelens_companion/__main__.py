from __future__ import annotations
import argparse
import ctypes
from dataclasses import replace
import os
import queue
import sys
import threading
import time
import traceback
from pathlib import Path
import tkinter as tk
from tkinter import messagebox

from . import __version__
from .addon_sync import TooltipCacheSync
from .config import Config, load_config, log_path, save_config
from .engine import ApplicantEngine, ranking_key
from .models import Applicant, ApplicantView, EngineState, Listing, PartyMember, WCLBracket, WCLResult
from .rio import RIOClient
from .scoring import calculate_score
from .ui import OverlayWindow, SetupDialog
from .watcher import ScreenshotWatcher
from .wcl import WCLCache, WCLClient


def _apply_windows_app_identity(root: tk.Tk) -> None:
    if os.name != "nt":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("KeystoneLens.Companion")
    except (AttributeError, OSError):
        pass
    icon_path = Path(__file__).resolve().parent.parent / "KeystoneLens.ico"
    if icon_path.exists():
        try:
            root.iconbitmap(default=str(icon_path))
        except tk.TclError:
            pass


class App:
    def __init__(self, demo: bool = False):
        self.cfg = load_config()
        self.root = tk.Tk()
        self.root.title("KeystoneLens Companion")
        _apply_windows_app_identity(self.root)
        self.root.report_callback_exception = self._tk_exception
        self.q: queue.Queue[tuple[str, object]] = queue.Queue()
        self.cache = WCLCache(ttl=self.cfg.cache_ttl_seconds)
        self.wcl: WCLClient | None = None
        self.rio = RIOClient()
        self.watcher: ScreenshotWatcher | None = None
        self._wcl_pending = False
        self._transport_status = ""
        self._tooltip_notice_until = 0.0
        self._tooltip_notice_generation = 0
        self.tooltip_sync = TooltipCacheSync(self.cfg.screenshots_path)
        self._preferences_save_job: str | None = None
        self._next_season_transition_check = 0.0
        self.engine = ApplicantEngine(None, lambda state: self.q.put(("state", state)), rio=self.rio)
        self.ui = OverlayWindow(
            self.root,
            self.open_settings,
            self.quit,
            self.save_position,
            self.save_height,
            cfg=self.cfg,
            on_preferences=self.save_preferences,
        )
        if self.cfg.overlay_height is not None:
            self.ui.set_user_height(self.cfg.overlay_height)
        if self.cfg.overlay_x is not None:
            self.ui.set_position(self.cfg.overlay_x, self.cfg.overlay_y)
        else:
            self.root.update_idletasks()
            self.ui.set_position(max(20, self.root.winfo_screenwidth() - self.ui.width - 20), 60)
        self.root.after(100, self._poll)
        if demo:
            self.root.after(250, self._demo)
        elif not self.cfg.ready:
            self.root.after(250, self.open_settings)
            self.ui.set_status("Choose the WoW Screenshots folder to start")
        else:
            self.start_runtime()


    def _tk_exception(self, exc_type, exc_value, exc_traceback) -> None:
        _write_crash_log(exc_type, exc_value, exc_traceback)
        try:
            messagebox.showerror(
                "KeystoneLens",
                f"Something went wrong. Details are in:\n{log_path()}",
                parent=self.root,
            )
        except tk.TclError:
            pass

    @staticmethod
    def _close_client_async(client) -> None:
        if client is None or not hasattr(client, "close"):
            return
        threading.Thread(target=client.close, daemon=True, name="KL-HTTP-Close").start()

    def start_runtime(self) -> None:
        old_wcl = self.wcl
        if self.watcher:
            self.watcher.stop()
            self.watcher = None
        if not self.cfg.ready:
            self.engine.set_wcl(None)
            self.wcl = None
            self._close_client_async(old_wcl)
            self.ui.set_status("Choose the WoW Screenshots folder to start")
            return
        self.wcl = None
        self._wcl_pending = False
        self._transport_status = ""
        self.engine.set_wcl(None)
        self._close_client_async(old_wcl)
        self.tooltip_sync = TooltipCacheSync(self.cfg.screenshots_path)
        self._tooltip_notice_generation += 1
        self._tooltip_notice_until = 0.0

        if self.cfg.wcl_configured:
            try:
                self.wcl = WCLClient(self.cfg.client_id, self.cfg.client_secret, self.cache)
                self.engine.set_wcl(self.wcl)
                current = self.wcl
                threading.Thread(target=self._check_wcl_auth, args=(current,), daemon=True,
                                 name="KL-WCLAuth").start()
            except Exception as exc:
                self.q.put(("status", f"WCL could not start: {exc}"))

        try:
            self.watcher = ScreenshotWatcher(
                Path(self.cfg.screenshots_path),
                self.engine.handle_snapshot,
                lambda status: self.q.put(("transport_status", status)),
            )
            self.watcher.start()
            mode = "Raider.IO live + WCL" if self.wcl else "Raider.IO live"
            self.ui.set_status(f"Active • {mode} • waiting for Group Finder players")
        except Exception as exc:
            self.ui.set_status(f"Startup error: {exc}")

    def _check_wcl_auth(self, client: WCLClient) -> None:
        try:
            client.test()
            if client is self.wcl:
                self.q.put(("status", "WCL connected • waiting for Group Finder players"))
        except Exception as exc:
            if client is self.wcl:
                self.q.put(("wcl_auth_failed", (client, str(exc))))

    def open_settings(self) -> None:
        SetupDialog(self.root, self.cfg, self._settings_saved)

    def _settings_saved(self, cfg: Config) -> bool:
        previous = self.cfg
        try:
            save_config(cfg)
        except (OSError, ValueError) as exc:
            self.ui.set_status(f"Settings could not be saved safely: {exc}")
            return False
        self.cfg = cfg
        self.cache.ttl = cfg.cache_ttl_seconds
        self.ui.apply_config(cfg)
        runtime_changed = any((
            previous.client_id != cfg.client_id,
            previous.client_secret != cfg.client_secret,
            previous.screenshots_path != cfg.screenshots_path,
            previous.cache_ttl_seconds != cfg.cache_ttl_seconds,
        ))
        if runtime_changed:
            self.start_runtime()
        return True

    def save_preferences(self, changes: dict[str, object]) -> None:
        allowed = {"score_min", "score_max", "class_filter_id", "role_filter"}
        clean = {key: value for key, value in changes.items() if key in allowed}
        if not clean:
            return
        self.cfg = replace(self.cfg, **clean)
        if self._preferences_save_job is not None:
            try:
                self.root.after_cancel(self._preferences_save_job)
            except tk.TclError:
                pass
        self._preferences_save_job = self.root.after(250, self._flush_preferences)

    def _flush_preferences(self) -> None:
        self._preferences_save_job = None
        try:
            save_config(self.cfg)
        except (OSError, ValueError) as exc:
            self.ui.set_status(f"Preferences could not be saved: {exc}")

    def save_position(self, x: int, y: int) -> None:
        candidate = replace(self.cfg, overlay_x=x, overlay_y=y)
        try:
            save_config(candidate)
        except (OSError, ValueError):
            return
        self.cfg = candidate

    def save_height(self, height: int) -> None:
        candidate = replace(self.cfg, overlay_height=int(height))
        try:
            save_config(candidate)
        except (OSError, ValueError):
            return
        self.cfg = candidate

    def _poll(self) -> None:
        try:
            now = time.monotonic()
            if now >= self._next_season_transition_check:
                self._next_season_transition_check = now + 30.0
                self.engine.refresh_season_transition()
            while True:
                kind, data = self.q.get_nowait()
                if kind == "state":
                    state: EngineState = data
                    self._wcl_pending = bool(
                        self.wcl is not None
                        and any(row.wcl_status in {"queued", "loading"} for row in state.rows)
                    )
                    prior_tooltip_write = self.tooltip_sync.last_written_at
                    tooltip_write_ok = self.tooltip_sync.write(list(state.rows))
                    if tooltip_write_ok and self.tooltip_sync.last_written_at > prior_tooltip_write:
                        self._tooltip_notice_generation += 1
                        notice_generation = self._tooltip_notice_generation
                        self._tooltip_notice_until = time.monotonic() + 8.0
                        self.root.after(8100, lambda g=notice_generation: self._expire_tooltip_notice(g))
                    published_status = state.status
                    if not tooltip_write_ok:
                        detail = self.tooltip_sync.last_error or "unknown write error"
                        published_status = f"Tooltip sync failed: {detail}"
                    self.ui.update_state(replace(state, status=self._status_text(published_status)))
                elif kind == "status":
                    self.ui.set_status(self._status_text(str(data)))
                elif kind == "transport_status":
                    self._transport_status = str(data)
                    self.ui.set_status(self._status_text(self._transport_status))
                elif kind == "wcl_auth_failed":
                    client, error = data
                    if client is self.wcl:
                        self.wcl = None
                        self._wcl_pending = False
                        self.engine.set_wcl(None)
                        self._close_client_async(client)
                        self.ui.set_status(self._status_text(
                            f"WCL connection failed: {error} • Raider.IO live remains active"
                        ))
        except queue.Empty:
            pass
        self.root.after(120, self._poll)

    def _status_text(self, base: str) -> str:
        """Keep transport diagnostics visible instead of hiding them behind WCL."""
        lower = base.casefold()
        actionable = (
            "error", "failed", "not found", "could not", "temporary", "temporarily",
            "retry", "startup error", "invalid", "no keystonelens qr",
            "fout", "mislukt", "niet gevonden", "kon niet", "tijdelijk", "ongeldig", "geen keystonelens-qr",
        )
        if any(token in lower for token in actionable):
            return base
        if lower.startswith("transport •"):
            return base
        if self._transport_status:
            transport_lower = self._transport_status.casefold()
            if any(token in transport_lower for token in actionable):
                return self._transport_status
        if self._wcl_pending:
            return "Warcraft Logs loading…"
        if time.monotonic() < self._tooltip_notice_until:
            return "Tooltip updated → /reload"
        if self.cfg.wcl_configured:
            if not self.wcl:
                return "Raider.IO live active • Warcraft Logs not connected"
            if self.wcl.last_quota:
                spent, limit, reset = self.wcl.last_quota
                if limit and spent / limit >= .9:
                    return f"Warcraft Logs connected • limit {int(spent)}/{int(limit)} • reset {int(reset // 60)}m"
            return "Warcraft Logs connected"
        return "Raider.IO live active • WCL not configured (WCL half 0/100)"

    def _expire_tooltip_notice(self, generation: int) -> None:
        if generation != self._tooltip_notice_generation:
            return
        if time.monotonic() < self._tooltip_notice_until:
            return
        state = self.ui.state
        if state is not None:
            self.ui.set_status(self._status_text(state.status))

    def _demo(self) -> None:
        listing = Listing(activity_id=404, key_level=16, dungeon_name="Skyreach", listing_name="+16")
        samples = [
            ("Valgoror-KirinTor", 71, 2, 3347, 17, 16, 8, 88, 82, 6),
            ("Emptystar-Draenor", 258, 2, 3337, 16, 15, 6, 72, 69, 4),
            ("Stonewall-TarrenMill", 73, 0, 3290, 17, 16, 8, 64, 61, 5),
            ("Bloomwell-Area52", 264, 1, 2740, 16, 15, 5, 83, 78, 3),
            ("Riskyone-Silvermoon", 266, 2, 3010, 15, 13, 4, 44, 39, 1),
            ("Fastmage-TwistingNether", 64, 2, 3200, 16, 16, 6, 79, 76, 5),
        ]
        rows: list[ApplicantView] = []
        for i, (name, spec, role, rio, best, same, coverage, best_pct, median_pct, n) in enumerate(samples, 1):
            applicant = Applicant(
                i, 1, 1, spec, 680, rio, 0, role, name, True, best, same,
                2, 4, 7, 4, coverage, application_member_count=1,
                blizzard_score=rio - 25, blizzard_best_dungeon_key=same, blizzard_best_key=best,
            )
            char, realm = name.split("-", 1)
            wcl = WCLResult(
                char, realm, "Skyreach", spec,
                WCLBracket(0, best_pct, median_pct, n, median_pct), time.time(), target_key=16,
            )
            view = ApplicantView(applicant, listing, "EU", wcl, "ready", revision=1, rio_status="ready")
            view.score = calculate_score(applicant, listing, wcl)
            rows.append(view)
        rows.sort(key=ranking_key)
        party = (PartyMember(
            1, 1, 1, 2, 66, 682, 3250, 0, 0, "Jij-Silvermoon",
            True, 17, 16, 2, 4, 7, 4, 8,
        ),)
        state = EngineState(
            listing=listing, rows=tuple(rows), party=party,
            status="Demo • one live player ranking", revision=1,
        )
        self.ui.update_state(state)

    def quit(self) -> None:
        if self._preferences_save_job is not None:
            try:
                self.root.after_cancel(self._preferences_save_job)
            except tk.TclError:
                pass
            self._preferences_save_job = None
            try:
                save_config(self.cfg)
            except (OSError, ValueError):
                pass
        if self.watcher:
            self.watcher.stop()
            self.watcher = None
        # Signal network clients before joining workers. Their closed flags stop
        # retries/rate-limit waits immediately and engine workers reject any late
        # result after the stop boundary. This keeps shutdown deterministic even
        # when an HTTP lookup is active.
        if self.wcl is not None:
            self.wcl.close()
            self.wcl = None
        self.rio.close()
        self.engine.stop()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def _enable_dpi_awareness() -> None:
    if os.name != "nt":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


MAX_CRASH_LOG_BYTES = 1_048_576
CRASH_LOG_TAIL_BYTES = 262_144


def _write_crash_log(exc_type, exc_value, exc_traceback) -> None:
    try:
        path = log_path()
        if path.exists() and path.stat().st_size > MAX_CRASH_LOG_BYTES:
            raw = path.read_bytes()[-CRASH_LOG_TAIL_BYTES:]
            path.write_text(raw.decode("utf-8", errors="replace"), encoding="utf-8")
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"\n[{stamp}] [FATAL] KeystoneLens {__version__} Companion fatal/callback error\n{text}")
    except OSError:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="KeystoneLens Mythic+ LFG companion")
    parser.add_argument("--demo", action="store_true", help="toon de UI met testdata")
    args = parser.parse_args()
    _enable_dpi_awareness()
    try:
        App(demo=args.demo).run()
    except tk.TclError as exc:
        _write_crash_log(type(exc), exc, exc.__traceback__)
        print(f"KeystoneLens UI could not start: {exc}", file=sys.stderr)
        raise SystemExit(2)
    except Exception as exc:
        _write_crash_log(type(exc), exc, exc.__traceback__)
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("KeystoneLens", f"KeystoneLens could not start. Details are in:\n{log_path()}", parent=root)
            root.destroy()
        except tk.TclError:
            pass
        raise SystemExit(1)


if __name__ == "__main__":
    main()
