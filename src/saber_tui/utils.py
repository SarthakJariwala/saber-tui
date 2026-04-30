from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass

import regex
from wcwidth import wcswidth, wcwidth

RESET = "\x1b[0m"
_WIDTH_CACHE_SIZE = 512
_width_cache: dict[str, int] = {}
_CSI_FINAL_RE = re.compile(r"[\x40-\x7e]")
_SGR_RE = re.compile(r"^\x1b\[([\d;]*)m$")
_OSC8_RE = re.compile(r"^\x1b\]8;[^;]*;([^\x1b\x07]*)")
_ZERO_WIDTH_RE = regex.compile(r"^(?:\p{Default_Ignorable_Code_Point}|\p{Control}|\p{Mark}|\p{Surrogate})+$")
_LEADING_NON_PRINTING_RE = regex.compile(
    r"^[\p{Default_Ignorable_Code_Point}\p{Control}\p{Format}\p{Mark}\p{Surrogate}]+"
)
_THAI_LAO_AM_RE = re.compile("[\u0e33\u0eb3]")


@dataclass
class SliceResult:
    text: str
    width: int


@dataclass
class SegmentResult:
    before: str
    before_width: int
    after: str
    after_width: int


def graphemes(text: str) -> list[str]:
    return regex.findall(r"\X", text)


def _is_printable_ascii(text: str) -> bool:
    return all(0x20 <= ord(char) <= 0x7E for char in text)


def _terminated_escape(text: str, pos: int) -> tuple[str, int] | None:
    j = pos + 2
    while j < len(text):
        if text[j] == "\x07":
            return text[pos : j + 1], j + 1 - pos
        if text[j] == "\x1b" and j + 1 < len(text) and text[j + 1] == "\\":
            return text[pos : j + 2], j + 2 - pos
        j += 1
    return None


def extract_ansi_code(text: str, pos: int) -> tuple[str, int] | None:
    if pos >= len(text) or text[pos] != "\x1b" or pos + 1 >= len(text):
        return None

    next_char = text[pos + 1]

    if next_char == "[":
        j = pos + 2
        while j < len(text) and not _CSI_FINAL_RE.match(text[j]):
            j += 1
        if j < len(text):
            return text[pos : j + 1], j + 1 - pos
        return None

    if next_char in {"]", "_", "P"}:
        return _terminated_escape(text, pos)

    return None


def strip_ansi(text: str) -> str:
    if "\x1b" not in text:
        return text

    result: list[str] = []
    i = 0
    while i < len(text):
        ansi = extract_ansi_code(text, i)
        if ansi is not None:
            i += ansi[1]
            continue
        result.append(text[i])
        i += 1
    return "".join(result)


def _could_be_emoji(segment: str) -> bool:
    if not segment:
        return False
    codepoint = ord(segment[0])
    return (
        0x1F000 <= codepoint <= 0x1FBFF
        or 0x2300 <= codepoint <= 0x23FF
        or 0x2600 <= codepoint <= 0x27BF
        or 0x2B50 <= codepoint <= 0x2B55
        or "\ufe0f" in segment
        or "\u200d" in segment
        or len(segment) > 2
    )


def _char_width(char: str) -> int:
    if char == "\t":
        return 3
    width = wcwidth(char)
    return max(0, width)


def _grapheme_width(segment: str) -> int:
    if not segment:
        return 0
    if segment == "\t":
        return 3
    if _ZERO_WIDTH_RE.fullmatch(segment):
        return 0
    if _could_be_emoji(segment):
        return 2

    base = _LEADING_NON_PRINTING_RE.sub("", segment)
    if not base:
        return 0
    first = ord(base[0])
    if 0x1F1E6 <= first <= 0x1F1FF:
        return 2

    width = wcswidth(segment)
    if width >= 0:
        if any(char in "\u0e33\u0eb3" for char in segment[1:]):
            return width + sum(1 for char in segment[1:] if char in "\u0e33\u0eb3")
        return width

    return sum(_char_width(char) for char in segment)


def visible_width(text: str) -> int:
    if not text:
        return 0
    if _is_printable_ascii(text):
        return len(text)
    if text in _width_cache:
        return _width_cache[text]

    clean = strip_ansi(text)
    width = sum(_grapheme_width(segment) for segment in graphemes(clean))

    if len(_width_cache) >= _WIDTH_CACHE_SIZE:
        _width_cache.pop(next(iter(_width_cache)))
    _width_cache[text] = width
    return width


