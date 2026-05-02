from __future__ import annotations

from saber_tui.autocomplete import AutocompleteItem, AutocompleteSuggestions
from saber_tui.components.editor import Editor, EditorCursor, EditorOptions, EditorTheme
from saber_tui.components.select_list import SelectListTheme
from saber_tui.tui import CURSOR_MARKER, TUI
from saber_tui.utils import visible_width
from tests.virtual_terminal import VirtualTerminal


def _theme() -> EditorTheme:
    return EditorTheme(border_color=lambda text: text, select_list=SelectListTheme())


def _editor(cols: int = 80, rows: int = 24) -> Editor:
    return Editor(TUI(VirtualTerminal(cols, rows)), _theme())


class StaticProvider:
    def get_suggestions(self, lines, cursor_line, cursor_col, *, force=False, signal=None):
        return AutocompleteSuggestions([AutocompleteItem("help", "help", "Show help")], "/h")

    def apply_completion(self, lines, cursor_line, cursor_col, item, prefix):
        from saber_tui.autocomplete import CompletionResult

        line = lines[cursor_line]
        before = line[: cursor_col - len(prefix)]
        after = line[cursor_col:]
        new_line = before + "/" + item.value + " " + after
        return CompletionResult([new_line], cursor_line, len(before) + len(item.value) + 2)

    def should_trigger_file_completion(self, lines, cursor_line, cursor_col):
        return True


class AwaitableProvider:
    def __init__(self) -> None:
        self.calls = 0

    def get_suggestions(self, lines, cursor_line, cursor_col, *, force=False, signal=None):
        self.calls += 1
        if self.calls == 1:
            return AutocompleteSuggestions([AutocompleteItem("help", "help", "Show help")], "/")
        return self._get_async_suggestions()

    async def _get_async_suggestions(self):
        return AutocompleteSuggestions([AutocompleteItem("ignored", "ignored", None)], "/h")

    def apply_completion(self, lines, cursor_line, cursor_col, item, prefix):
        from saber_tui.autocomplete import CompletionResult

        return CompletionResult(lines, cursor_line, cursor_col)

    def should_trigger_file_completion(self, lines, cursor_line, cursor_col):
        return True


class DuplicateValueProvider:
    def get_suggestions(self, lines, cursor_line, cursor_col, *, force=False, signal=None):
        return AutocompleteSuggestions(
            [
                AutocompleteItem("same", "first", "First item"),
                AutocompleteItem("same", "second", "Second item"),
            ],
            "/s",
        )

    def apply_completion(self, lines, cursor_line, cursor_col, item, prefix):
        from saber_tui.autocomplete import CompletionResult

        return CompletionResult([item.label], 0, len(item.label))

    def should_trigger_file_completion(self, lines, cursor_line, cursor_col):
        return True


class RecordingSignalProvider:
    def __init__(self) -> None:
        self.signals = []

    def get_suggestions(self, lines, cursor_line, cursor_col, *, force=False, signal=None):
        self.signals.append(signal)
        return AutocompleteSuggestions([AutocompleteItem("first", "first")], lines[cursor_line][:cursor_col])

    def apply_completion(self, lines, cursor_line, cursor_col, item, prefix):
        from saber_tui.autocomplete import CompletionResult

        return CompletionResult([item.value], 0, len(item.value))

    def should_trigger_file_completion(self, lines, cursor_line, cursor_col):
        return True


def test_editor_shows_and_applies_autocomplete() -> None:
    editor = _editor()
    editor.set_autocomplete_provider(StaticProvider())
    editor.handle_input("/")
    editor.handle_input("h")

    assert editor.is_showing_autocomplete() is True

    editor.handle_input("\r")

    assert editor.get_text() == "/help "
    assert editor.is_showing_autocomplete() is False


