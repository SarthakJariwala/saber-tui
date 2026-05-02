from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import regex

from saber_tui.components.select_list import SelectListTheme
from saber_tui.keybindings import get_keybindings
from saber_tui.tui import CURSOR_MARKER
from saber_tui.utils import slice_by_column, strip_ansi, visible_width


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


def _grapheme_spans(text: str) -> list[tuple[str, int, int]]:
    spans: list[tuple[str, int, int]] = []
    for match in regex.finditer(r"\X", text):
        spans.append((match.group(0), match.start(), match.end()))
    return spans


def word_wrap_line(line: str, max_width: int, pre_segmented: object | None = None) -> list[TextChunk]:
    _ = pre_segmented
    if not line or max_width <= 0:
        return [TextChunk("", 0, 0)]
    if visible_width(line) <= max_width:
        return [TextChunk(line, 0, len(line))]

    spans = _grapheme_spans(line)
    chunks: list[TextChunk] = []
    chunk_start = 0
    current_width = 0
    wrap_index = -1
    wrap_width = 0

    for index, (segment, start, end) in enumerate(spans):
        segment_width = visible_width(segment)
        if current_width + segment_width > max_width:
            if wrap_index >= 0:
                chunks.append(TextChunk(line[chunk_start:wrap_index], chunk_start, wrap_index))
                chunk_start = wrap_index
                current_width -= wrap_width
            elif chunk_start < start:
                chunks.append(TextChunk(line[chunk_start:start], chunk_start, start))
                chunk_start = start
                current_width = 0
            wrap_index = -1

        current_width += segment_width
        next_segment = spans[index + 1][0] if index + 1 < len(spans) else ""
        if segment.isspace() and next_segment and not next_segment.isspace():
            wrap_index = end
            wrap_width = current_width

    chunks.append(TextChunk(line[chunk_start:], chunk_start, len(line)))
    return chunks