class _AnsiCodeTracker:
    def __init__(self) -> None:
        self.clear()

    def clear(self) -> None:
        self.bold = False
        self.dim = False
        self.italic = False
        self.underline = False
        self.blink = False
        self.inverse = False
        self.hidden = False
        self.strikethrough = False
        self.fg_color: str | None = None
        self.bg_color: str | None = None
        self.active_hyperlink: str | None = None

    def _reset_sgr(self) -> None:
        self.bold = False
        self.dim = False
        self.italic = False
        self.underline = False
        self.blink = False
        self.inverse = False
        self.hidden = False
        self.strikethrough = False
        self.fg_color = None
        self.bg_color = None

    def process(self, ansi_code: str) -> None:
        if ansi_code.startswith("\x1b]8;"):
            match = _OSC8_RE.match(ansi_code)
            self.active_hyperlink = match.group(1) if match and match.group(1) else None
            return
        match = _SGR_RE.match(ansi_code)
        if match is None:
            return

        params = match.group(1)
        if params in {"", "0"}:
            self._reset_sgr()
            return

        parts = params.split(";")
        i = 0
        while i < len(parts):
            try:
                code = int(parts[i])
            except ValueError:
                i += 1
                continue

            if code in {38, 48}:
                if i + 2 < len(parts) and parts[i + 1] == "5":
                    color_code = ";".join(parts[i : i + 3])
                    if code == 38:
                        self.fg_color = color_code
                    else:
                        self.bg_color = color_code
                    i += 3
                    continue
                if i + 4 < len(parts) and parts[i + 1] == "2":
                    color_code = ";".join(parts[i : i + 5])
                    if code == 38:
                        self.fg_color = color_code
                    else:
                        self.bg_color = color_code
                    i += 5
                    continue

            if code == 0:
                self._reset_sgr()
            elif code == 1:
                self.bold = True
            elif code == 2:
                self.dim = True
            elif code == 3:
                self.italic = True
            elif code == 4:
                self.underline = True
            elif code == 5:
                self.blink = True
            elif code == 7:
                self.inverse = True
            elif code == 8:
                self.hidden = True
            elif code == 9:
                self.strikethrough = True
            elif code == 21:
                self.bold = False
            elif code == 22:
                self.bold = False
                self.dim = False
            elif code == 23:
                self.italic = False
            elif code == 24:
                self.underline = False
            elif code == 25:
                self.blink = False
            elif code == 27:
                self.inverse = False
            elif code == 28:
                self.hidden = False
            elif code == 29:
                self.strikethrough = False
            elif code == 39:
                self.fg_color = None
            elif code == 49:
                self.bg_color = None
            elif 30 <= code <= 37 or 90 <= code <= 97:
                self.fg_color = str(code)
            elif 40 <= code <= 47 or 100 <= code <= 107:
                self.bg_color = str(code)
            i += 1

    def active_codes(self) -> str:
        codes: list[str] = []
        if self.bold:
            codes.append("1")
        if self.dim:
            codes.append("2")
        if self.italic:
            codes.append("3")
        if self.underline:
            codes.append("4")
        if self.blink:
            codes.append("5")
        if self.inverse:
            codes.append("7")
        if self.hidden:
            codes.append("8")
        if self.strikethrough:
            codes.append("9")
        if self.fg_color:
            codes.append(self.fg_color)
        if self.bg_color:
            codes.append(self.bg_color)

        result = f"\x1b[{';'.join(codes)}m" if codes else ""
        if self.active_hyperlink:
            result += f"\x1b]8;;{self.active_hyperlink}\x1b\\"
        return result

    def line_end_reset(self) -> str:
        result = ""
        if self.underline:
            result += "\x1b[24m"
        if self.active_hyperlink:
            result += "\x1b]8;;\x1b\\"
        return result


def _update_tracker_from_text(text: str, tracker: _AnsiCodeTracker) -> None:
    i = 0
    while i < len(text):
        ansi = extract_ansi_code(text, i)
        if ansi is not None:
            tracker.process(ansi[0])
            i += ansi[1]
        else:
            i += 1