def test_editor_clears_autocomplete_after_cursor_movement() -> None:
    editor = _editor()
    submitted: list[str] = []
    editor.on_submit = submitted.append
    editor.set_autocomplete_provider(StaticProvider())
    editor.handle_input("/")
    editor.handle_input("h")

    editor.handle_input("\x1b[D")
    assert editor.is_showing_autocomplete() is False

    editor.handle_input("\r")

    assert editor.get_text() == "/h"
    assert submitted == ["/h"]
    assert editor.is_showing_autocomplete() is False


def test_editor_clears_autocomplete_after_delete() -> None:
    editor = _editor()
    editor.set_autocomplete_provider(StaticProvider())
    editor.handle_input("/")
    editor.handle_input("h")

    editor.handle_input("\x7f")

    assert editor.get_text() == "/"
    assert editor.is_showing_autocomplete() is False


def test_editor_awaitable_autocomplete_clears_stale_suggestions() -> None:
    editor = _editor()
    editor.set_autocomplete_provider(AwaitableProvider())
    editor.handle_input("/")

    assert editor.is_showing_autocomplete() is True

    editor.handle_input("h")

    assert editor.is_showing_autocomplete() is False


def test_editor_applies_duplicate_value_autocomplete_by_selected_index() -> None:
    editor = _editor()
    editor.set_autocomplete_provider(DuplicateValueProvider())
    editor.handle_input("/")
    editor.handle_input("s")

    editor.handle_input("\x1b[B")
    editor.handle_input("\r")

    assert editor.get_text() == "second"
    assert editor.is_showing_autocomplete() is False


def test_new_autocomplete_request_aborts_previous_signal() -> None:
    provider = RecordingSignalProvider()
    editor = _editor()
    editor.set_autocomplete_provider(provider)

    editor.handle_input("@")
    editor.handle_input("a")

    assert len(provider.signals) >= 2
    assert provider.signals[0].aborted is True
    assert provider.signals[-1].aborted is False


def test_clear_autocomplete_aborts_active_signal() -> None:
    provider = RecordingSignalProvider()
    editor = _editor()
    editor.set_autocomplete_provider(provider)

    editor.handle_input("@")
    signal = provider.signals[-1]

    assert signal.aborted is False
    assert editor.autocomplete_signal is signal

    editor.handle_input("\x1b[D")

    assert signal.aborted is True
    assert editor.autocomplete_signal is None


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


def test_editor_kill_ring_and_yank() -> None:
    editor = _editor()
    editor.set_text("foo bar")

    editor.handle_input("\x17")
    assert editor.get_text() == "foo "

    editor.handle_input("\x19")
    assert editor.get_text() == "foo bar"


def test_editor_undo_restores_previous_text_and_cursor() -> None:
    editor = _editor()
    editor.handle_input("a")
    editor.handle_input("b")
    editor.handle_input(" ")
    editor.handle_input("c")

    editor.handle_input("\x1f")

    assert editor.get_text() == "ab "
    assert editor.get_cursor() == EditorCursor(0, 3)


def test_editor_undo_after_yank_pop_restores_previous_yank_text() -> None:
    editor = _editor()
    editor.set_text("one two")
    editor.handle_input("\x17")
    editor.set_text("alpha beta")
    editor.handle_input("\x17")

    editor.handle_input("\x19")
    assert editor.get_text() == "alpha beta"

    editor.handle_input("\x1by")
    assert editor.get_text() == "alpha two"

    editor.handle_input("\x1f")

    assert editor.get_text() == "alpha beta"
    assert editor.get_cursor() == EditorCursor(0, 10)


def test_editor_delete_word_backward_at_buffer_start_does_not_push_undo() -> None:
    editor = _editor()
    changes: list[str] = []
    editor.on_change = changes.append

    editor.handle_input("\x17")
    editor.handle_input("\x1f")
    assert changes == []

    editor.handle_input("a")
    editor.handle_input("\x1f")

    assert editor.get_text() == ""


