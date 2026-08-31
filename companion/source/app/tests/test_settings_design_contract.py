from pathlib import Path


UI_SOURCE = Path(__file__).resolve().parents[1] / "keystonelens_companion" / "ui.py"


def _source() -> str:
    return UI_SOURCE.read_text(encoding="utf-8")


def test_settings_visible_columns_finish_with_balanced_full_width_row() -> None:
    source = _source()
    assert 'if key == "show_wcl":' in source
    assert 'row.grid(row=2, column=0, columnspan=2' in source
    assert 'padx=(0, 4) if column == 0 else (4, 0)' in source


def test_settings_empty_error_copy_does_not_reserve_vertical_space() -> None:
    source = _source()
    error_section = source.split("self.error_label = tk.Label(", 1)[1].split(
        "self.attribution = tk.Label(", 1
    )[0]
    assert "self.error_label.pack(" not in error_section
    assert "def _show_error" in source
    assert "before=self.attribution" in source
    assert "def _clear_error" in source
    assert "self.error_label.pack_forget()" in source


def test_settings_optional_status_is_not_styled_as_a_button() -> None:
    source = _source()
    assert 'tk.Label(heading, text="Optional", bg=BG, fg=DIALOG_MUTED' in source
    assert 'text="Stored encrypted for your Windows account."' in source
