from __future__ import annotations

from saber_tui.components import Input
from saber_tui.tui import CURSOR_MARKER
from saber_tui.utils import visible_width


def test_input_inserts_printable_text_and_submits() -> None:
    input_box = Input()
    submitted: list[str] = []
    input_box.on_submit = submitted.append

    for char in "hello":
        input_box.handle_input(char)
    input_box.handle_input("\r")

    assert input_box.get_value() == "hello"
    assert submitted == ["hello"]


def test_input_backspace_deletes_grapheme() -> None:
    input_box = Input()
    input_box.set_value("aコン")
    input_box.handle_input("\x05")
    input_box.handle_input("\x7f")

    assert input_box.get_value() == "aコ"


def test_input_kill_ring_and_yank() -> None:
    input_box = Input()
    input_box.set_value("foo bar")
    input_box.handle_input("\x05")
    input_box.handle_input("\x17")
    assert input_box.get_value() == "foo "
    input_box.handle_input("\x19")
    assert input_box.get_value() == "foo bar"


def test_input_render_never_exceeds_width_and_marks_cursor_when_focused() -> None:
    input_box = Input()
    input_box.set_value("コンピューター")
    input_box.focused = True

    line = input_box.render(10)[0]

    assert visible_width(line) <= 10
    assert CURSOR_MARKER in line


def test_input_bracketed_paste_buffers_and_sanitizes() -> None:
    input_box = Input()
    input_box.handle_input("a")
    input_box.handle_input("\x1b[200~b\r\n")
    assert input_box.get_value() == "a"

    input_box.handle_input("c\td\x1b[201~e")

    assert input_box.get_value() == "abc    de"


def test_input_undo_restores_previous_value_and_cursor() -> None:
    input_box = Input()
    input_box.handle_input("abc")
    input_box.handle_input(" ")
    input_box.handle_input("def")
    input_box.handle_input("\x1f")

    assert input_box.get_value() == "abc"

    input_box.handle_input("X")

    assert input_box.get_value() == "abcX"


def test_input_decodes_kitty_printable_before_control_rejection() -> None:
    input_box = Input()

    input_box.handle_input("\x1b[97u")
    input_box.handle_input("\x1b[65;2u")

    assert input_box.get_value() == "aA"


def test_input_rejects_c0_del_and_c1_controls_as_text() -> None:
    input_box = Input()

    input_box.handle_input("\x00")
    input_box.handle_input("\x7f")
    input_box.handle_input("\x85")

    assert input_box.get_value() == ""


def test_input_yank_pop_replaces_previous_yank() -> None:
    input_box = Input()
    input_box.set_value("one two")
    input_box.handle_input("\x05")
    input_box.handle_input("\x17")
    input_box.handle_input("\x02")
    input_box.handle_input("\x15")
    input_box.handle_input("\x19")
    assert input_box.get_value() == "one "

    input_box.handle_input("\x1by")

    assert input_box.get_value() == "two "


def test_input_render_handles_width_narrower_than_prompt() -> None:
    input_box = Input()
    input_box.set_value("abc")
    input_box.focused = True

    line = input_box.render(1)[0]

    assert visible_width(line) <= 1


def test_input_focused_render_width_one_includes_zero_width_cursor() -> None:
    input_box = Input()
    input_box.focused = True

    line = input_box.render(1)[0]

    assert visible_width(line) <= 1
    assert CURSOR_MARKER in line
    assert "\x1b[7m" in line
    assert "\x1b[27m" in line


def test_input_focused_render_width_two_includes_zero_width_cursor() -> None:
    input_box = Input()
    input_box.focused = True

    line = input_box.render(2)[0]

    assert visible_width(line) <= 2
    assert CURSOR_MARKER in line
    assert "\x1b[7m" in line
    assert "\x1b[27m" in line


def test_input_unfocused_narrow_render_keeps_prompt_only() -> None:
    input_box = Input()

    assert input_box.render(1)[0] == ">"
    assert input_box.render(2)[0] == "> "
