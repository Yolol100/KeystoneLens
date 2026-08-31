from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _ui_source() -> str:
    return (ROOT / "app/keystonelens_companion/ui.py").read_text(encoding="utf-8")


def test_row_click_selection_opens_the_existing_detail_panel():
    source = _ui_source()

    render_rows_start = source.index("    def _render_rows(self) -> None:")
    render_row_start = source.index("    def _render_row(self, view: ApplicantView, idx: int) -> None:")
    draw_role_start = source.index("    def _draw_role_icon", render_row_start)
    select_start = source.index("    def _select(self, view: ApplicantView) -> None:", draw_role_start)
    show_detail_start = source.index("    def _show_detail(self, view: ApplicantView) -> None:", select_start)

    render_rows = source[render_rows_start:render_row_start]
    render_row = source[render_row_start:draw_role_start]
    select = source[select_start:show_detail_start]

    assert 'widget.bind("<Button-1>", lambda _event, v=view: self._select(v))' in render_row
    assert 'child.bind("<Button-1>", lambda _event, v=view: self._select(v))' in render_row
    assert "self.selected_identity = view.applicant.identity" in select
    assert "self._render_rows()" in select
    assert "self._show_detail(selected)" in render_rows
    assert 'self.detail.pack(fill="x", padx=12, pady=(6, 0))' in render_rows


def test_role_icon_click_is_forwarded_to_the_row_selection_handler():
    source = _ui_source()
    draw_role_start = source.index("    def _draw_role_icon")
    select_start = source.index("    def _select(self, view: ApplicantView) -> None:", draw_role_start)
    draw_role = source[draw_role_start:select_start]

    assert 'canvas.bind("<Button-1>", lambda event: parent.event_generate("<Button-1>"' in draw_role
