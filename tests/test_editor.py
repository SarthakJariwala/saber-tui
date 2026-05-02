from __future__ import annotations

from saber_tui.components.editor import Editor, EditorCursor, EditorTheme
from saber_tui.components.select_list import SelectListTheme
from saber_tui.tui import TUI
from tests.virtual_terminal import VirtualTerminal


def _theme() -> EditorTheme:
    return EditorTheme(border_color=lambda text: text, select_list=SelectListTheme())


def _editor(cols: int = 80, rows: int = 24) -> Editor:
    return Editor(TUI(VirtualTerminal(cols, rows)), _theme())


def test_editor_public_state_accessors_are_defensive() -> None:
    editor = _editor()
    editor.set_text("one\ntwo")

    lines = editor.get_lines()
    lines.append("mutated")

    assert editor.get_text() == "one\ntwo"
    assert editor.get_cursor() == EditorCursor(1, 3)


def test_insert_text_at_cursor_handles_multiline_text() -> None:
    editor = _editor()
    editor.set_text("hello")
    editor.handle_input("\x01")  # Ctrl+A

    editor.insert_text_at_cursor("a\r\nb\r")

    assert editor.get_text() == "a\nb\nhello"
    assert editor.get_cursor() == EditorCursor(2, 0)


def test_on_change_fires_for_text_changes_only() -> None:
    editor = _editor()
    changes: list[str] = []
    editor.on_change = changes.append

    editor.handle_input("a")
    editor.handle_input("\x1b[D")

    assert changes == ["a"]


def test_set_text_sanitizes_controls_and_ansi_while_preserving_newlines() -> None:
    editor = _editor()

    editor.set_text("a\x1b[31mred\x1b[0m\tb\x00\nc\x7fd\u0085\r\ne")

    assert editor.get_text() == "ared    b\ncd\ne"
    assert editor.get_cursor() == EditorCursor(2, 1)


def test_insert_text_at_cursor_sanitizes_mixed_text() -> None:
    editor = _editor()
    editor.set_text("tail")
    editor.handle_input("\x01")  # Ctrl+A

    editor.insert_text_at_cursor("a\x1b[31m!\x1b[0m\x02\nb\t\u009fc")

    assert editor.get_text() == "a!\nb    ctail"
    assert editor.get_cursor() == EditorCursor(1, 6)


def test_noop_text_mutations_do_not_emit_change_or_request_render() -> None:
    editor = _editor()
    editor.set_text("same")
    changes: list[str] = []
    renders: list[None] = []

    def request_render() -> None:
        renders.append(None)

    editor.on_change = changes.append
    editor.tui.request_render = request_render  # type: ignore[method-assign]

    editor.set_text("sa\x00me")
    editor.insert_text_at_cursor("")
    editor.insert_text_at_cursor("\x1b[31m\x1b[0m\x7f\u009f")

    assert editor.get_text() == "same"
    assert changes == []
    assert renders == []