def _split_into_tokens_with_ansi(text: str) -> list[str]:
    tokens: list[str] = []
    current = ""
    pending_ansi = ""
    in_whitespace = False
    i = 0

    while i < len(text):
        ansi = extract_ansi_code(text, i)
        if ansi is not None:
            pending_ansi += ansi[0]
            i += ansi[1]
            continue

        char = text[i]
        char_is_space = char == " "
        if char_is_space != in_whitespace and current:
            tokens.append(current)
            current = ""

        if pending_ansi:
            current += pending_ansi
            pending_ansi = ""

        in_whitespace = char_is_space
        current += char
        i += 1

    if pending_ansi:
        current += pending_ansi
    if current:
        tokens.append(current)
    return tokens


def _iter_ansi_and_graphemes(text: str) -> list[tuple[str, str]]:
    segments: list[tuple[str, str]] = []
    i = 0
    while i < len(text):
        ansi = extract_ansi_code(text, i)
        if ansi is not None:
            segments.append(("ansi", ansi[0]))
            i += ansi[1]
            continue

        end = i
        while end < len(text) and extract_ansi_code(text, end) is None:
            end += 1
        segments.extend(("grapheme", segment) for segment in graphemes(text[i:end]))
        i = end
    return segments


def _break_long_word(word: str, width: int, tracker: _AnsiCodeTracker) -> list[str]:
    if width <= 0:
        return [word]

    lines: list[str] = []
    current_line = tracker.active_codes()
    current_width = 0

    for kind, value in _iter_ansi_and_graphemes(word):
        if kind == "ansi":
            current_line += value
            tracker.process(value)
            continue

        grapheme_width = _grapheme_width(value)
        if current_width > 0 and current_width + grapheme_width > width:
            current_line += tracker.line_end_reset()
            lines.append(current_line)
            current_line = tracker.active_codes()
            current_width = 0

        if grapheme_width <= width:
            current_line += value
            current_width += grapheme_width

    if current_line:
        lines.append(current_line)
    return lines or [""]


def _wrap_single_line(line: str, width: int) -> list[str]:
    if not line:
        return [""]
    if width <= 0 or visible_width(line) <= width:
        return [line]

    wrapped: list[str] = []
    tracker = _AnsiCodeTracker()
    current_line = ""
    current_width = 0

    for token in _split_into_tokens_with_ansi(line):
        token_width = visible_width(token)
        is_whitespace = token.strip() == ""

        if token_width > width and not is_whitespace:
            if current_line:
                wrapped.append((current_line.rstrip() + tracker.line_end_reset()).rstrip())
                current_line = ""
                current_width = 0
            broken = _break_long_word(token, width, tracker)
            wrapped.extend(broken[:-1])
            current_line = broken[-1]
            current_width = visible_width(current_line)
            continue

        if current_width > 0 and current_width + token_width > width:
            wrapped.append((current_line.rstrip() + tracker.line_end_reset()).rstrip())
            if is_whitespace:
                current_line = tracker.active_codes()
                current_width = 0
            else:
                current_line = tracker.active_codes() + token
                current_width = token_width
        else:
            current_line += token
            current_width += token_width

        _update_tracker_from_text(token, tracker)

    if current_line:
        wrapped.append(current_line.rstrip())
    return wrapped or [""]


def wrap_text_with_ansi(text: str, width: int) -> list[str]:
    if not text:
        return [""]

    result: list[str] = []
    tracker = _AnsiCodeTracker()
    for input_line in text.split("\n"):
        prefix = tracker.active_codes() if result else ""
        result.extend(_wrap_single_line(prefix + input_line, width))
        _update_tracker_from_text(input_line, tracker)
    return result or [""]


def _truncate_fragment_to_width(text: str, max_width: int) -> SliceResult:
    if max_width <= 0 or not text:
        return SliceResult("", 0)

    result = ""
    width = 0
    pending_ansi = ""
    for kind, value in _iter_ansi_and_graphemes(text):
        if kind == "ansi":
            pending_ansi += value
            continue
        segment_width = _grapheme_width(value)
        if width + segment_width > max_width:
            break
        if pending_ansi:
            result += pending_ansi
            pending_ansi = ""
        result += value
        width += segment_width
    return SliceResult(result, width)


