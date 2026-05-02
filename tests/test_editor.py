from __future__ import annotations

from saber_tui.components.editor import Editor, EditorCursor, EditorOptions, EditorTheme
from saber_tui.components.select_list import SelectListTheme
from saber_tui.tui import CURSOR_MARKER, TUI
from saber_tui.utils import visible_width
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


def test_word_wrap_line_wraps_at_word_boundaries() -> None:
    from saber_tui.components.editor import word_wrap_line

    chunks = word_wrap_line("hello world", 7)

    assert [chunk.text for chunk in chunks] == ["hello ", "world"]
    assert [(chunk.start_index, chunk.end_index) for chunk in chunks] == [(0, 6), (6, 11)]


def test_editor_render_is_width_bounded_and_marks_focused_cursor() -> None:
    editor = _editor()
    editor.focused = True
    editor.set_text("hello コンピューター")

    lines = editor.render(12)

    assert len(lines) >= 3
    assert CURSOR_MARKER in "".join(lines)
    assert all(visible_width(line) <= 12 for line in lines)


def test_editor_render_handles_narrow_width() -> None:
    editor = _editor()
    editor.focused = True
    editor.set_text("abcdef")

    lines = editor.render(1)

    assert lines
    assert all(visible_width(line) <= 1 for line in lines)


def test_editor_render_marks_wrapped_boundary_cursor_once() -> None:
    editor = _editor()
    editor.focused = True
    editor.set_text("hello world")
    editor.cursor_col = 6

    lines = editor.render(7)

    assert "".join(lines).count(CURSOR_MARKER) == 1
    assert all(visible_width(line) <= 7 for line in lines)


def test_editor_render_preserves_end_cursor_marker_at_exact_width() -> None:
    editor = _editor()
    editor.focused = True
    editor.set_text("abc")

    lines = editor.render(3)

    assert CURSOR_MARKER in "".join(lines)
    assert all(visible_width(line) <= 3 for line in lines)


def test_editor_render_preserves_wide_cursor_marker_at_narrow_width() -> None:
    editor = _editor()
    editor.focused = True
    editor.set_text("コ")

    lines = editor.render(1)

    assert CURSOR_MARKER in "".join(lines)
    assert all(visible_width(line) <= 1 for line in lines)


def test_editor_render_prioritizes_cursor_marker_over_padding_at_narrow_width() -> None:
    editor = Editor(object(), options=EditorOptions(padding_x=1))
    editor.focused = True
    editor.set_text("a")

    lines = editor.render(1)

    assert CURSOR_MARKER in "".join(lines)
    assert all(visible_width(line) <= 1 for line in lines)


def test_arrow_keys_move_across_lines_and_insert_at_cursor() -> None:
    editor = _editor()
    editor.set_text("one\ntwo")

    editor.handle_input("\x1b[A")
    editor.handle_input("X")

    assert editor.get_text() == "oneX\ntwo"


def test_backspace_at_line_start_joins_previous_line() -> None:
    editor = _editor()
    editor.set_text("one\ntwo")
    editor.handle_input("\x01")
    editor.handle_input("\x7f")

    assert editor.get_text() == "onetwo"
    assert editor.get_cursor() == EditorCursor(0, 3)


def test_delete_at_line_end_joins_next_line() -> None:
    editor = _editor()
    editor.set_text("one\ntwo")
    editor.handle_input("\x1b[A")
    editor.handle_input("\x05")
    editor.handle_input("\x04")

    assert editor.get_text() == "onetwo"
    assert editor.get_cursor() == EditorCursor(0, 3)


def test_vertical_movement_aligns_to_combining_grapheme_boundary() -> None:
    editor = _editor()
    editor.set_text("ab\ne\u0301Z")
    editor.cursor_line = 0
    editor.cursor_col = 1

    editor.handle_input("\x1b[B")

    assert editor.get_cursor() == EditorCursor(1, 2)


def test_backspace_after_vertical_movement_removes_full_combining_grapheme() -> None:
    editor = _editor()
    editor.set_text("ab\ne\u0301Z")
    editor.cursor_line = 0
    editor.cursor_col = 1

    editor.handle_input("\x1b[B")
    editor.handle_input("\x7f")

    assert editor.get_text() == "ab\nZ"
    assert editor.get_cursor() == EditorCursor(1, 0)


def test_horizontal_movement_repairs_cursor_inside_combining_grapheme() -> None:
    editor = _editor()
    editor.set_text("e\u0301Z")
    editor.cursor_col = 1

    editor.handle_input("\x1b[C")

    assert editor.get_cursor() == EditorCursor(0, 3)


def test_enter_submits_and_shift_enter_inserts_newline() -> None:
    editor = _editor()
    submitted: list[str] = []
    editor.on_submit = submitted.append
    editor.handle_input("h")
    editor.handle_input("\x1b[13;2u")  # shift+enter Kitty CSI-u
    editor.handle_input("i")
    editor.handle_input("\r")

    assert editor.get_text() == "h\ni"
    assert submitted == ["h\ni"]


def test_backslash_enter_converts_standalone_backslash_to_newline() -> None:
    editor = _editor()
    editor.handle_input("\\")
    editor.handle_input("\r")

    assert editor.get_text() == "\n"


def test_prompt_history_navigation() -> None:
    editor = _editor()
    editor.add_to_history("first")
    editor.add_to_history("second")

    editor.handle_input("\x1b[A")
    assert editor.get_text() == "second"

    editor.handle_input("\x1b[A")
    assert editor.get_text() == "first"

    editor.handle_input("\x1b[B")
    assert editor.get_text() == "second"

    editor.handle_input("\x1b[B")
    assert editor.get_text() == ""


def test_prompt_history_navigation_emits_change_for_visible_text() -> None:
    editor = _editor()
    changes: list[str] = []
    editor.on_change = changes.append
    editor.add_to_history("first")
    editor.add_to_history("second")

    editor.handle_input("\x1b[A")
    editor.handle_input("\x1b[A")
    editor.handle_input("\x1b[B")
    editor.handle_input("\x1b[B")

    assert changes == ["second", "first", "second", ""]


def test_backspace_while_browsing_history_keeps_edited_text_on_down() -> None:
    editor = _editor()
    editor.add_to_history("first")
    editor.add_to_history("second")

    editor.handle_input("\x1b[A")
    editor.handle_input("\x7f")
    editor.handle_input("\x1b[B")

    assert editor.get_text() == "secon"


def test_delete_while_browsing_history_keeps_edited_text_on_down() -> None:
    editor = _editor()
    editor.add_to_history("first")
    editor.add_to_history("second")

    editor.handle_input("\x1b[A")
    editor.handle_input("\x01")  # Ctrl+A
    editor.handle_input("\x04")  # Ctrl+D
    editor.handle_input("\x1b[B")

    assert editor.get_text() == "econd"
