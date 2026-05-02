from __future__ import annotations

import asyncio
import inspect
import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import cast

import regex

from saber_tui.autocomplete import AutocompleteAbortSignal, AutocompleteProvider, AutocompleteSuggestions
from saber_tui.components.select_list import SelectItem, SelectList, SelectListTheme
from saber_tui.keybindings import get_keybindings
from saber_tui.kill_ring import KillRing
from saber_tui.tui import CURSOR_MARKER
from saber_tui.undo_stack import UndoStack
from saber_tui.utils import slice_by_column, strip_ansi, visible_width

_PASTE_MARKER_RE = re.compile(r"\[paste #(\d+)( \+\d+ lines| \d+ chars)?\]")
type _SegmentSpan = tuple[str, int, int]


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


@dataclass(frozen=True)
class _EditorState:
    lines: list[str]
    cursor_line: int
    cursor_col: int
    pastes: dict[int, str]
    paste_counter: int


@dataclass(frozen=True)
class _EditorYank:
    text: str
    start_line: int
    start_col: int
    end_line: int
    end_col: int


def _grapheme_spans(text: str, atomic_spans: Sequence[tuple[int, int]] | None = None) -> list[_SegmentSpan]:
    spans: list[_SegmentSpan] = []
    markers = sorted(atomic_spans or ())
    marker_index = 0
    for match in regex.finditer(r"\X", text):
        start = match.start()
        while marker_index < len(markers) and markers[marker_index][1] <= start:
            marker_index += 1
        if marker_index < len(markers):
            marker_start, marker_end = markers[marker_index]
            if marker_start <= start < marker_end:
                if start == marker_start:
                    spans.append((text[marker_start:marker_end], marker_start, marker_end))
                continue
        spans.append((match.group(0), match.start(), match.end()))
    return spans