def _finalize_truncated_result(
    prefix: str,
    prefix_width: int,
    ellipsis: str,
    ellipsis_width: int,
    max_width: int,
    pad: bool,
) -> str:
    result = f"{prefix}{RESET}{ellipsis}{RESET}" if ellipsis else f"{prefix}{RESET}"
    if pad:
        result += " " * max(0, max_width - prefix_width - ellipsis_width)
    return result


def truncate_to_width(text: str, max_width: int, ellipsis: str = "...", pad: bool = False) -> str:
    if max_width <= 0:
        return ""
    if not text:
        return " " * max_width if pad else ""

    ellipsis_width = visible_width(ellipsis)
    text_width = visible_width(text)
    if text_width <= max_width:
        return text + (" " * (max_width - text_width) if pad else "")

    if ellipsis_width >= max_width:
        clipped = _truncate_fragment_to_width(ellipsis, max_width)
        if clipped.width == 0:
            return " " * max_width if pad else ""
        return _finalize_truncated_result("", 0, clipped.text, clipped.width, max_width, pad)

    target_width = max_width - ellipsis_width
    clipped = _truncate_fragment_to_width(text, target_width)
    return _finalize_truncated_result(clipped.text, clipped.width, ellipsis, ellipsis_width, max_width, pad)


def slice_with_width(line: str, start_col: int, length: int, strict: bool = False) -> SliceResult:
    if length <= 0:
        return SliceResult("", 0)

    end_col = start_col + length
    result = ""
    result_width = 0
    current_col = 0
    pending_ansi = ""
    i = 0

    while i < len(line):
        ansi = extract_ansi_code(line, i)
        if ansi is not None:
            if start_col <= current_col < end_col:
                result += ansi[0]
            elif current_col < start_col:
                pending_ansi += ansi[0]
            i += ansi[1]
            continue

        text_end = i
        while text_end < len(line) and extract_ansi_code(line, text_end) is None:
            text_end += 1

        for segment in graphemes(line[i:text_end]):
            width = _grapheme_width(segment)
            in_range = start_col <= current_col < end_col
            fits = not strict or current_col + width <= end_col
            if in_range and fits:
                if pending_ansi:
                    result += pending_ansi
                    pending_ansi = ""
                result += segment
                result_width += width
            current_col += width
            if current_col >= end_col:
                break
        i = text_end
        if current_col >= end_col:
            break

    return SliceResult(result, result_width)


def slice_by_column(line: str, start_col: int, length: int, strict: bool = False) -> str:
    return slice_with_width(line, start_col, length, strict).text


def extract_segments(
    line: str,
    before_end: int,
    after_start: int,
    after_len: int,
    strict_after: bool = False,
) -> SegmentResult:
    before = ""
    before_width = 0
    after = ""
    after_width = 0
    current_col = 0
    pending_ansi_before = ""
    after_started = False
    after_end = after_start + after_len
    tracker = _AnsiCodeTracker()
    i = 0

    while i < len(line):
        ansi = extract_ansi_code(line, i)
        if ansi is not None:
            tracker.process(ansi[0])
            if current_col < before_end:
                pending_ansi_before += ansi[0]
            elif after_started and after_start <= current_col < after_end:
                after += ansi[0]
            i += ansi[1]
            continue

        text_end = i
        while text_end < len(line) and extract_ansi_code(line, text_end) is None:
            text_end += 1

        for segment in graphemes(line[i:text_end]):
            width = _grapheme_width(segment)
            if current_col < before_end and current_col + width <= before_end:
                if pending_ansi_before:
                    before += pending_ansi_before
                    pending_ansi_before = ""
                before += segment
                before_width += width
            elif after_start <= current_col < after_end:
                if current_col + width <= after_end:
                    if not after_started:
                        after += tracker.active_codes()
                        after_started = True
                    after += segment
                    after_width += width

            current_col += width
            if current_col >= (before_end if after_len <= 0 else after_end):
                break
        i = text_end
        if current_col >= (before_end if after_len <= 0 else after_end):
            break

    return SegmentResult(before, before_width, after, after_width)


def apply_background_to_line(line: str, width: int, bg_fn: Callable[[str], str]) -> str:
    padding = " " * max(0, width - visible_width(line))
    return bg_fn(line + padding)


def normalize_terminal_output(text: str) -> str:
    if not _THAI_LAO_AM_RE.search(text):
        return text
    return "".join(unicodedata.normalize("NFKD", char) if char in "\u0e33\u0eb3" else char for char in text)
