from __future__ import annotations

import ctypes
import os
from pathlib import Path
import queue
import sys
import threading
import time
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox

from . import __version__
from .addon_sync import TooltipCacheSync
from .config import Config, load_config, log_path, save_config
from .engine import ApplicantEngine
from .models import EngineState
from .watcher import ScreenshotWatcher
from .wcl import WCLCache, WCLClient


class SettingsDialog(tk.Toplevel):
    def __init__(self, parent: tk.Tk, cfg: Config, on_save):
        super().__init__(parent)
        self.title("KeystoneLens Settings")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.on_save = on_save

        self.client_id = tk.StringVar(value=cfg.client_id)
        self.client_secret = tk.StringVar(value=cfg.client_secret)
        self.screenshots = tk.StringVar(value=cfg.screenshots_path)

        frame = tk.Frame(self, padx=14, pady=14)
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text="Warcraft Logs Client ID").grid(row=0, column=0, sticky="w")
        tk.Entry(frame, textvariable=self.client_id, width=48).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(2, 10))

        tk.Label(frame, text="Warcraft Logs Client Secret").grid(row=2, column=0, sticky="w")
        tk.Entry(frame, textvariable=self.client_secret, show="•", width=48).grid(row=3, column=0, columnspan=2, sticky="ew", pady=(2, 10))

        tk.Label(frame, text="WoW _retail_\\Screenshots map").grid(row=4, column=0, sticky="w")
        tk.Entry(frame, textvariable=self.screenshots, width=40).grid(row=5, column=0, sticky="ew", pady=(2, 10))
        tk.Button(frame, text="Kiezen", command=self._browse).grid(row=5, column=1, padx=(8, 0), pady=(2, 10))

        buttons = tk.Frame(frame)
        buttons.grid(row=6, column=0, columnspan=2, sticky="e")
        tk.Button(buttons, text="Annuleren", command=self.destroy).pack(side="right")
        tk.Button(buttons, text="Opslaan", command=self._save).pack(side="right", padx=(0, 8))

    def _browse(self) -> None:
        value = filedialog.askdirectory(parent=self, title="Kies de WoW Screenshots map")
        if value:
            self.screenshots.set(value)

    def _save(self) -> None:
        path = self.screenshots.get().strip()
        if not path:
            messagebox.showerror("KeystoneLens", "Kies eerst de WoW Screenshots map.", parent=self)
            return
        cfg = Config(
            client_id=self.client_id.get().strip(),
            client_secret=self.client_secret.get().strip(),
            screenshots_path=path,
        )
        if not cfg.wcl_configured:
            messagebox.showerror("KeystoneLens", "Vul je Warcraft Logs Client ID en Client Secret in.", parent=self)
            return
        if self.on_save(cfg):
            self.destroy()


SHUTDOWN_STEP_TIMEOUT_SECONDS = 0.75
SHUTDOWN_FORCE_EXIT_SECONDS = 5.0
DISABLE_SHUTDOWN_WATCHDOG_ENV = "KEYSTONELENS_DISABLE_FORCE_EXIT_WATCHDOG"