def word_wrap_line(
    line: str,
    max_width: int,
    pre_segmented: Sequence[_SegmentSpan] | None = None,
) -> list[TextChunk]:
    if not line or max_width <= 0:
        return [TextChunk("", 0, 0)]
    if visible_width(line) <= max_width:
        return [TextChunk(line, 0, len(line))]

    spans = list(pre_segmented) if pre_segmented is not None else _grapheme_spans(line)
    chunks: list[TextChunk] = []
    chunk_start = 0
    current_width = 0
    wrap_index = -1
    wrap_width = 0

    for index, (segment, start, end) in enumerate(spans):
        segment_width = visible_width(segment)
        if current_width + segment_width > max_width:
            if wrap_index >= 0 and current_width - wrap_width + segment_width <= max_width:
                chunks.append(TextChunk(line[chunk_start:wrap_index], chunk_start, wrap_index))
                chunk_start = wrap_index
                current_width -= wrap_width
            elif chunk_start < start:
                chunks.append(TextChunk(line[chunk_start:start], chunk_start, start))
                chunk_start = start
                current_width = 0
            wrap_index = -1

        if segment_width > max_width and len(segment) > 1:
            sub_chunks = word_wrap_line(segment, max_width)
            for sub_chunk in sub_chunks[:-1]:
                chunks.append(
                    TextChunk(
                        sub_chunk.text,
                        start + sub_chunk.start_index,
                        start + sub_chunk.end_index,
                    )
                )
            last_sub_chunk = sub_chunks[-1]
            chunk_start = start + last_sub_chunk.start_index
            current_width = visible_width(last_sub_chunk.text)
            wrap_index = -1
            continue

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
        self.history: list[str] = []
        self.history_index = -1
        self.history_browse_original: str | None = None
        self.lines = [""]
        self.cursor_line = 0
        self.cursor_col = 0
        self.preferred_visual_col: int | None = None
        self.last_render_width: int | None = None
        self.kill_ring = KillRing()
        self.last_action: str | None = None
        self.last_yank: _EditorYank | None = None
        self.jump_mode: str | None = None
        self.undo_stack: UndoStack[_EditorState] = UndoStack()
        self.padding_x = max(0, int(self.options.padding_x))
        self.autocomplete_max_visible = max(3, min(20, int(self.options.autocomplete_max_visible)))
        self.autocomplete_provider: AutocompleteProvider | None = None
        self.autocomplete_signal: AutocompleteAbortSignal | None = None
        self.autocomplete_task: asyncio.Future[AutocompleteSuggestions | None] | None = None
        self.autocomplete_suggestions: AutocompleteSuggestions | None = None
        self.autocomplete_list: SelectList | None = None
        self.is_in_paste = False
        self.paste_buffer = ""
        self.pastes: dict[int, str] = {}
        self.paste_counter = 0

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

    def set_autocomplete_provider(self, provider: AutocompleteProvider) -> None:
        self.autocomplete_provider = provider
        self._clear_autocomplete()

    def is_showing_autocomplete(self) -> bool:
        return self.autocomplete_list is not None

    def get_text(self) -> str:
        return "\n".join(self.lines)

    def get_expanded_text(self) -> str:
        def replace_marker(match: re.Match[str]) -> str:
            paste_id = int(match.group(1))
            return self.pastes.get(paste_id, match.group(0))

        return _PASTE_MARKER_RE.sub(replace_marker, self.get_text())

    def get_lines(self) -> list[str]:
        return list(self.lines)

    def get_cursor(self) -> EditorCursor:
        self._clamp_cursor()
        return EditorCursor(self.cursor_line, self.cursor_col)

    def _valid_paste_marker_spans(self, text: str) -> list[tuple[int, int]]:
        spans: list[tuple[int, int]] = []
        for match in _PASTE_MARKER_RE.finditer(text):
            paste_id = int(match.group(1))
            if paste_id in self.pastes:
                spans.append((match.start(), match.end()))
        return spans

    def _segments(self, text: str) -> list[_SegmentSpan]:
        return _grapheme_spans(text, self._valid_paste_marker_spans(text))

    def _is_valid_paste_marker(self, text: str) -> bool:
        match = _PASTE_MARKER_RE.fullmatch(text)
        return bool(match and int(match.group(1)) in self.pastes)

    def _is_whitespace_segment(self, text: str) -> bool:
        return not self._is_valid_paste_marker(text) and text.isspace()

    def _is_punctuation_segment(self, text: str) -> bool:
        return not self._is_valid_paste_marker(text) and bool(regex.fullmatch(r"\p{P}+", text))

    def set_text(self, text: str) -> None:
        normalized = self._normalize_text(text)
        if normalized == self.get_text() and not self.pastes:
            return

        self._push_undo()
        self.last_action = None
        self._reset_sticky_column()
        self._exit_history_mode()
        self._clear_autocomplete()
        self.pastes = {}
        self.paste_counter = 0
        self._set_text_internal(normalized, emit_change=True)

    def add_to_history(self, text: str) -> None:
        if not text.strip():
            return
        if self.history and self.history[-1] == text:
            return
        self.history.append(text)
        if len(self.history) > 100:
            self.history = self.history[-100:]

    def insert_text_at_cursor(self, text: str) -> None:
        normalized = self._normalize_text(text)
        if not normalized:
            return

        self._push_undo()
        self.last_action = None
        self._reset_sticky_column()
        self._exit_history_mode()
        self._clear_autocomplete()
        self._insert_text_at_cursor_internal(normalized)
        self._prune_pastes_to_visible_markers()
        self._emit_change()
        self._request_render()

    def _paste_marker(self, content: str) -> str:
        self.paste_counter += 1
        paste_id = self.paste_counter
        self.pastes[paste_id] = content
        lines = content.split("\n")
        suffix = f"+{len(lines)} lines" if len(lines) > 10 else f"{len(content)} chars"
        return f"[paste #{paste_id} {suffix}]"

    def _handle_paste(self, pasted_text: str) -> None:
        normalized = self._normalize_text(pasted_text)
        if not normalized:
            return

        self._push_undo()
        text_to_insert = self._paste_marker(normalized) if len(normalized.split("\n")) > 10 else normalized
        self._insert_text_at_cursor_internal(text_to_insert)
        self._prune_pastes_to_visible_markers()
        self.last_action = None
        self._reset_sticky_column()
        self._exit_history_mode()
        self._clear_autocomplete()
        self._emit_change()
        self._request_render()

    def invalidate(self) -> None:
        pass

    def _content_width(self, width: int) -> int:
        return max(1, width - self.padding_x * 2)

    def _cursor_line_with_marker(self, text: str, cursor_col: int, max_width: int) -> str:
        before = text[:cursor_col]
        after = text[cursor_col:]
        graphemes = self._segments(after)
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
        self.last_render_width = width

        self._clamp_cursor()
        border = self.border_color("─" * width)
        if width <= 1:
            border = self.border_color("─"[:width])

        content_width = self._content_width(width)
        rendered: list[str] = [border]
        for logical_index, line in enumerate(self.lines):
            chunks = word_wrap_line(line, content_width, self._segments(line))
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

        if self.autocomplete_list is not None:
            rendered.extend(self.autocomplete_list.render(width))

        rendered.append(border)
        return [slice_by_column(line, 0, width, True) if visible_width(line) > width else line for line in rendered]

    def handle_input(self, data: str) -> None:
        if "\x1b[200~" in data:
            self.is_in_paste = True
            self.paste_buffer = ""
            data = data.replace("\x1b[200~", "")
        if self.is_in_paste:
            self.paste_buffer += data
            end_index = self.paste_buffer.find("\x1b[201~")
            if end_index != -1:
                paste_content = self.paste_buffer[:end_index]
                remaining = self.paste_buffer[end_index + len("\x1b[201~") :]
                self.is_in_paste = False
                self.paste_buffer = ""
                self._handle_paste(paste_content)
                if remaining:
                    self.handle_input(remaining)
            return

        kb = get_keybindings()
        if self.jump_mode is not None:
            mode = self.jump_mode
            self.jump_mode = None
            if kb.matches(data, "tui.select.cancel"):
                self._request_render()
                return
            if (mode == "forward" and kb.matches(data, "tui.editor.jumpForward")) or (
                mode == "backward" and kb.matches(data, "tui.editor.jumpBackward")
            ):
                self.last_action = None
                self._reset_sticky_column()
                self._clear_autocomplete()
                self._request_render()
                return
            if data and all(ord(char) >= 32 and ord(char) != 0x7F for char in data):
                self._jump_to_char(data[0], mode)
                self.last_action = None
                self._clear_autocomplete()
                self._request_render()
                return

        if self.autocomplete_list is not None:
            if (
                kb.matches(data, "tui.select.up")
                or kb.matches(data, "tui.select.down")
                or kb.matches(data, "tui.select.pageUp")
                or kb.matches(data, "tui.select.pageDown")
            ):
                self.autocomplete_list.handle_input(data)
                self._request_render()
                return
            if kb.matches(data, "tui.select.confirm") and self._apply_autocomplete():
                return
            if kb.matches(data, "tui.select.cancel"):
                self._clear_autocomplete()
                self._request_render()
                return

        if kb.matches(data, "tui.editor.undo"):
            self._undo()
            return
        if kb.matches(data, "tui.editor.deleteWordBackward"):
            self._clamp_cursor()
            should_push = self.cursor_col > 0 or self.cursor_line > 0
            if should_push:
                self._push_undo()
            if self._delete_word_backward():
                self._clear_autocomplete()
                self._exit_history_mode()
                self._prune_pastes_to_visible_markers()
                self._emit_change()
            self._request_render()
            return
        if kb.matches(data, "tui.editor.deleteWordForward"):
            self._clamp_cursor()
            line = self.lines[self.cursor_line]
            should_push = self.cursor_col < len(line) or self.cursor_line < len(self.lines) - 1
            if should_push:
                self._push_undo()
            if self._delete_word_forward():
                self._clear_autocomplete()
                self._exit_history_mode()
                self._prune_pastes_to_visible_markers()
                self._emit_change()
            self._request_render()
            return
        if kb.matches(data, "tui.editor.deleteToLineStart"):
            self._clamp_cursor()
            should_push = self.cursor_col > 0 or self.cursor_line > 0
            if should_push:
                self._push_undo()
            if self._delete_to_line_start():
                self._clear_autocomplete()
                self._exit_history_mode()
                self._prune_pastes_to_visible_markers()
                self._emit_change()
            self._request_render()
            return
        if kb.matches(data, "tui.editor.deleteToLineEnd"):
            self._clamp_cursor()
            line = self.lines[self.cursor_line]
            should_push = self.cursor_col < len(line) or self.cursor_line < len(self.lines) - 1
            if should_push:
                self._push_undo()
            if self._delete_to_line_end():
                self._clear_autocomplete()
                self._exit_history_mode()
                self._prune_pastes_to_visible_markers()
                self._emit_change()
            self._request_render()
            return
        if kb.matches(data, "tui.editor.yank"):
            self._yank()
            return
        if kb.matches(data, "tui.editor.yankPop"):
            self._yank_pop()
            return
        if kb.matches(data, "tui.input.newLine"):
            self._push_undo()
            self.last_action = None
            self._reset_sticky_column()
            self._clear_autocomplete()
            self._add_newline()
            return
        if kb.matches(data, "tui.input.submit") or data == "\n":
            if self._should_submit_on_backslash_enter(data):
                self._push_undo()
                self.last_action = None
                self._reset_sticky_column()
                self._clear_autocomplete()
                self._delete_backward()
                self._add_newline()
                return
            self._reset_sticky_column()
            self._clear_autocomplete()
            self._submit_value()
            return
        if kb.matches(data, "tui.input.tab"):
            force = True
            if self.autocomplete_provider is not None:
                force = self.autocomplete_provider.should_trigger_file_completion(
                    self.get_lines(),
                    self.cursor_line,
                    self.cursor_col,
                )
            self._update_autocomplete(force=force)
            if self.autocomplete_suggestions is not None and len(self.autocomplete_suggestions.items) == 1:
                self._apply_autocomplete()
            return
        if kb.matches(data, "tui.editor.jumpForward"):
            self.jump_mode = None if self.jump_mode == "forward" else "forward"
            self.last_action = None
            self._clear_autocomplete()
            self._request_render()
            return
        if kb.matches(data, "tui.editor.jumpBackward"):
            self.jump_mode = None if self.jump_mode == "backward" else "backward"
            self.last_action = None
            self._clear_autocomplete()
            self._request_render()
            return
        if kb.matches(data, "tui.editor.pageUp"):
            self.jump_mode = None
            self.last_action = None
            self._reset_sticky_column()
            self.cursor_line = max(0, self.cursor_line - 10)
            self.cursor_col = min(self.cursor_col, len(self.lines[self.cursor_line]))
            self.cursor_col = self._grapheme_boundary_at_or_after(self.lines[self.cursor_line], self.cursor_col)
            self._clear_autocomplete()
            self._request_render()
            return
        if kb.matches(data, "tui.editor.pageDown"):
            self.jump_mode = None
            self.last_action = None
            self._reset_sticky_column()
            self.cursor_line = min(len(self.lines) - 1, self.cursor_line + 10)
            self.cursor_col = min(self.cursor_col, len(self.lines[self.cursor_line]))
            self.cursor_col = self._grapheme_boundary_at_or_after(self.lines[self.cursor_line], self.cursor_col)
            self._clear_autocomplete()
            self._request_render()
            return
        if kb.matches(data, "tui.editor.cursorLineStart"):
            self.last_action = None
            self._reset_sticky_column()
            self.cursor_col = 0
            self._clear_autocomplete()
            self._request_render()
            return
        if kb.matches(data, "tui.editor.cursorWordLeft"):
            self.last_action = None
            self._move_word_left()
            self._clear_autocomplete()
            self._request_render()
            return
        if kb.matches(data, "tui.editor.cursorWordRight"):
            self.last_action = None
            self._move_word_right()
            self._clear_autocomplete()
            self._request_render()
            return
        if kb.matches(data, "tui.editor.cursorUp"):
            self.last_action = None
            if self._navigate_history(-1):
                return
            self._move_up()
            self._clear_autocomplete()
            self._request_render()
            return
        if kb.matches(data, "tui.editor.cursorDown"):
            self.last_action = None
            if self.history_index != -1 and self._navigate_history(1):
                return
            self._move_down()
            self._clear_autocomplete()
            self._request_render()
            return
        if kb.matches(data, "tui.editor.cursorLeft"):
            self.last_action = None
            self._move_left()
            self._clear_autocomplete()
            self._request_render()
            return
        if kb.matches(data, "tui.editor.cursorRight"):
            self.last_action = None
            self._move_right()
            self._clear_autocomplete()
            self._request_render()
            return
        if kb.matches(data, "tui.editor.cursorLineEnd"):
            self.last_action = None
            self._reset_sticky_column()
            self.cursor_col = len(self.lines[self.cursor_line])
            self._clear_autocomplete()
            self._request_render()
            return
        if kb.matches(data, "tui.editor.deleteCharBackward"):
            self.last_action = None
            should_push = self.cursor_col > 0 or self.cursor_line > 0
            if should_push:
                self._push_undo()
            if self._delete_backward():
                self._clear_autocomplete()
                self._exit_history_mode()
                self._prune_pastes_to_visible_markers()
                self._emit_change()
            self._request_render()
            return
        if kb.matches(data, "tui.editor.deleteCharForward"):
            self.last_action = None
            should_push = self.cursor_col < len(self.lines[self.cursor_line]) or self.cursor_line < len(self.lines) - 1
            if should_push:
                self._push_undo()
            if self._delete_forward():
                self._clear_autocomplete()
                self._exit_history_mode()
                self._prune_pastes_to_visible_markers()
                self._emit_change()
            self._request_render()
            return

        if data and not _has_control_chars(data):
            self._before_text_change()
            self._exit_history_mode()
            self._insert_text_at_cursor_internal(data)
            self._prune_pastes_to_visible_markers()
            if data.isspace():
                self.last_action = None
            self._emit_change()
            self._update_autocomplete()
            self._request_render()

    def _clear_autocomplete(self) -> None:
        if self.autocomplete_task is not None:
            if not self.autocomplete_task.done():
                self.autocomplete_task.cancel()
            self.autocomplete_task = None
        if self.autocomplete_signal is not None:
            self.autocomplete_signal.abort()
            self.autocomplete_signal = None
        self.autocomplete_suggestions = None
        self.autocomplete_list = None

    def _prune_pastes_to_visible_markers(self) -> None:
        visible_ids = {int(match.group(1)) for match in _PASTE_MARKER_RE.finditer(self.get_text())}
        self.pastes = {paste_id: content for paste_id, content in self.pastes.items() if paste_id in visible_ids}

    def _update_autocomplete(self, *, force: bool = False) -> None:
        if self.autocomplete_provider is None:
            return
        if self.autocomplete_task is not None:
            if not self.autocomplete_task.done():
                self.autocomplete_task.cancel()
            self.autocomplete_task = None
        if self.autocomplete_signal is not None:
            self.autocomplete_signal.abort()
        self.autocomplete_signal = AutocompleteAbortSignal()
        signal = self.autocomplete_signal
        try:
            suggestions = self.autocomplete_provider.get_suggestions(
                self.get_lines(),
                self.cursor_line,
                self.cursor_col,
                force=force,
                signal=signal,
            )
        except Exception:
            self._clear_autocomplete()
            return
        if inspect.isawaitable(suggestions):
            self._schedule_autocomplete_resolution(
                cast(Awaitable[AutocompleteSuggestions | None], suggestions),
                signal,
            )
            return
        self._set_autocomplete_result(suggestions, signal)

    async def _await_autocomplete_result(
        self,
        suggestions: Awaitable[AutocompleteSuggestions | None],
    ) -> AutocompleteSuggestions | None:
        return await suggestions

    def _schedule_autocomplete_resolution(
        self,
        suggestions: Awaitable[AutocompleteSuggestions | None],
        signal: AutocompleteAbortSignal,
    ) -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            try:
                result = asyncio.run(self._await_autocomplete_result(suggestions))
            except Exception:
                result = None
            self._set_autocomplete_result(result, signal)
            return

        task = asyncio.ensure_future(suggestions)
        self.autocomplete_task = task
        task.add_done_callback(lambda completed: self._finish_autocomplete_task(completed, signal))

    def _finish_autocomplete_task(
        self,
        task: asyncio.Future[AutocompleteSuggestions | None],
        signal: AutocompleteAbortSignal,
    ) -> None:
        if self.autocomplete_task is task:
            self.autocomplete_task = None
        if task.cancelled():
            return
        try:
            result = task.result()
        except Exception:
            result = None
        self._set_autocomplete_result(result, signal)

    def _set_autocomplete_result(
        self,
        suggestions: AutocompleteSuggestions | None,
        signal: AutocompleteAbortSignal,
    ) -> None:
        if signal.aborted or self.autocomplete_signal is not signal:
            return
        if suggestions is None or not suggestions.items:
            self.autocomplete_suggestions = None
            self.autocomplete_list = None
            self.autocomplete_signal = None
            self._request_render()
            return
        self.autocomplete_suggestions = suggestions
        items = [SelectItem(item.value, item.label, item.description) for item in suggestions.items]
        self.autocomplete_list = SelectList(items, self.autocomplete_max_visible, self.theme.select_list)
        self._request_render()

    def _apply_autocomplete(self) -> bool:
        if (
            self.autocomplete_provider is None
            or self.autocomplete_suggestions is None
            or self.autocomplete_list is None
        ):
            return False
        selected = self.autocomplete_list.get_selected_item()
        if selected is None:
            return False
        selected_index = self.autocomplete_list.items.index(selected)
        item = self.autocomplete_suggestions.items[selected_index]
        self._push_undo()
        result = self.autocomplete_provider.apply_completion(
            self.get_lines(),
            self.cursor_line,
            self.cursor_col,
            item,
            self.autocomplete_suggestions.prefix,
        )
        self.lines = result.lines
        self.cursor_line = result.cursor_line
        self.cursor_col = result.cursor_col
        self._reset_sticky_column()
        self._clear_autocomplete()
        self._prune_pastes_to_visible_markers()
        self._emit_change()
        self._request_render()
        return True

    def _normalize_text(self, text: str) -> str:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n").replace("\t", "    ")
        without_ansi = strip_ansi(normalized)
        return "".join(char for char in without_ansi if char == "\n" or not _has_control_chars(char))

    def _set_text_internal(self, text: str, *, emit_change: bool) -> None:
        normalized = self._normalize_text(text)
        if normalized == self.get_text():
            return
        self._clear_autocomplete()
        self._reset_sticky_column()
        self.lines = normalized.split("\n") if normalized else [""]
        self.cursor_line = len(self.lines) - 1
        self.cursor_col = len(self.lines[self.cursor_line])
        if emit_change:
            self._emit_change()
        self._request_render()

    def _exit_history_mode(self) -> None:
        self.history_index = -1
        self.history_browse_original = None

    def _is_editor_empty(self) -> bool:
        return len(self.lines) == 1 and self.lines[0] == ""

    def _navigate_history(self, direction: int) -> bool:
        if not self.history:
            return False
        if direction < 0 and not self._is_editor_empty() and self.history_index == -1:
            return False
        self._reset_sticky_column()
        if self.history_index == -1:
            self.history_browse_original = self.get_text()
            self._push_undo()
            self.history_index = 0
        else:
            self.history_index += -direction
        if self.history_index < 0:
            self.history_index = -1
            self._set_text_internal(self.history_browse_original or "", emit_change=True)
            self.history_browse_original = None
            return True
        self.history_index = min(self.history_index, len(self.history) - 1)
        self._set_text_internal(self.history[-1 - self.history_index], emit_change=True)
        return True

    def _add_newline(self) -> None:
        self._reset_sticky_column()
        self._exit_history_mode()
        self._insert_text_at_cursor_internal("\n")
        self._prune_pastes_to_visible_markers()
        self._emit_change()
        self._request_render()

    def _submit_value(self) -> None:
        self._exit_history_mode()
        if self.disable_submit:
            return
        if self.on_submit is not None:
            self.on_submit(self.get_expanded_text())
        self.undo_stack.clear()
        self.last_action = None
        self.last_yank = None

    def _should_submit_on_backslash_enter(self, data: str) -> bool:
        _ = data
        self._clamp_cursor()
        line = self.lines[self.cursor_line]
        return self.cursor_col > 0 and line[self.cursor_col - 1] == "\\"

    def _clamp_cursor(self) -> None:
        if not self.lines:
            self.lines = [""]
        self.cursor_line = max(0, min(self.cursor_line, len(self.lines) - 1))
        line = self.lines[self.cursor_line]
        self.cursor_col = self._grapheme_boundary_at_or_after(line, max(0, min(self.cursor_col, len(line))))

    def _grapheme_boundary_at_or_after(self, text: str, col: int) -> int:
        if col <= 0:
            return 0
        for _, start, end in self._segments(text):
            if col in (start, end):
                return col
            if start < col < end:
                return end
        return min(col, len(text))

    def _previous_grapheme_start(self, text: str, col: int) -> int:
        starts = [start for _, start, end in self._segments(text) if end <= col]
        return starts[-1] if starts else max(0, col - 1)

    def _next_grapheme_end(self, text: str, col: int) -> int:
        for _, start, end in self._segments(text):
            if start >= col:
                return end
        return min(len(text), col + 1)

    def _current_visual_col(self) -> int:
        return visible_width(self.lines[self.cursor_line][: self.cursor_col])

    def _terminal_content_width(self) -> int:
        terminal = getattr(self.tui, "terminal", None)
        width = self.last_render_width or getattr(terminal, "columns", 80)
        return self._content_width(int(width))

    def _wrap_chunks(self, line: str) -> list[TextChunk]:
        return word_wrap_line(line, self._terminal_content_width(), self._segments(line))

    def _current_wrap_chunk(self) -> tuple[list[TextChunk], int]:
        chunks = self._wrap_chunks(self.lines[self.cursor_line])
        for index, _ in enumerate(chunks):
            if _chunk_contains_cursor(chunks, index, self.cursor_col):
                return chunks, index
        return chunks, len(chunks) - 1

    def _current_wrap_visual_col(self) -> int:
        chunks, chunk_index = self._current_wrap_chunk()
        chunk = chunks[chunk_index]
        return visible_width(self.lines[self.cursor_line][chunk.start_index : self.cursor_col])

    def _column_for_visual_col(self, line: str, target: int) -> int:
        current_width = 0
        for segment, start, end in self._segments(line):
            next_width = current_width + visible_width(segment)
            if next_width > target:
                return start
            current_width = next_width
            if current_width == target:
                return end
        return len(line)

    def _column_for_wrap_visual_col(self, chunk: TextChunk, target: int) -> int:
        return chunk.start_index + self._column_for_visual_col(chunk.text, target)

    def _reset_sticky_column(self) -> None:
        self.preferred_visual_col = None

    def _move_left(self) -> None:
        self._reset_sticky_column()
        self._clamp_cursor()
        if self.cursor_col > 0:
            self.cursor_col = self._previous_grapheme_start(self.lines[self.cursor_line], self.cursor_col)
        elif self.cursor_line > 0:
            self.cursor_line -= 1
            self.cursor_col = len(self.lines[self.cursor_line])

    def _move_right(self) -> None:
        self._reset_sticky_column()
        self._clamp_cursor()
        if self.cursor_col < len(self.lines[self.cursor_line]):
            self.cursor_col = self._next_grapheme_end(self.lines[self.cursor_line], self.cursor_col)
        elif self.cursor_line < len(self.lines) - 1:
            self.cursor_line += 1
            self.cursor_col = 0

    def _word_left_position(self) -> tuple[int, int]:
        self._clamp_cursor()
        if self.cursor_col == 0:
            if self.cursor_line > 0:
                previous_line = self.cursor_line - 1
                return previous_line, len(self.lines[previous_line])
            return self.cursor_line, self.cursor_col

        line = self.lines[self.cursor_line]
        segments = [(segment, start, end) for segment, start, end in self._segments(line) if end <= self.cursor_col]
        new_col = self.cursor_col
        while segments and self._is_whitespace_segment(segments[-1][0]):
            _, start, _ = segments.pop()
            new_col = start

        if not segments:
            return self.cursor_line, new_col

        last_segment = segments[-1][0]
        if self._is_valid_paste_marker(last_segment):
            _, start, _ = segments.pop()
            new_col = start
        elif self._is_punctuation_segment(last_segment):
            while segments and self._is_punctuation_segment(segments[-1][0]):
                _, start, _ = segments.pop()
                new_col = start
        else:
            while (
                segments
                and not self._is_whitespace_segment(segments[-1][0])
                and not self._is_punctuation_segment(segments[-1][0])
                and not self._is_valid_paste_marker(segments[-1][0])
            ):
                _, start, _ = segments.pop()
                new_col = start

        return self.cursor_line, new_col

    def _word_right_position(self) -> tuple[int, int]:
        self._clamp_cursor()
        line = self.lines[self.cursor_line]
        if self.cursor_col >= len(line):
            if self.cursor_line < len(self.lines) - 1:
                return self.cursor_line + 1, 0
            return self.cursor_line, self.cursor_col

        segments = [(segment, start, end) for segment, start, end in self._segments(line) if start >= self.cursor_col]
        new_col = self.cursor_col
        while segments and self._is_whitespace_segment(segments[0][0]):
            _, _, end = segments.pop(0)
            new_col = end

        if not segments:
            return self.cursor_line, new_col

        first_segment = segments[0][0]
        if self._is_valid_paste_marker(first_segment):
            _, _, end = segments.pop(0)
            new_col = end
        elif self._is_punctuation_segment(first_segment):
            while segments and self._is_punctuation_segment(segments[0][0]):
                _, _, end = segments.pop(0)
                new_col = end
        else:
            while (
                segments
                and not self._is_whitespace_segment(segments[0][0])
                and not self._is_punctuation_segment(segments[0][0])
                and not self._is_valid_paste_marker(segments[0][0])
            ):
                _, _, end = segments.pop(0)
                new_col = end

        return self.cursor_line, new_col

    def _move_word_left(self) -> None:
        self._reset_sticky_column()
        self.cursor_line, self.cursor_col = self._word_left_position()

    def _move_word_right(self) -> None:
        self._reset_sticky_column()
        self.cursor_line, self.cursor_col = self._word_right_position()

    def _move_up(self) -> None:
        self._clamp_cursor()
        if self.preferred_visual_col is None:
            self.preferred_visual_col = self._current_wrap_visual_col()
        chunks, chunk_index = self._current_wrap_chunk()
        if chunk_index > 0:
            self.cursor_col = self._column_for_wrap_visual_col(chunks[chunk_index - 1], self.preferred_visual_col)
            return
        if self.cursor_line > 0:
            self.cursor_line -= 1
            previous_chunks = self._wrap_chunks(self.lines[self.cursor_line])
            self.cursor_col = self._column_for_wrap_visual_col(previous_chunks[-1], self.preferred_visual_col)

    def _move_down(self) -> None:
        self._clamp_cursor()
        if self.preferred_visual_col is None:
            self.preferred_visual_col = self._current_wrap_visual_col()
        chunks, chunk_index = self._current_wrap_chunk()
        if chunk_index < len(chunks) - 1:
            self.cursor_col = self._column_for_wrap_visual_col(chunks[chunk_index + 1], self.preferred_visual_col)
            return
        if self.cursor_line < len(self.lines) - 1:
            self.cursor_line += 1
            next_chunks = self._wrap_chunks(self.lines[self.cursor_line])
            self.cursor_col = self._column_for_wrap_visual_col(next_chunks[0], self.preferred_visual_col)

    def _jump_to_char(self, char: str, direction: str) -> None:
        if direction == "forward":
            for line_index in range(self.cursor_line, len(self.lines)):
                start = self.cursor_col + 1 if line_index == self.cursor_line else 0
                for grapheme, found, _ in self._segments(self.lines[line_index]):
                    if found >= start and char in grapheme:
                        self.cursor_line = line_index
                        self.cursor_col = found
                        self._reset_sticky_column()
                        return
        else:
            for line_index in range(self.cursor_line, -1, -1):
                end = self.cursor_col if line_index == self.cursor_line else len(self.lines[line_index])
                for grapheme, found, _ in reversed(self._segments(self.lines[line_index])):
                    if found < end and char in grapheme:
                        self.cursor_line = line_index
                        self.cursor_col = found
                        self._reset_sticky_column()
                        return

    def _delete_backward(self) -> bool:
        self._clamp_cursor()
        if self.cursor_col > 0:
            line = self.lines[self.cursor_line]
            start = self._previous_grapheme_start(line, self.cursor_col)
            self.lines[self.cursor_line] = line[:start] + line[self.cursor_col :]
            self.cursor_col = start
            self._reset_sticky_column()
            return True
        if self.cursor_line > 0:
            previous_len = len(self.lines[self.cursor_line - 1])
            self.lines[self.cursor_line - 1] += self.lines[self.cursor_line]
            del self.lines[self.cursor_line]
            self.cursor_line -= 1
            self.cursor_col = previous_len
            self._reset_sticky_column()
            return True
        return False

    def _delete_forward(self) -> bool:
        self._clamp_cursor()
        line = self.lines[self.cursor_line]
        if self.cursor_col < len(line):
            end = self._next_grapheme_end(line, self.cursor_col)
            self.lines[self.cursor_line] = line[: self.cursor_col] + line[end:]
            self._reset_sticky_column()
            return True
        if self.cursor_line < len(self.lines) - 1:
            self.lines[self.cursor_line] += self.lines[self.cursor_line + 1]
            del self.lines[self.cursor_line + 1]
            self._reset_sticky_column()
            return True
        return False

    def _delete_word_backward(self) -> bool:
        self._clamp_cursor()
        original_line = self.cursor_line
        original_col = self.cursor_col
        target_line, target_col = self._word_left_position()
        if target_line == original_line and target_col == original_col:
            return False

        if target_line != original_line:
            previous_len = len(self.lines[target_line])
            self.lines[target_line] += self.lines[original_line]
            del self.lines[original_line]
            self.cursor_line = target_line
            self.cursor_col = previous_len
            deleted = "\n"
        else:
            line = self.lines[original_line]
            deleted = line[target_col:original_col]
            self.lines[original_line] = line[:target_col] + line[original_col:]
            self.cursor_col = target_col

        self.kill_ring.push(deleted, prepend=True, accumulate=self.last_action == "kill")
        self.last_action = "kill"
        self.last_yank = None
        self._reset_sticky_column()
        return True

    def _delete_word_forward(self) -> bool:
        self._clamp_cursor()
        original_line = self.cursor_line
        original_col = self.cursor_col
        target_line, target_col = self._word_right_position()
        if target_line == original_line and target_col == original_col:
            return False

        if target_line != original_line:
            self.lines[original_line] += self.lines[target_line]
            del self.lines[target_line]
            deleted = "\n"
        else:
            line = self.lines[original_line]
            deleted = line[original_col:target_col]
            self.lines[original_line] = line[:original_col] + line[target_col:]

        if deleted:
            self.kill_ring.push(deleted, prepend=False, accumulate=self.last_action == "kill")
            self.last_action = "kill"
            self.last_yank = None
            self._reset_sticky_column()
            return True
        return False

    def _delete_to_line_start(self) -> bool:
        self._clamp_cursor()
        line = self.lines[self.cursor_line]
        if self.cursor_col > 0:
            deleted = line[: self.cursor_col]
            self.lines[self.cursor_line] = line[self.cursor_col :]
            self.cursor_col = 0
        elif self.cursor_line > 0:
            previous_len = len(self.lines[self.cursor_line - 1])
            self.lines[self.cursor_line - 1] += line
            del self.lines[self.cursor_line]
            self.cursor_line -= 1
            self.cursor_col = previous_len
            deleted = "\n"
        else:
            return False

        self.kill_ring.push(deleted, prepend=True, accumulate=self.last_action == "kill")
        self.last_action = "kill"
        self.last_yank = None
        self._reset_sticky_column()
        return True

    def _delete_to_line_end(self) -> bool:
        self._clamp_cursor()
        line = self.lines[self.cursor_line]
        if self.cursor_col < len(line):
            deleted = line[self.cursor_col :]
            self.lines[self.cursor_line] = line[: self.cursor_col]
        elif self.cursor_line < len(self.lines) - 1:
            self.lines[self.cursor_line] += self.lines[self.cursor_line + 1]
            del self.lines[self.cursor_line + 1]
            deleted = "\n"
        else:
            return False

        self.kill_ring.push(deleted, prepend=False, accumulate=self.last_action == "kill")
        self.last_action = "kill"
        self.last_yank = None
        self._reset_sticky_column()
        return True

    def _yank(self) -> None:
        text = self.kill_ring.peek()
        if not text:
            return
        self._push_undo()
        self._reset_sticky_column()
        self._exit_history_mode()
        self._clear_autocomplete()
        start_line = self.cursor_line
        start_col = self.cursor_col
        self._insert_text_at_cursor_internal(text)
        self._prune_pastes_to_visible_markers()
        self.last_yank = _EditorYank(text, start_line, start_col, self.cursor_line, self.cursor_col)
        self.last_action = "yank"
        self._emit_change()
        self._request_render()

    def _yank_pop(self) -> None:
        if self.last_action != "yank" or self.last_yank is None or len(self.kill_ring) <= 1:
            return
        self._push_undo()
        self._reset_sticky_column()
        self._exit_history_mode()
        self._clear_autocomplete()
        self._delete_yank_range(self.last_yank)
        self.kill_ring.rotate()
        text = self.kill_ring.peek() or ""
        start_line = self.cursor_line
        start_col = self.cursor_col
        self._insert_text_at_cursor_internal(text)
        self._prune_pastes_to_visible_markers()
        self.last_yank = _EditorYank(text, start_line, start_col, self.cursor_line, self.cursor_col)
        self.last_action = "yank"
        self._emit_change()
        self._request_render()

    def _delete_yank_range(self, yank: _EditorYank) -> None:
        if yank.start_line == yank.end_line:
            line = self.lines[yank.start_line]
            self.lines[yank.start_line] = line[: yank.start_col] + line[yank.end_col :]
        else:
            first = self.lines[yank.start_line][: yank.start_col]
            last = self.lines[yank.end_line][yank.end_col :]
            self.lines[yank.start_line : yank.end_line + 1] = [first + last]
        self.cursor_line = yank.start_line
        self.cursor_col = yank.start_col

    def _snapshot(self) -> _EditorState:
        return _EditorState(list(self.lines), self.cursor_line, self.cursor_col, dict(self.pastes), self.paste_counter)

    def _push_undo(self) -> None:
        self.undo_stack.push(self._snapshot())

    def _undo(self) -> None:
        snapshot = self.undo_stack.pop()
        if snapshot is None:
            return
        self.lines = list(snapshot.lines)
        self.cursor_line = snapshot.cursor_line
        self.cursor_col = snapshot.cursor_col
        self.pastes = dict(snapshot.pastes)
        self.paste_counter = snapshot.paste_counter
        self.last_action = None
        self.last_yank = None
        self._reset_sticky_column()
        self._exit_history_mode()
        self._clear_autocomplete()
        self._emit_change()
        self._request_render()

    def _before_text_change(self) -> None:
        if self.last_action != "type-word":
            self._push_undo()
        self.last_action = "type-word"
        self.last_yank = None
        self._reset_sticky_column()

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