def test_editor_yank_pop_replaces_combining_grapheme_yank_exactly() -> None:
    editor = _editor()
    editor.set_text("one next")
    editor.handle_input("\x17")
    editor.set_text("one e\u0301")
    editor.handle_input("\x17")
    editor.set_text("pre ")

    editor.handle_input("\x19")
    assert editor.get_text() == "pre e\u0301"

    editor.handle_input("\x1by")

    assert editor.get_text() == "pre next"
    assert editor.get_cursor() == EditorCursor(0, 8)


def test_editor_delete_word_backward_while_browsing_history_preserves_edit_on_down() -> None:
    editor = _editor()
    editor.add_to_history("first")
    editor.add_to_history("second word")

    editor.handle_input("\x1b[A")
    editor.handle_input("\x17")
    editor.handle_input("\x1b[B")

    assert editor.get_text() == "second "


def test_editor_yank_while_browsing_history_preserves_edit_on_down() -> None:
    editor = _editor()
    editor.set_text("foo bar")
    editor.handle_input("\x17")
    editor.set_text("")
    editor.add_to_history("first")
    editor.add_to_history("second")

    editor.handle_input("\x1b[A")
    editor.handle_input("\x19")
    editor.handle_input("\x1b[B")

    assert editor.get_text() == "secondbar"


def test_editor_delete_word_backward_at_line_start_joins_previous_line() -> None:
    editor = _editor()
    editor.set_text("one\ntwo")
    editor.handle_input("\x01")

    editor.handle_input("\x17")

    assert editor.get_text() == "onetwo"
    assert editor.get_cursor() == EditorCursor(0, 3)


def test_character_jump_forward_and_backward() -> None:
    editor = _editor()
    editor.set_text("abc\ndef")
    editor.handle_input("\x01")

    editor.handle_input("\x1d")  # ctrl+]
    editor.handle_input("e")

    assert editor.get_cursor() == EditorCursor(1, 1)

    editor.handle_input("\x1b[93;7u")  # ctrl+alt+] in Kitty CSI-u form
    editor.handle_input("b")

    assert editor.get_cursor() == EditorCursor(0, 1)


def test_entering_character_jump_resets_yank_pop_state() -> None:
    editor = _editor()
    editor.set_text("one two")
    editor.handle_input("\x17")
    editor.set_text("alpha beta")
    editor.handle_input("\x17")
    editor.set_text("")

    editor.handle_input("\x19")
    editor.handle_input("\x1d")
    editor.handle_input("\x1by")

    assert editor.get_text() == "beta"


def test_character_jump_does_not_land_inside_grapheme() -> None:
    editor = _editor()
    editor.set_text("ae\u0301z")
    editor.handle_input("\x01")

    editor.handle_input("\x1d")
    editor.handle_input("\u0301")

    assert editor.cursor_col != 2


def test_repeating_character_jump_key_cancels_jump_mode() -> None:
    editor = _editor()
    editor.set_text("abc")
    editor.handle_input("\x01")

    editor.handle_input("\x1d")
    editor.handle_input("\x1d")
    editor.handle_input("c")

    assert editor.get_text() == "cabc"
    assert editor.get_cursor() == EditorCursor(0, 1)


def test_page_down_with_autocomplete_open_keeps_editor_state() -> None:
    editor = _editor()
    editor.set_autocomplete_provider(StaticProvider())
    editor.handle_input("/")
    editor.handle_input("h")
    cursor = editor.get_cursor()

    editor.handle_input("\x1b[6~")

    assert editor.get_text() == "/h"
    assert editor.get_cursor() == cursor
    assert editor.is_showing_autocomplete() is True


def test_sticky_column_preserves_target_through_shorter_line() -> None:
    editor = _editor()
    editor.set_text("abcdef\nxy\nabcdef")

    editor.handle_input("\x1b[A")
    assert editor.get_cursor() == EditorCursor(1, 2)

    editor.handle_input("\x1b[A")
    assert editor.get_cursor() == EditorCursor(0, 6)