class App:
    def __init__(self):
        self._shutdown_started = False
        self._shutdown_cleaned = False
        self._shutdown_watchdog_started = False
        self._shutdown_step_timeout = SHUTDOWN_STEP_TIMEOUT_SECONDS
        self._shutdown_warnings: list[str] = []

        self.cfg = load_config()
        self.root = tk.Tk()
        self.root.title(f"KeystoneLens {__version__}")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.quit)
        self.root.report_callback_exception = self._tk_exception
        self._apply_icon()

        self.status_var = tk.StringVar(value="Starten…")
        frame = tk.Frame(self.root, padx=16, pady=16)
        frame.pack(fill="both", expand=True)
        tk.Label(frame, text="Warcraft Logs M+ Tooltip", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        tk.Label(frame, textvariable=self.status_var, justify="left", wraplength=430).pack(anchor="w", pady=(8, 14))
        buttons = tk.Frame(frame)
        buttons.pack(anchor="e")
        tk.Button(buttons, text="Instellingen", command=self.open_settings).pack(side="left")
        tk.Button(buttons, text="Afsluiten", command=self.quit).pack(side="left", padx=(8, 0))

        self.q: queue.Queue[tuple[str, object]] = queue.Queue()
        self.cache = WCLCache(ttl=self.cfg.cache_ttl_seconds)
        self.wcl: WCLClient | None = None
        self.watcher: ScreenshotWatcher | None = None
        self.tooltip_sync = TooltipCacheSync(self.cfg.screenshots_path)
        self.engine = ApplicantEngine(None, lambda state: self.q.put(("state", state)))

        self.root.after(100, self._poll)
        if self.cfg.ready and self.cfg.wcl_configured:
            self.start_runtime()
        else:
            self.status_var.set("Configureer Warcraft Logs en je WoW Screenshots map.")
            self.root.after(250, self.open_settings)

    def _apply_icon(self) -> None:
        if os.name != "nt":
            return
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("KeystoneLens.Companion")
        except (AttributeError, OSError):
            pass
        icon_path = Path(__file__).resolve().parent.parent / "KeystoneLens.ico"
        if icon_path.exists():
            try:
                self.root.iconbitmap(default=str(icon_path))
            except tk.TclError:
                pass

    def open_settings(self) -> None:
        if self._shutdown_started:
            return
        if any(isinstance(child, SettingsDialog) for child in self.root.winfo_children()):
            return
        SettingsDialog(self.root, self.cfg, self._settings_saved)

    def _settings_saved(self, cfg: Config) -> bool:
        try:
            save_config(cfg)
        except (OSError, ValueError) as exc:
            messagebox.showerror("KeystoneLens", f"Instellingen konden niet worden opgeslagen:\n{exc}", parent=self.root)
            return False
        self.cfg = cfg
        self.cache.ttl = cfg.cache_ttl_seconds
        self.start_runtime()
        return True

    def start_runtime(self) -> None:
        if self._shutdown_started:
            return
        if self.watcher:
            self.watcher.stop()
            self.watcher = None
        old_wcl = self.wcl
        self.wcl = None
        self.engine.set_wcl(None)
        if old_wcl:
            old_wcl.close()

        if not self.cfg.ready or not self.cfg.wcl_configured:
            self.status_var.set("Configureer Warcraft Logs en je WoW Screenshots map.")
            return

        self.tooltip_sync = TooltipCacheSync(self.cfg.screenshots_path)
        try:
            self.wcl = WCLClient(self.cfg.client_id, self.cfg.client_secret, self.cache)
            self.engine.set_wcl(self.wcl)
            threading.Thread(target=self._check_wcl_auth, args=(self.wcl,), daemon=True, name="KL-WCLAuth").start()
            self.watcher = ScreenshotWatcher(
                Path(self.cfg.screenshots_path),
                self.engine.handle_snapshot,
                lambda status: self.q.put(("status", status)),
            )
            self.watcher.start()
            self.status_var.set("Actief • wacht op Mythic+ Group Finder spelers")
        except Exception as exc:
            self.status_var.set(f"Startfout: {exc}")

    def _check_wcl_auth(self, client: WCLClient) -> None:
        try:
            client.test()
            if not self._shutdown_started and client is self.wcl:
                self.q.put(("status", "Warcraft Logs verbonden • wacht op spelers"))
        except Exception as exc:
            if not self._shutdown_started and client is self.wcl:
                self.q.put(("auth_failed", str(exc)))

    def _poll(self) -> None:
        if self._shutdown_started:
            return
        try:
            while True:
                kind, data = self.q.get_nowait()
                if kind == "state":
                    state: EngineState = data
                    if not self.tooltip_sync.write(list(state.rows)):
                        self.status_var.set(f"Tooltip-cache fout: {self.tooltip_sync.last_error}")
                        continue
                    ready = sum(1 for row in state.rows if row.wcl_status == "ready")
                    loading = sum(1 for row in state.rows if row.wcl_status in {"queued", "loading"})
                    if ready:
                        self.status_var.set(f"{ready} speler(s) klaar • /reload in WoW om nieuwe tooltipdata te laden")
                    elif loading:
                        self.status_var.set(f"Warcraft Logs laden voor {loading} speler(s)…")
                    else:
                        self.status_var.set(state.status)
                elif kind == "status":
                    self.status_var.set(str(data))
                elif kind == "auth_failed":
                    self.status_var.set(f"Warcraft Logs verbinding mislukt: {data}")
                    if self.wcl:
                        self.wcl.close()
                        self.wcl = None
                    self.engine.set_wcl(None)
        except queue.Empty:
            pass
        if not self._shutdown_started:
            self.root.after(120, self._poll)

    def _tk_exception(self, exc_type, exc_value, exc_traceback) -> None:
        _write_crash_log(exc_type, exc_value, exc_traceback)
        try:
            messagebox.showerror("KeystoneLens", f"Er ging iets mis. Details:\n{log_path()}", parent=self.root)
        except tk.TclError:
            pass

    def _arm_force_exit_watchdog(self) -> None:
        if self._shutdown_watchdog_started:
            return
        if os.environ.get(DISABLE_SHUTDOWN_WATCHDOG_ENV) == "1":
            return

        self._shutdown_watchdog_started = True

        def force_exit_if_stuck() -> None:
            time.sleep(SHUTDOWN_FORCE_EXIT_SECONDS)
            os._exit(0)

        threading.Thread(
            target=force_exit_if_stuck,
            name="KL-ShutdownWatchdog",
            daemon=True,
        ).start()

    def _bounded_cleanup(self, label: str, callback) -> None:
        done = threading.Event()
        failure: list[str] = []

        def run_step() -> None:
            try:
                callback()
            except Exception as exc:
                failure.append(f"{label}: {type(exc).__name__}: {exc}")
            finally:
                done.set()

        threading.Thread(
            target=run_step,
            name=f"KL-Shutdown-{label}",
            daemon=True,
        ).start()

        if not done.wait(self._shutdown_step_timeout):
            self._shutdown_warnings.append(f"{label}: cleanup timed out")
        elif failure:
            self._shutdown_warnings.extend(failure)

    def _cleanup_after_ui(self) -> None:
        if self._shutdown_cleaned:
            return

        self._shutdown_cleaned = True
        self._shutdown_started = True
        self._arm_force_exit_watchdog()

        watcher = self.watcher
        self.watcher = None
        wcl = self.wcl
        self.wcl = None
        engine = self.engine

        if watcher:
            watcher.request_stop()
        engine.request_stop()

        if watcher:
            self._bounded_cleanup(
                "watcher",
                lambda: watcher.stop(timeout=self._shutdown_step_timeout / 2),
            )
        if wcl:
            self._bounded_cleanup("wcl", wcl.close)
        self._bounded_cleanup(
            "engine",
            lambda: engine.stop(timeout=self._shutdown_step_timeout / 2),
        )

        if self._shutdown_warnings:
            try:
                log_path().write_text(
                    "Shutdown warnings:\n" + "\n".join(self._shutdown_warnings) + "\n",
                    encoding="utf-8",
                )
            except OSError:
                pass

    def quit(self) -> None:
        """Used by both the window X and the Afsluiten button."""
        if self._shutdown_started:
            return

        self._shutdown_started = True
        self._arm_force_exit_watchdog()

        if self.watcher:
            self.watcher.request_stop()
        self.engine.request_stop()

        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def run(self) -> None:
        try:
            self.root.mainloop()
        finally:
            self._cleanup_after_ui()


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


def _write_crash_log(exc_type, exc_value, exc_traceback) -> None:
    try:
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        log_path().write_text(text, encoding="utf-8")
    except OSError:
        pass


def _safe_stderr(message: str) -> None:
    stream = sys.stderr
    if stream is None:
        return
    try:
        stream.write(message + "\n")
        stream.flush()
    except Exception:
        pass


def main() -> int:
    _enable_dpi_awareness()
    try:
        App().run()
        return 0
    except tk.TclError as exc:
        _write_crash_log(type(exc), exc, exc.__traceback__)
        _safe_stderr(f"KeystoneLens UI could not start: {exc}")
        return 2
    except Exception as exc:
        _write_crash_log(type(exc), exc, exc.__traceback__)
        _safe_stderr(f"KeystoneLens could not start: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
