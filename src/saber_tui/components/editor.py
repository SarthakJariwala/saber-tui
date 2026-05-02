from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from saber_tui.components.select_list import SelectListTheme


@dataclass(frozen=True)
class TextChunk:
    text: str
    start_index: int
    end_index: int


@dataclass(frozen=True)
class EditorCursor:
    line: int
    col: int


@dataclass(frozen=True)
class EditorTheme:
    border_color: Callable[[str], str] = lambda text: text
    select_list: SelectListTheme = SelectListTheme()


@dataclass(frozen=True)
class EditorOptions:
    padding_x: int = 0
    autocomplete_max_visible: int = 5


def word_wrap_line(line: str, max_width: int, pre_segmented: object | None = None) -> list[TextChunk]:
    _ = pre_segmented
    return [TextChunk(line, 0, len(line))] if line and max_width > 0 else [TextChunk("", 0, 0)]


class Editor:
    def __init__(self, tui: object, theme: EditorTheme | None = None, options: EditorOptions | None = None) -> None:
        self.tui = tui
        self.theme = theme or EditorTheme()
        self.options = options or EditorOptions()
        self.focused = False
        self.border_color = self.theme.border_color
        self.on_submit: Callable[[str], None] | None = None
        self.on_change: Callable[[str], None] | None = None
        self.disable_submit = False

    def render(self, width: int) -> list[str]:
        return [""[:width]]

    def handle_input(self, data: str) -> None:
        _ = data
