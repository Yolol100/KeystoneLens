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
from .live_overlay import LiveTooltipOverlay
from .models import EngineState
from .watcher import ScreenshotWatcher
from .wcl import WCLCache, WCLClient


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
        self.root.bind("<Map>", self._on_root_mapped, add="+")
        self._apply_icon()

        self.status_var = tk.StringVar(value="Starten…")
        self.client_id_var = tk.StringVar(value=self.cfg.client_id)
        self.client_secret_var = tk.StringVar(value=self.cfg.client_secret)
        self.screenshots_var = tk.StringVar(value=self.cfg.screenshots_path)
        self._settings_visible = False

        frame = tk.Frame(self.root, padx=16, pady=16)
        frame.pack(fill="both", expand=True)
        tk.Label(frame, text="Warcraft Logs M+ Tooltip", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        tk.Label(frame, textvariable=self.status_var, justify="left", wraplength=450).pack(anchor="w", pady=(8, 14))

        self.settings_frame = tk.LabelFrame(frame, text="Instellingen", padx=10, pady=10)
        tk.Label(self.settings_frame, text="Warcraft Logs Client ID").grid(row=0, column=0, sticky="w")
        self.client_id_entry = tk.Entry(self.settings_frame, textvariable=self.client_id_var, width=50)
        self.client_id_entry.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(2, 8))

        tk.Label(self.settings_frame, text="Warcraft Logs Client Secret").grid(row=2, column=0, sticky="w")
        tk.Entry(
            self.settings_frame,
            textvariable=self.client_secret_var,
            show="•",
            width=50,
        ).grid(row=3, column=0, columnspan=2, sticky="ew", pady=(2, 8))

        tk.Label(self.settings_frame, text="WoW _retail_\\Screenshots map").grid(row=4, column=0, sticky="w")
        tk.Entry(self.settings_frame, textvariable=self.screenshots_var, width=40).grid(
            row=5, column=0, sticky="ew", pady=(2, 8)
        )
        tk.Button(self.settings_frame, text="Kiezen", command=self._browse_screenshots).grid(
            row=5, column=1, padx=(8, 0), pady=(2, 8)
        )

        settings_buttons = tk.Frame(self.settings_frame)
        settings_buttons.grid(row=6, column=0, columnspan=2, sticky="e")
        tk.Button(settings_buttons, text="Verbergen", command=lambda: self._set_settings_visible(False)).pack(
            side="right"
        )
        tk.Button(settings_buttons, text="Opslaan", command=self._save_settings).pack(
            side="right", padx=(0, 8)
        )

        self.button_frame = tk.Frame(frame)
        self.button_frame.pack(anchor="e")
        tk.Button(self.button_frame, text="Instellingen", command=self.open_settings).pack(side="left")
        tk.Button(self.button_frame, text="Afsluiten", command=self.quit).pack(side="left", padx=(8, 0))

        self.q: queue.Queue[tuple[str, object]] = queue.Queue()
        self.cache = WCLCache(ttl=self.cfg.cache_ttl_seconds)
        self.wcl: WCLClient | None = None
        self.watcher: ScreenshotWatcher | None = None
        self.tooltip_sync = TooltipCacheSync(self.cfg.screenshots_path)
        self.engine = ApplicantEngine(None, lambda state: self.q.put(("state", state)))
        self.live_overlay = LiveTooltipOverlay(self.root)

        self.root.after(0, self._show_main_window)
        self.root.after(100, self._poll)
        if self.cfg.ready and self.cfg.wcl_configured:
            self.start_runtime()
        else:
            self.status_var.set("Configureer Warcraft Logs en je WoW Screenshots map.")
            self._set_settings_visible(True)

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

    def _center_main_window(self) -> None:
        try:
            self.root.update_idletasks()
            width = max(self.root.winfo_reqwidth(), self.root.winfo_width())
            height = max(self.root.winfo_reqheight(), self.root.winfo_height())
            x = max(0, (self.root.winfo_screenwidth() - width) // 2)
            y = max(0, (self.root.winfo_screenheight() - height) // 3)
            self.root.geometry(f"+{x}+{y}")
        except tk.TclError:
            pass

    def _show_main_window(self, force_foreground: bool = False) -> None:
        if self._shutdown_started:
            return
        try:
            state = self.root.state()
            if state in {"withdrawn", "iconic"}:
                self.root.deiconify()
                self.root.state("normal")
            self.root.update_idletasks()
            self.root.lift()
            if force_foreground:
                self.root.focus_force()
        except tk.TclError:
            return

    def _on_root_mapped(self, event) -> None:
        if self._shutdown_started or event.widget is not self.root:
            return
        try:
            self.root.after_idle(self._show_main_window)
        except tk.TclError:
            pass

    def _set_settings_visible(self, visible: bool) -> None:
        if self._shutdown_started:
            return
        if visible and not self._settings_visible:
            self.settings_frame.pack(
                before=self.button_frame,
                fill="x",
                pady=(0, 14),
            )
            self._settings_visible = True
            self.root.after_idle(self._center_main_window)
        elif not visible and self._settings_visible:
            self.settings_frame.pack_forget()
            self._settings_visible = False
            self.root.after_idle(self._center_main_window)

    def open_settings(self) -> None:
        if self._shutdown_started:
            return
        self._show_main_window(force_foreground=True)
        self._set_settings_visible(True)
        try:
            self.client_id_entry.focus_set()
        except tk.TclError:
            pass

    def _browse_screenshots(self) -> None:
        value = filedialog.askdirectory(parent=self.root, title="Kies de WoW Screenshots map")
        if value:
            self.screenshots_var.set(value)
            self._show_main_window(force_foreground=True)

    def _save_settings(self) -> None:
        path = self.screenshots_var.get().strip()
        if not path:
            messagebox.showerror("KeystoneLens", "Kies eerst de WoW Screenshots map.", parent=self.root)
            return

        cfg = Config(
            client_id=self.client_id_var.get().strip(),
            client_secret=self.client_secret_var.get().strip(),
            screenshots_path=path,
            cache_ttl_seconds=self.cfg.cache_ttl_seconds,
        )
        if not cfg.wcl_configured:
            messagebox.showerror(
                "KeystoneLens",
                "Vul je Warcraft Logs Client ID en Client Secret in.",
                parent=self.root,
            )
            return

        try:
            save_config(cfg)
        except (OSError, ValueError) as exc:
            messagebox.showerror(
                "KeystoneLens",
                f"Instellingen konden niet worden opgeslagen:\n{exc}",
                parent=self.root,
            )
            return

        self.cfg = cfg
        self.cache.ttl = cfg.cache_ttl_seconds
        self._set_settings_visible(False)
        self.start_runtime()
        self._show_main_window(force_foreground=True)

    def start_runtime(self) -> None:
        if self._shutdown_started:
            return
        self.live_overlay.hide()
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
                    self.live_overlay.update_from_state(state)
                    if not self.tooltip_sync.write(list(state.rows)):
                        self.status_var.set(f"Tooltip-cache fout: {self.tooltip_sync.last_error}")
                        continue
                    ready = sum(1 for row in state.rows if row.wcl_status == "ready")
                    loading = sum(1 for row in state.rows if row.wcl_status in {"queued", "loading"})
                    if ready:
                        self.status_var.set(f"{ready} speler(s) klaar • live tooltip actief • geen /reload nodig")
                    elif loading:
                        self.status_var.set(f"Warcraft Logs laden voor {loading} speler(s)…")
                    else:
                        self.status_var.set(state.status)
                elif kind == "status":
                    self.status_var.set(str(data))
                elif kind == "auth_failed":
                    self.live_overlay.hide()
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

        self.live_overlay.close()

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
        self.live_overlay.close()

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
