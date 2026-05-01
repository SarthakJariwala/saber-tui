from __future__ import annotations

from typing import Protocol

from saber_tui.components import Box, Spacer, Text, TruncatedText
from saber_tui.utils import visible_width


class Renderable(Protocol):
    def render(self, width: int) -> list[str]: ...


def test_text_wraps_and_pads_to_width() -> None:
    text = Text("hello world", padding_x=1, padding_y=1)

    lines = text.render(8)

    assert lines[0] == " " * 8
    assert all(visible_width(line) == 8 for line in lines)


def test_text_cache_is_invalidated_by_set_text() -> None:
    text = Text("alpha", padding_x=0, padding_y=0)

    assert text.render(8) == ["alpha   "]

    text.set_text("beta")

    assert text.render(8) == ["beta    "]


def test_text_background_fn_receives_padded_text_and_can_change() -> None:
    calls: list[str] = []

    def bg(text: str) -> str:
        calls.append(text)
        return f"\x1b[41m{text}\x1b[0m"

    text = Text("x", padding_x=1, padding_y=0, custom_bg_fn=bg)

    lines = text.render(5)

    assert calls == [" x   "]
    assert visible_width(lines[0]) == 5

    text.set_custom_bg_fn(lambda padded: f"\x1b[42m{padded}\x1b[0m")

    assert text.render(5) == ["\x1b[42m x   \x1b[0m"]


def test_text_background_fn_rerenders_stateful_output_without_invalidation() -> None:
    state = {"prefix": "A"}
    calls: list[str] = []

    def bg(text: str) -> str:
        calls.append(text)
        return state["prefix"] + text

    text = Text("hi", padding_x=0, padding_y=0, custom_bg_fn=bg)

    assert text.render(4) == ["Ahi  "]

    state["prefix"] = "B"

    assert text.render(4) == ["Bhi  "]
    assert calls == ["hi  ", "hi  "]


def test_truncated_text_is_single_line() -> None:
    text = TruncatedText("abcdef", padding_x=1)

    assert text.render(6) == [" a... "]


def test_truncated_text_subtracts_both_sides_of_horizontal_padding() -> None:
    lines = TruncatedText("abcdef", padding_x=2).render(8)

    assert lines == ["  a...  "]
    assert all(visible_width(line) <= 8 for line in lines)


def test_truncated_text_truncates_wide_graphemes_by_visible_width() -> None:
    lines = TruncatedText("你好世界").render(5)

    assert lines == ["你..."]
    assert all(visible_width(line) <= 5 for line in lines)


def test_truncated_text_cache_is_invalidated_by_set_text() -> None:
    text = TruncatedText("abcdef", padding_x=0)

    assert text.render(5) == ["ab..."]

    text.set_text("xy")

    assert text.render(5) == ["xy   "]


def test_box_wraps_child_lines_with_padding() -> None:
    box = Box(padding_x=1, padding_y=1)
    box.add_child(Text("hi", padding_x=0, padding_y=0))

    lines = box.render(6)

    assert lines == ["      ", " hi   ", "      "]


def test_box_cache_is_invalidated_by_child_changes() -> None:
    first = Text("one", padding_x=0, padding_y=0)
    second = Text("two", padding_x=0, padding_y=0)
    box = Box(padding_x=0, padding_y=0)

    box.add_child(first)
    assert box.render(5) == ["one  "]

    box.add_child(second)
    assert box.render(5) == ["one  ", "two  "]

    box.remove_child(first)
    assert box.render(5) == ["two  "]

    box.clear()
    assert box.render(5) == []


def test_box_background_fn_receives_padded_text() -> None:
    calls: list[str] = []
    box = Box(padding_x=1, padding_y=0, bg_fn=lambda padded: calls.append(padded) or padded)
    box.add_child(Text("hi", padding_x=0, padding_y=0))

    assert box.render(6) == [" hi   "]
    assert " hi   " in calls


def test_box_cache_samples_background_output_for_stateful_functions() -> None:
    state = {"prefix": "A"}

    def bg_fn(padded: str) -> str:
        return state["prefix"] + padded

    box = Box(padding_x=0, padding_y=0, bg_fn=bg_fn)
    box.add_child(Text("hi", padding_x=0, padding_y=0))

    assert box.render(4) == ["Ahi  "]

    state["prefix"] = "B"

    assert box.render(4) == ["Bhi  "]


def test_box_samples_background_once_on_uncached_render() -> None:
    calls: list[str] = []

    def bg_fn(padded: str) -> str:
        calls.append(padded)
        return padded

    box = Box(padding_x=1, padding_y=0, bg_fn=bg_fn)
    box.add_child(Text("hi", padding_x=0, padding_y=0))

    assert box.render(6) == [" hi   "]
    assert calls.count("test") == 1
    assert calls.count(" hi   ") == 1


def test_rendered_lines_do_not_exceed_width() -> None:
    components: list[Renderable] = [
        Text("abcdef", padding_x=2, padding_y=1),
        TruncatedText("abcdef", padding_x=2, padding_y=1),
        Spacer(2),
    ]
    box = Box(padding_x=2, padding_y=1)
    box.add_child(Text("abcdef", padding_x=1, padding_y=0))
    components.append(box)

    for component in components:
        assert all(visible_width(line) <= 3 for line in component.render(3))


def test_spacer_returns_empty_width_lines() -> None:
    spacer = Spacer(2)

    assert spacer.render(4) == ["    ", "    "]
