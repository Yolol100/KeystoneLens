from pathlib import Path

path = Path("companion/source/app/keystonelens_companion/ui.py")
source = path.read_text(encoding="utf-8")
start = source.index("class _ToggleSwitch(tk.Canvas):")
end = source.index("\n\nclass SetupDialog", start)
replacement = '''class _ToggleSwitch(tk.Canvas):
    # Deliberately larger than the old 38x20 control: the Settings switches must
    # remain immediately recognizable on Windows at normal and high-DPI scaling.
    WIDTH = 48
    HEIGHT = 28
    TRACK_LEFT = 2
    TRACK_TOP = 4
    TRACK_RIGHT = 46
    TRACK_BOTTOM = 24
    TRACK_RADIUS = 10
    THUMB_RADIUS = 8

    def __init__(self, parent: tk.Misc, variable: tk.BooleanVar):
        self._parent_bg = str(parent.cget("bg"))
        super().__init__(
            parent, width=self.WIDTH, height=self.HEIGHT, bg=self._parent_bg,
            highlightthickness=1, highlightbackground=self._parent_bg, highlightcolor=ACCENT,
            bd=0, cursor="hand2", takefocus=1,
        )
        self.variable = variable
        self.bind("<Button-1>", self._toggle)
        self.bind("<Key-space>", self._toggle)
        self.bind("<Key-Return>", self._toggle)
        self.bind("<FocusIn>", lambda _e: self._draw())
        self.bind("<FocusOut>", lambda _e: self._draw())
        self.variable.trace_add("write", lambda *_args: self._draw())
        self._draw()

    def _toggle(self, _event=None) -> str:
        self.variable.set(not self.variable.get())
        return "break"

    def _draw(self) -> None:
        self.delete("all")
        on = bool(self.variable.get())
        track = ACCENT if on else DIALOG_CONTROL_BORDER
        outline = "#8fc5ff" if on else DIALOG_MUTED
        self.configure(highlightbackground=ACCENT if self.focus_get() is self else self._parent_bg)

        left, top = self.TRACK_LEFT, self.TRACK_TOP
        right, bottom = self.TRACK_RIGHT, self.TRACK_BOTTOM
        radius = self.TRACK_RADIUS
        self.create_oval(left, top, left + radius * 2, bottom, fill=track, outline=outline, width=1)
        self.create_oval(right - radius * 2, top, right, bottom, fill=track, outline=outline, width=1)
        self.create_rectangle(left + radius, top, right - radius, bottom, fill=track, outline=track)
        self.create_line(left + radius, top, right - radius, top, fill=outline, width=1)
        self.create_line(left + radius, bottom, right - radius, bottom, fill=outline, width=1)

        cx = right - radius if on else left + radius
        cy = (top + bottom) // 2
        r = self.THUMB_RADIUS
        self.create_oval(cx - r, cy - r, cx + r, cy + r, fill=TEXT, outline="#ffffff", width=1)
'''
source = source[:start] + replacement + source[end:]
required = (
    "WIDTH = 48",
    "HEIGHT = 28",
    'outline = "#8fc5ff" if on else DIALOG_MUTED',
    'self.bind("<FocusIn>", lambda _e: self._draw())',
    'fill=TEXT, outline="#ffffff", width=1',
)
for marker in required:
    if marker not in source:
        raise SystemExit(f"missing post-patch marker: {marker}")
path.write_text(source, encoding="utf-8")