def _chunk_contains_cursor(chunks: list[TextChunk], index: int, cursor_col: int) -> bool:
    chunk = chunks[index]
    if index == len(chunks) - 1:
        return chunk.start_index <= cursor_col <= chunk.end_index
    return chunk.start_index <= cursor_col < chunk.end_index


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

    def _content_width(self, width: int) -> int:
        return max(1, width - self.padding_x * 2)

    def _cursor_line_with_marker(self, text: str, cursor_col: int, max_width: int) -> str:
        before = text[:cursor_col]
        after = text[cursor_col:]
        graphemes = _grapheme_spans(after)
        cursor_cell = graphemes[0][0] if graphemes else " "
        cursor_cell_len = len(cursor_cell)
        if visible_width(cursor_cell) > max_width:
            cursor_cell = " "

        cursor_width = visible_width(cursor_cell)
        available_width = max(0, max_width - cursor_width)
        before_width = min(visible_width(before), available_width)
        before_start = max(0, visible_width(before) - before_width)
        before = slice_by_column(before, before_start, before_width, True)

        rest_width = max(0, available_width - visible_width(before))
        rest = slice_by_column(after[cursor_cell_len:], 0, rest_width, True)
        marker = CURSOR_MARKER if self.focused else ""
        return f"{before}{marker}\x1b[7m{cursor_cell}\x1b[27m{rest}"

    def render(self, width: int) -> list[str]:
        if width <= 0:
            return [""]

        self._clamp_cursor()
        border = self.border_color("─" * width)
        if width <= 1:
            border = self.border_color("─"[:width])

        content_width = self._content_width(width)
        rendered: list[str] = [border]
        for logical_index, line in enumerate(self.lines):
            chunks = word_wrap_line(line, content_width)
            for chunk_index, chunk in enumerate(chunks):
                chunk_text = chunk.text
                if logical_index == self.cursor_line and _chunk_contains_cursor(chunks, chunk_index, self.cursor_col):
                    chunk_cursor = self.cursor_col - chunk.start_index
                    chunk_text = self._cursor_line_with_marker(chunk_text, chunk_cursor, content_width)

                left_padding = " " * min(self.padding_x, max(0, width))
                rendered_line = left_padding + chunk_text
                if CURSOR_MARKER in chunk_text and visible_width(rendered_line) > width:
                    left_padding = slice_by_column(left_padding, 0, max(0, width - visible_width(chunk_text)), True)
                    rendered_line = left_padding + chunk_text
                if visible_width(rendered_line) > width:
                    rendered_line = slice_by_column(rendered_line, 0, width, True)
                rendered.append(rendered_line + " " * max(0, width - visible_width(rendered_line)))

        rendered.append(border)
        return [slice_by_column(line, 0, width, True) if visible_width(line) > width else line for line in rendered]

    def handle_input(self, data: str) -> None:
        kb = get_keybindings()
        if kb.matches(data, "tui.editor.cursorLineStart"):
            self.cursor_col = 0
            self._request_render()
            return
        if kb.matches(data, "tui.editor.cursorUp"):
            self._move_up()
            self._request_render()
            return
        if kb.matches(data, "tui.editor.cursorDown"):
            self._move_down()
            self._request_render()
            return
        if kb.matches(data, "tui.editor.cursorLeft"):
            self._move_left()
            self._request_render()
            return
        if kb.matches(data, "tui.editor.cursorRight"):
            self._move_right()
            self._request_render()
            return
        if kb.matches(data, "tui.editor.cursorLineEnd"):
            self.cursor_col = len(self.lines[self.cursor_line])
            self._request_render()
            return
        if kb.matches(data, "tui.editor.deleteCharBackward"):
            if self._delete_backward():
                self._emit_change()
            self._request_render()
            return
        if kb.matches(data, "tui.editor.deleteCharForward"):
            if self._delete_forward():
                self._emit_change()
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
        line = self.lines[self.cursor_line]
        self.cursor_col = self._grapheme_boundary_at_or_after(line, max(0, min(self.cursor_col, len(line))))

    def _grapheme_boundary_at_or_after(self, text: str, col: int) -> int:
        if col <= 0:
            return 0
        for _, start, end in _grapheme_spans(text):
            if col in (start, end):
                return col
            if start < col < end:
                return end
        return min(col, len(text))

    def _previous_grapheme_start(self, text: str, col: int) -> int:
        starts = [start for _, start, end in _grapheme_spans(text) if end <= col]
        return starts[-1] if starts else max(0, col - 1)

    def _next_grapheme_end(self, text: str, col: int) -> int:
        for _, start, end in _grapheme_spans(text):
            if start >= col:
                return end
        return min(len(text), col + 1)

    def _move_left(self) -> None:
        self._clamp_cursor()
        if self.cursor_col > 0:
            self.cursor_col = self._previous_grapheme_start(self.lines[self.cursor_line], self.cursor_col)
        elif self.cursor_line > 0:
            self.cursor_line -= 1
            self.cursor_col = len(self.lines[self.cursor_line])

    def _move_right(self) -> None:
        self._clamp_cursor()
        if self.cursor_col < len(self.lines[self.cursor_line]):
            self.cursor_col = self._next_grapheme_end(self.lines[self.cursor_line], self.cursor_col)
        elif self.cursor_line < len(self.lines) - 1:
            self.cursor_line += 1
            self.cursor_col = 0

    def _move_up(self) -> None:
        self._clamp_cursor()
        if self.cursor_line > 0:
            self.cursor_line -= 1
            line = self.lines[self.cursor_line]
            self.cursor_col = self._grapheme_boundary_at_or_after(line, min(self.cursor_col, len(line)))

    def _move_down(self) -> None:
        self._clamp_cursor()
        if self.cursor_line < len(self.lines) - 1:
            self.cursor_line += 1
            line = self.lines[self.cursor_line]
            self.cursor_col = self._grapheme_boundary_at_or_after(line, min(self.cursor_col, len(line)))

    def _delete_backward(self) -> bool:
        self._clamp_cursor()
        if self.cursor_col > 0:
            line = self.lines[self.cursor_line]
            start = self._previous_grapheme_start(line, self.cursor_col)
            self.lines[self.cursor_line] = line[:start] + line[self.cursor_col :]
            self.cursor_col = start
            return True
        if self.cursor_line > 0:
            previous_len = len(self.lines[self.cursor_line - 1])
            self.lines[self.cursor_line - 1] += self.lines[self.cursor_line]
            del self.lines[self.cursor_line]
            self.cursor_line -= 1
            self.cursor_col = previous_len
            return True
        return False

    def _delete_forward(self) -> bool:
        self._clamp_cursor()
        line = self.lines[self.cursor_line]
        if self.cursor_col < len(line):
            end = self._next_grapheme_end(line, self.cursor_col)
            self.lines[self.cursor_line] = line[: self.cursor_col] + line[end:]
            return True
        if self.cursor_line < len(self.lines) - 1:
            self.lines[self.cursor_line] += self.lines[self.cursor_line + 1]
            del self.lines[self.cursor_line + 1]
            return True
        return False

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
