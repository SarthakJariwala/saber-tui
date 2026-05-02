from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from saber_tui.components.select_list import SelectListTheme
from saber_tui.keybindings import get_keybindings
from saber_tui.utils import strip_ansi


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


def _has_control_chars(text: str) -> bool:
    for char in text:
        code = ord(char)
        if code < 32 or code == 0x7F or 0x80 <= code <= 0x9F:
            return True
    return False


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
        self.lines = [""]
        self.cursor_line = 0
        self.cursor_col = 0
        self.padding_x = max(0, int(self.options.padding_x))
        self.autocomplete_max_visible = max(3, min(20, int(self.options.autocomplete_max_visible)))

    def get_padding_x(self) -> int:
        return self.padding_x

    def set_padding_x(self, padding: int) -> None:
        self.padding_x = max(0, int(padding))
        self._request_render()

    def get_autocomplete_max_visible(self) -> int:
        return self.autocomplete_max_visible

    def set_autocomplete_max_visible(self, max_visible: int) -> None:
        self.autocomplete_max_visible = max(3, min(20, int(max_visible)))
        self._request_render()

    def get_text(self) -> str:
        return "\n".join(self.lines)

    def get_expanded_text(self) -> str:
        return self.get_text()

    def get_lines(self) -> list[str]:
        return list(self.lines)

    def get_cursor(self) -> EditorCursor:
        self._clamp_cursor()
        return EditorCursor(self.cursor_line, self.cursor_col)

    def set_text(self, text: str) -> None:
        normalized = self._normalize_text(text)
        if normalized == self.get_text():
            return

        self.lines = normalized.split("\n") if normalized else [""]
        self.cursor_line = len(self.lines) - 1
        self.cursor_col = len(self.lines[self.cursor_line])
        self._emit_change()
        self._request_render()

    def insert_text_at_cursor(self, text: str) -> None:
        normalized = self._normalize_text(text)
        if not normalized:
            return

        self._insert_text_at_cursor_internal(normalized)
        self._emit_change()
        self._request_render()

    def invalidate(self) -> None:
        pass

    def render(self, width: int) -> list[str]:
        return [""[:width]]

    def handle_input(self, data: str) -> None:
        kb = get_keybindings()
        if kb.matches(data, "tui.editor.cursorLineStart"):
            self.cursor_col = 0
            self._request_render()
            return

        if data and not _has_control_chars(data):
            self.insert_text_at_cursor(data)

    def _normalize_text(self, text: str) -> str:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n").replace("\t", "    ")
        without_ansi = strip_ansi(normalized)
        return "".join(char for char in without_ansi if char == "\n" or not _has_control_chars(char))

    def _clamp_cursor(self) -> None:
        if not self.lines:
            self.lines = [""]
        self.cursor_line = max(0, min(self.cursor_line, len(self.lines) - 1))
        self.cursor_col = max(0, min(self.cursor_col, len(self.lines[self.cursor_line])))

    def _insert_text_at_cursor_internal(self, text: str) -> None:
        self._clamp_cursor()
        before = self.lines[self.cursor_line][: self.cursor_col]
        after = self.lines[self.cursor_line][self.cursor_col :]
        parts = text.split("\n")
        if len(parts) == 1:
            self.lines[self.cursor_line] = before + parts[0] + after
            self.cursor_col += len(parts[0])
            return

        replacement = [before + parts[0], *parts[1:-1], parts[-1] + after]
        self.lines[self.cursor_line : self.cursor_line + 1] = replacement
        self.cursor_line += len(parts) - 1
        self.cursor_col = len(parts[-1])

    def _emit_change(self) -> None:
        if self.on_change is not None:
            self.on_change(self.get_text())

    def _request_render(self) -> None:
        request_render = getattr(self.tui, "request_render", None)
        if request_render is not None:
            request_render()
