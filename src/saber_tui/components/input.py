from __future__ import annotations

import string
from collections.abc import Callable
from dataclasses import dataclass

import regex

from saber_tui.keybindings import get_keybindings
from saber_tui.keys import decode_kitty_printable
from saber_tui.kill_ring import KillRing
from saber_tui.tui import CURSOR_MARKER
from saber_tui.undo_stack import UndoStack
from saber_tui.utils import slice_by_column, visible_width


@dataclass(frozen=True)
class _InputState:
    value: str
    cursor: int


def _graphemes(text: str) -> list[str]:
    return regex.findall(r"\X", text)


def _is_whitespace(text: str) -> bool:
    return bool(text) and all(char.isspace() for char in text)


def _is_punctuation(text: str) -> bool:
    return bool(text) and all(char in string.punctuation for char in text)


def _has_control_chars(text: str) -> bool:
    for char in text:
        code = ord(char)
        if code < 32 or code == 0x7F or 0x80 <= code <= 0x9F:
            return True
    return False


def _sanitize_paste(text: str) -> str:
    return text.replace("\r\n", "").replace("\r", "").replace("\n", "").replace("\t", "    ")


class Input:
    def __init__(self) -> None:
        self.value = ""
        self.cursor = 0
        self.focused = False
        self.on_submit: Callable[[str], None] | None = None
        self.on_escape: Callable[[], None] | None = None

        self._paste_buffer = ""
        self._is_in_paste = False
        self._kill_ring = KillRing()
        self._last_action: str | None = None
        self._undo_stack: UndoStack[_InputState] = UndoStack()

    def get_value(self) -> str:
        return self.value

    def set_value(self, value: str) -> None:
        self.value = value
        self.cursor = min(self.cursor, len(value))

    def handle_input(self, data: str) -> None:
        if "\x1b[200~" in data:
            self._is_in_paste = True
            self._paste_buffer = ""
            data = data.replace("\x1b[200~", "")

        if self._is_in_paste:
            self._paste_buffer += data
            end_index = self._paste_buffer.find("\x1b[201~")
            if end_index != -1:
                paste_content = self._paste_buffer[:end_index]
                remaining = self._paste_buffer[end_index + len("\x1b[201~") :]
                self._handle_paste(paste_content)
                self._is_in_paste = False
                self._paste_buffer = ""
                if remaining:
                    self.handle_input(remaining)
            return

        kb = get_keybindings()

        if kb.matches(data, "tui.select.cancel"):
            if self.on_escape is not None:
                self.on_escape()
            return

        if kb.matches(data, "tui.editor.undo"):
            self._undo()
            return

        if kb.matches(data, "tui.input.submit") or data == "\n":
            if self.on_submit is not None:
                self.on_submit(self.value)
            return

        if kb.matches(data, "tui.editor.deleteCharBackward"):
            self._handle_backspace()
            return

        if kb.matches(data, "tui.editor.deleteCharForward"):
            self._handle_forward_delete()
            return

        if kb.matches(data, "tui.editor.deleteWordBackward"):
            self._delete_word_backwards()
            return

        if kb.matches(data, "tui.editor.deleteWordForward"):
            self._delete_word_forward()
            return

        if kb.matches(data, "tui.editor.deleteToLineStart"):
            self._delete_to_line_start()
            return

        if kb.matches(data, "tui.editor.deleteToLineEnd"):
            self._delete_to_line_end()
            return

        if kb.matches(data, "tui.editor.yank"):
            self._yank()
            return

        if kb.matches(data, "tui.editor.yankPop"):
            self._yank_pop()
            return

        if kb.matches(data, "tui.editor.cursorLeft"):
            self._last_action = None
            if self.cursor > 0:
                before_cursor = self.value[: self.cursor]
                segments = _graphemes(before_cursor)
                self.cursor -= len(segments[-1]) if segments else 1
            return

        if kb.matches(data, "tui.editor.cursorRight"):
            self._last_action = None
            if self.cursor < len(self.value):
                after_cursor = self.value[self.cursor :]
                segments = _graphemes(after_cursor)
                self.cursor += len(segments[0]) if segments else 1
            return

        if kb.matches(data, "tui.editor.cursorLineStart"):
            self._last_action = None
            self.cursor = 0
            return

        if kb.matches(data, "tui.editor.cursorLineEnd"):
            self._last_action = None
            self.cursor = len(self.value)
            return

        if kb.matches(data, "tui.editor.cursorWordLeft"):
            self._move_word_backwards()
            return

        if kb.matches(data, "tui.editor.cursorWordRight"):
            self._move_word_forwards()
            return

        kitty_printable = decode_kitty_printable(data)
        if kitty_printable is not None:
            self._insert_character(kitty_printable)
            return

        if not _has_control_chars(data):
            self._insert_character(data)

    def invalidate(self) -> None:
        pass

    def render(self, width: int) -> list[str]:
        if width <= 0:
            return [""]

        prompt = "> "
        if width <= visible_width(prompt):
            if self.focused:
                prompt_before_cursor = slice_by_column(prompt, 0, max(0, width - 1), True)
                cursor_cell = slice_by_column(prompt, visible_width(prompt_before_cursor), 1, True) or " "
                return [f"{prompt_before_cursor}{CURSOR_MARKER}\x1b[7m{cursor_cell}\x1b[27m"]
            line = slice_by_column(prompt, 0, width, True)
            return [line]

        available_width = width - visible_width(prompt)
        visible_text = ""
        cursor_display = self.cursor
        total_width = visible_width(self.value)

        if total_width < available_width:
            visible_text = self.value
        else:
            scroll_width = available_width - 1 if self.cursor == len(self.value) else available_width
            cursor_col = visible_width(self.value[: self.cursor])

            if scroll_width > 0:
                half_width = scroll_width // 2
                if cursor_col < half_width:
                    start_col = 0
                elif cursor_col > total_width - half_width:
                    start_col = max(0, total_width - scroll_width)
                else:
                    start_col = max(0, cursor_col - half_width)

                visible_text = slice_by_column(self.value, start_col, scroll_width, True)
                before_cursor = slice_by_column(self.value, start_col, max(0, cursor_col - start_col), True)
                cursor_display = len(before_cursor)
            else:
                cursor_display = 0

        after_cursor_segments = _graphemes(visible_text[cursor_display:])
        cursor_grapheme = after_cursor_segments[0] if after_cursor_segments else " "

        before_cursor = visible_text[:cursor_display]
        at_cursor = cursor_grapheme
        after_cursor = visible_text[cursor_display + len(at_cursor) :]

        marker = CURSOR_MARKER if self.focused else ""
        cursor_char = f"\x1b[7m{at_cursor}\x1b[27m"
        text_with_cursor = before_cursor + marker + cursor_char + after_cursor

        visual_length = visible_width(text_with_cursor)
        if visual_length > available_width:
            text_with_cursor = before_cursor + marker + "\x1b[7m \x1b[27m" + after_cursor
            visual_length = visible_width(text_with_cursor)
            while visible_width(text_with_cursor) > available_width and after_cursor:
                after_cursor = after_cursor[:-1]
                text_with_cursor = before_cursor + marker + "\x1b[7m \x1b[27m" + after_cursor
                visual_length = visible_width(text_with_cursor)

        padding = " " * max(0, available_width - visual_length)
        line = prompt + text_with_cursor + padding
        while visible_width(line) > width:
            line = line[:-1]
        return [line]

    def _insert_character(self, char: str) -> None:
        if _is_whitespace(char) or self._last_action != "type-word":
            self._push_undo()
        self._last_action = "type-word"

        self.value = self.value[: self.cursor] + char + self.value[self.cursor :]
        self.cursor += len(char)

    def _handle_backspace(self) -> None:
        self._last_action = None
        if self.cursor <= 0:
            return

        self._push_undo()
        before_cursor = self.value[: self.cursor]
        segments = _graphemes(before_cursor)
        grapheme_length = len(segments[-1]) if segments else 1
        self.value = self.value[: self.cursor - grapheme_length] + self.value[self.cursor :]
        self.cursor -= grapheme_length

    def _handle_forward_delete(self) -> None:
        self._last_action = None
        if self.cursor >= len(self.value):
            return

        self._push_undo()
        after_cursor = self.value[self.cursor :]
        segments = _graphemes(after_cursor)
        grapheme_length = len(segments[0]) if segments else 1
        self.value = self.value[: self.cursor] + self.value[self.cursor + grapheme_length :]

    def _delete_to_line_start(self) -> None:
        if self.cursor == 0:
            return

        self._push_undo()
        deleted_text = self.value[: self.cursor]
        self._kill_ring.push(deleted_text, prepend=True, accumulate=self._last_action == "kill")
        self._last_action = "kill"
        self.value = self.value[self.cursor :]
        self.cursor = 0

    def _delete_to_line_end(self) -> None:
        if self.cursor >= len(self.value):
            return

        self._push_undo()
        deleted_text = self.value[self.cursor :]
        self._kill_ring.push(deleted_text, prepend=False, accumulate=self._last_action == "kill")
        self._last_action = "kill"
        self.value = self.value[: self.cursor]

    def _delete_word_backwards(self) -> None:
        if self.cursor == 0:
            return

        was_kill = self._last_action == "kill"
        self._push_undo()
        old_cursor = self.cursor
        self._move_word_backwards()
        delete_from = self.cursor
        self.cursor = old_cursor

        deleted_text = self.value[delete_from : self.cursor]
        self._kill_ring.push(deleted_text, prepend=True, accumulate=was_kill)
        self._last_action = "kill"

        self.value = self.value[:delete_from] + self.value[self.cursor :]
        self.cursor = delete_from

    def _delete_word_forward(self) -> None:
        if self.cursor >= len(self.value):
            return

        was_kill = self._last_action == "kill"
        self._push_undo()
        old_cursor = self.cursor
        self._move_word_forwards()
        delete_to = self.cursor
        self.cursor = old_cursor

        deleted_text = self.value[self.cursor : delete_to]
        self._kill_ring.push(deleted_text, prepend=False, accumulate=was_kill)
        self._last_action = "kill"
        self.value = self.value[: self.cursor] + self.value[delete_to:]

    def _yank(self) -> None:
        text = self._kill_ring.peek()
        if not text:
            return

        self._push_undo()
        self.value = self.value[: self.cursor] + text + self.value[self.cursor :]
        self.cursor += len(text)
        self._last_action = "yank"

    def _yank_pop(self) -> None:
        if self._last_action != "yank" or len(self._kill_ring) <= 1:
            return

        self._push_undo()
        prev_text = self._kill_ring.peek() or ""
        self.value = self.value[: self.cursor - len(prev_text)] + self.value[self.cursor :]
        self.cursor -= len(prev_text)

        self._kill_ring.rotate()
        text = self._kill_ring.peek() or ""
        self.value = self.value[: self.cursor] + text + self.value[self.cursor :]
        self.cursor += len(text)
        self._last_action = "yank"

    def _push_undo(self) -> None:
        self._undo_stack.push(_InputState(self.value, self.cursor))

    def _undo(self) -> None:
        snapshot = self._undo_stack.pop()
        if snapshot is None:
            return

        self.value = snapshot.value
        self.cursor = snapshot.cursor
        self._last_action = None

    def _move_word_backwards(self) -> None:
        if self.cursor == 0:
            return

        self._last_action = None
        segments = _graphemes(self.value[: self.cursor])

        while segments and _is_whitespace(segments[-1]):
            self.cursor -= len(segments.pop())

        if not segments:
            return

        if _is_punctuation(segments[-1]):
            while segments and _is_punctuation(segments[-1]):
                self.cursor -= len(segments.pop())
        else:
            while segments and not _is_whitespace(segments[-1]) and not _is_punctuation(segments[-1]):
                self.cursor -= len(segments.pop())

    def _move_word_forwards(self) -> None:
        if self.cursor >= len(self.value):
            return

        self._last_action = None
        segments = _graphemes(self.value[self.cursor :])
        index = 0

        while index < len(segments) and _is_whitespace(segments[index]):
            self.cursor += len(segments[index])
            index += 1

        if index >= len(segments):
            return

        if _is_punctuation(segments[index]):
            while index < len(segments) and _is_punctuation(segments[index]):
                self.cursor += len(segments[index])
                index += 1
        else:
            while (
                index < len(segments)
                and not _is_whitespace(segments[index])
                and not _is_punctuation(segments[index])
            ):
                self.cursor += len(segments[index])
                index += 1

    def _handle_paste(self, pasted_text: str) -> None:
        self._last_action = None
        self._push_undo()
        clean_text = _sanitize_paste(pasted_text)
        self.value = self.value[: self.cursor] + clean_text + self.value[self.cursor :]
        self.cursor += len(clean_text)
