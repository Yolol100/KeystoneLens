from pathlib import Path

path = Path("companion/source/app/keystonelens_companion/ui.py")
source = path.read_text(encoding="utf-8")


def replace_once(old: str, new: str, label: str) -> None:
    global source
    count = source.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, found {count}")
    source = source.replace(old, new, 1)


replace_once(
    '        tk.Label(heading, text="Optional", bg=PANEL_ALT, fg=DIALOG_MUTED,\n'
    '                 font=(FONT, 7), padx=6, pady=1).pack(side="right")',
    '        # Keep the optional status visually secondary; it is information, not a button.\n'
    '        tk.Label(heading, text="Optional", bg=BG, fg=DIALOG_MUTED,\n'
    '                 font=(FONT, 7, "bold")).pack(side="right")',
    "optional status",
)
replace_once(
    '            text="Client Secret is protected by Windows.",',
    '            text="Stored encrypted for your Windows account.",',
    "secret helper",
)
replace_once(
    '            row.grid(row=index // 2, column=index % 2, sticky="ew", padx=(0, 10) if index % 2 == 0 else (10, 0), pady=2)',
    '            if key == "show_wcl":\n'
    '                # Five options in a 2-column grid otherwise leave a visually broken orphan card.\n'
    '                # Let the final option span the row so the section ends on a balanced edge.\n'
    '                row.grid(row=2, column=0, columnspan=2, sticky="ew", padx=0, pady=(4, 2))\n'
    '            else:\n'
    '                column = index % 2\n'
    '                row.grid(\n'
    '                    row=index // 2, column=column, sticky="ew",\n'
    '                    padx=(0, 4) if column == 0 else (4, 0), pady=2,\n'
    '                )',
    "balanced toggle grid",
)
replace_once(
    '        self.error_label.pack(fill="x", pady=(6, 0))\n\n'
    '        attribution = tk.Label(\n'
    '            content, text="Data by Raider.IO • raider.io", bg=BG, fg=ACCENT,\n'
    '            font=(FONT, 8, "underline"), cursor="hand2", anchor="w",\n'
    '        )\n'
    '        attribution.pack(fill="x", pady=(7, 0))\n'
    '        attribution.bind("<Button-1>", lambda _event: open_raider_io())',
    '        # Error copy is inserted only when validation or persistence actually fails.\n\n'
    '        self.attribution = tk.Label(\n'
    '            content, text="Data by Raider.IO • raider.io", bg=BG, fg=ACCENT,\n'
    '            font=(FONT, 8, "underline"), cursor="hand2", anchor="w",\n'
    '        )\n'
    '        self.attribution.pack(fill="x", pady=(7, 0))\n'
    '        self.attribution.bind("<Button-1>", lambda _event: open_raider_io())',
    "error spacing and attribution",
)
replace_once(
    '        row = tk.Frame(parent, bg=PANEL_ALT, padx=10, pady=7, highlightthickness=1, highlightbackground=BORDER)',
    '        row = tk.Frame(\n'
    '            parent, bg=PANEL_ALT, padx=10, pady=7, highlightthickness=1,\n'
    '            highlightbackground=BORDER, cursor="hand2",\n'
    '        )',
    "toggle card cursor",
)
replace_once(
    '        copy = tk.Frame(row, bg=PANEL_ALT)',
    '        copy = tk.Frame(row, bg=PANEL_ALT, cursor="hand2")',
    "toggle copy cursor",
)
replace_once(
    '        title = tk.Label(copy, text=label, bg=PANEL_ALT, fg=TEXT, font=(FONT, 8, "bold"), anchor="w")',
    '        title = tk.Label(\n'
    '            copy, text=label, bg=PANEL_ALT, fg=TEXT, font=(FONT, 8, "bold"),\n'
    '            anchor="w", cursor="hand2",\n'
    '        )',
    "toggle title cursor",
)
replace_once(
    '        detail = tk.Label(copy, text=description, bg=PANEL_ALT, fg=DIALOG_MUTED, font=(FONT, 7), anchor="w")',
    '        detail = tk.Label(\n'
    '            copy, text=description, bg=PANEL_ALT, fg=DIALOG_MUTED, font=(FONT, 7),\n'
    '            anchor="w", cursor="hand2",\n'
    '        )',
    "toggle detail cursor",
)

clear_call = 'self.error_label.configure(text="")'
if source.count(clear_call) != 2:
    raise SystemExit(f"clear error: expected two matches, found {source.count(clear_call)}")
source = source.replace(clear_call, "self._clear_error()")
replace_once('self.error_label.configure(text=error)', 'self._show_error(error)', "validation error")
replace_once(
    'self.error_label.configure(text="Couldn’t save settings. Check the main window status, then try again.")',
    'self._show_error("Couldn’t save settings. Check the main window status, then try again.")',
    "save error",
)
replace_once(
    '        return row\n\n    def _center_over_parent',
    '        return row\n\n'
    '    def _clear_error(self) -> None:\n'
    '        self.error_label.configure(text="")\n'
    '        if self.error_label.winfo_manager():\n'
    '            self.error_label.pack_forget()\n\n'
    '    def _show_error(self, message: str) -> None:\n'
    '        self.error_label.configure(text=message)\n'
    '        if not self.error_label.winfo_manager():\n'
    '            self.error_label.pack(fill="x", pady=(6, 0), before=self.attribution)\n\n'
    '    def _center_over_parent',
    "error helpers",
)

required = (
    'if key == "show_wcl":',
    'row.grid(row=2, column=0, columnspan=2',
    'text="Stored encrypted for your Windows account."',
    'def _show_error(self, message: str)',
    'before=self.attribution',
)
for marker in required:
    if marker not in source:
        raise SystemExit(f"missing post-patch marker: {marker}")

path.write_text(source, encoding="utf-8")