def test_horizontal_movement_resets_sticky_column() -> None:
    editor = _editor()
    editor.set_text("abcdef\nxy\nabcdef")

    editor.handle_input("\x1b[A")
    editor.handle_input("\x1b[D")
    editor.handle_input("\x1b[A")

    assert editor.get_cursor() == EditorCursor(0, 1)


def test_vertical_movement_moves_between_wrapped_rows_in_logical_line() -> None:
    editor = _editor(cols=4)
    editor.set_text("abcdef")
    editor.handle_input("\x01")

    editor.handle_input("\x1b[B")
    assert editor.get_cursor() == EditorCursor(0, 4)

    editor.handle_input("\x1b[A")
    assert editor.get_cursor() == EditorCursor(0, 0)


def test_vertical_movement_uses_last_render_width_for_wrapping() -> None:
    editor = _editor(cols=80)
    editor.set_text("abcdef")
    editor.render(4)
    editor.handle_input("\x01")

    editor.handle_input("\x1b[B")

    assert editor.get_cursor() == EditorCursor(0, 4)


def test_sticky_column_preserves_target_through_wrapped_rows() -> None:
    editor = _editor(cols=4)
    editor.set_text("abcdefghi")
    editor.handle_input("\x01")
    editor.handle_input("\x1b[C")
    editor.handle_input("\x1b[C")

    editor.handle_input("\x1b[B")
    assert editor.get_cursor() == EditorCursor(0, 6)

    editor.handle_input("\x1b[B")
    assert editor.get_cursor() == EditorCursor(0, 9)


def test_bracketed_paste_inserts_small_paste_atomically() -> None:
    editor = _editor()

    editor.handle_input("\x1b[200~a\nb\x1b[201~")

    assert editor.get_text() == "a\nb"
    editor.handle_input("\x1f")
    assert editor.get_text() == ""


def test_large_paste_marker_expands_in_get_expanded_text() -> None:
    editor = _editor()
    pasted = "\n".join(f"line {index}" for index in range(12))

    editor.handle_input(f"\x1b[200~{pasted}\x1b[201~")

    assert "[paste #1" in editor.get_text()
    assert editor.get_expanded_text() == pasted


def test_large_paste_expansion_does_not_expand_markers_inside_paste_content() -> None:
    editor = _editor()
    first_paste = "\n".join(["literal [paste #2 +12 lines]", *[f"first {index}" for index in range(11)]])
    second_paste = "\n".join(f"second {index}" for index in range(12))

    editor.handle_input(f"\x1b[200~{first_paste}\x1b[201~")
    editor.handle_input(f"\x1b[200~{second_paste}\x1b[201~")

    assert editor.get_expanded_text() == f"{first_paste}{second_paste}"


def test_undo_large_paste_discards_stale_paste_expansion() -> None:
    editor = _editor()
    pasted = "\n".join(f"line {index}" for index in range(12))
    marker = "[paste #1 +12 lines]"

    editor.handle_input(f"\x1b[200~{pasted}\x1b[201~")
    editor.handle_input("\x1f")
    editor.set_text(marker)

    assert editor.get_expanded_text() == marker


def test_set_text_clears_stale_paste_expansion() -> None:
    editor = _editor()
    pasted = "\n".join(f"line {index}" for index in range(12))
    marker = "[paste #1 +12 lines]"

    editor.handle_input(f"\x1b[200~{pasted}\x1b[201~")
    editor.set_text(marker)

    assert editor.get_expanded_text() == marker


def test_reinserted_deleted_paste_marker_remains_literal() -> None:
    editor = _editor()
    pasted = "\n".join(f"line {index}" for index in range(12))
    marker = "[paste #1 +12 lines]"

    editor.handle_input(f"\x1b[200~{pasted}\x1b[201~")
    editor.set_text("")
    editor.insert_text_at_cursor(marker)

    assert editor.get_expanded_text() == marker
