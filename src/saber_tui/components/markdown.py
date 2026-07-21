from __future__ import annotations

import os
import re
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, cast

import mistune

from saber_tui.terminal_image import is_image_line
from saber_tui.utils import apply_background_to_line, slice_by_column, visible_width, wrap_text_with_ansi

Style = Callable[[str], str]
HighlightCode = Callable[[str, str | None], list[str]]
Token = dict[str, Any]


def _identity(text: str) -> str:
    return text


@dataclass(frozen=True)
class DefaultTextStyle:
    """Base styling applied to ordinary markdown text."""

    color: Style | None = None
    bg_color: Style | None = None
    bold: bool = False
    italic: bool = False
    strikethrough: bool = False
    underline: bool = False


@dataclass(frozen=True)
class MarkdownTheme:
    """Style hooks used by :class:`Markdown`. Each hook may add ANSI codes."""

    heading: Style = _identity
    link: Style = _identity
    link_url: Style = _identity
    code: Style = _identity
    code_block: Style = _identity
    code_block_border: Style = _identity
    quote: Style = _identity
    quote_border: Style = _identity
    hr: Style = _identity
    list_bullet: Style = _identity
    bold: Style = _identity
    italic: Style = _identity
    strikethrough: Style = _identity
    underline: Style = _identity
    highlight_code: HighlightCode | None = None
    code_block_indent: str = "  "


@dataclass(frozen=True)
class MarkdownOptions:
    """Markdown rendering options.

    ``hyperlinks`` can force OSC 8 links on or off. The default detects known
    hyperlink-capable terminals conservatively.
    """

    preserve_ordered_list_markers: bool = False
    preserve_backslash_escapes: bool = False
    hyperlinks: bool | None = None


@dataclass(frozen=True)
class _InlineStyleContext:
    apply_text: Style
    style_prefix: str


_MARKDOWN = mistune.create_markdown(
    renderer="ast",
    plugins=["strikethrough", "table", "task_lists", "url"],
)
_LIST_MARKER_RE = re.compile(
    r"^(?P<prefix>(?: {0,3}>[ \t]?)*[ \t]*)(?P<marker>\d{1,9}[.)]|[-+*])"
    r"(?P<separator>[ \t]+|$)(?P<rest>.*)$"
)
_TOP_LEVEL_LIST_RE = re.compile(r"^(?P<indent> {0,3})(?P<marker>\d{1,9}[.)]|[-+*])(?P<separator>[ \t]+|$)")
_CONTAINER_LIST_RE = re.compile(r"(?:\d{1,9}[.)]|[-+*])[ \t]+")
_SOURCE_MARKER_RE = re.compile(r"\ue100([0-9a-f]+)\ue101")
_LIST_BREAK = "<!--saber-tui-list-break-->"
_EMAIL_RE = re.compile(
    r"(?<![\w@])([A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,})(?![\w@])"
)
_ESCAPABLE_RE = re.compile(r"\\([!\"#$%&'()*+,\-./:;<=>?@\[\\\]^_`{|}~])")
_ESCAPE_SENTINEL_RE = re.compile(r"\ue000([0-9a-f]{2,6})\ue001")
_FENCE_RE = re.compile(r"^(`{3,}|~{3,})(.*)$")


def _tmux_supports_hyperlinks() -> bool:
    try:
        result = subprocess.run(
            ["tmux", "display-message", "-p", "#{client_termfeatures}"],
            capture_output=True,
            check=True,
            text=True,
            timeout=0.25,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return "hyperlinks" in {feature.strip() for feature in result.stdout.split(",")}


@lru_cache(maxsize=1)
def _terminal_supports_hyperlinks() -> bool:
    term_program = os.environ.get("TERM_PROGRAM", "").lower()
    terminal_emulator = os.environ.get("TERMINAL_EMULATOR", "").lower()
    term = os.environ.get("TERM", "").lower()
    if os.environ.get("TMUX") or term.startswith("tmux"):
        return _tmux_supports_hyperlinks()
    if term.startswith("screen"):
        return False
    if terminal_emulator == "jetbrains-jediterm":
        return False
    return bool(
        os.environ.get("KITTY_WINDOW_ID")
        or os.environ.get("GHOSTTY_RESOURCES_DIR")
        or os.environ.get("WEZTERM_PANE")
        or os.environ.get("WARP_SESSION_ID")
        or os.environ.get("WARP_TERMINAL_SESSION_UUID")
        or os.environ.get("ITERM_SESSION_ID")
        or os.environ.get("WT_SESSION")
        or term_program
        in {
            "kitty",
            "ghostty",
            "wezterm",
            "warpterminal",
            "iterm.app",
            "vscode",
            "alacritty",
        }
        or "ghostty" in term
    )


def _hyperlink(text: str, url: str) -> str:
    return f"\x1b]8;;{url}\x1b\\{text}\x1b]8;;\x1b\\"


def _split_container_prefix(line: str, *, in_fence: bool) -> tuple[str, str]:
    """Split Markdown list/quote prefixes from possible fenced content."""

    index = 0
    spaces = len(line) - len(line.lstrip(" "))
    if spaces > 3 and not in_fence:
        return "", line
    index = spaces

    while index < len(line):
        if line[index] == ">":
            index += 1
            if index < len(line) and line[index] in " \t":
                index += 1
            while index < len(line) and line[index] == " ":
                index += 1
            continue
        marker = _CONTAINER_LIST_RE.match(line, index)
        if marker:
            index = marker.end()
            while index < len(line) and line[index] == " ":
                index += 1
            continue
        break
    return line[:index], line[index:]


def _trim_streaming_partial_fence(text: str) -> str:
    """Hide a partial final closing fence while markdown is streaming."""

    lines = text.split("\n")
    open_marker: str | None = None
    for line in lines:
        _, content = _split_container_prefix(line, in_fence=open_marker is not None)
        match = _FENCE_RE.match(content)
        if open_marker is None:
            if match:
                open_marker = match.group(1)
            continue
        if not match:
            continue
        marker = match.group(1)
        if marker[0] == open_marker[0] and len(marker) >= len(open_marker) and not match.group(2).strip():
            open_marker = None

    if open_marker and lines:
        _, content = _split_container_prefix(lines[-1], in_fence=True)
        if 0 < len(content) < len(open_marker) and content == open_marker[0] * len(content):
            lines[-1] = ""
    return "\n".join(lines)


def _list_kind(marker: str) -> tuple[bool, str]:
    return (marker[0].isdigit(), marker[-1] if marker[0].isdigit() else marker)


def _preserve_blank_lines_after_lists(text: str) -> str:
    """Keep source blank lines that Mistune drops after top-level lists."""

    lines = text.split("\n")
    active_kind: tuple[bool, str] | None = None
    content_indent = 0
    pending_blank: int | None = None
    open_marker: str | None = None

    for index, line in enumerate(lines):
        _, fence_content = _split_container_prefix(line, in_fence=open_marker is not None)
        fence = _FENCE_RE.match(fence_content)
        if open_marker is not None:
            if fence:
                marker = fence.group(1)
                if marker[0] == open_marker[0] and len(marker) >= len(open_marker) and not fence.group(2).strip():
                    open_marker = None
            continue

        if not line.strip():
            if active_kind is not None and pending_blank is None:
                pending_blank = index
            continue

        marker_match = _TOP_LEVEL_LIST_RE.match(line)
        marker_kind = _list_kind(marker_match.group("marker")) if marker_match else None
        leading_spaces = len(line) - len(line.lstrip(" "))

        if pending_blank is not None:
            continues_item = leading_spaces >= content_indent
            continues_list = marker_kind == active_kind
            if not continues_item and not continues_list:
                lines[pending_blank] = _LIST_BREAK
                active_kind = None
            pending_blank = None

        if marker_match and (active_kind is None or leading_spaces < content_indent):
            active_kind = marker_kind
            content_indent = marker_match.end()
        elif active_kind is not None and leading_spaces < content_indent:
            stripped = line.lstrip()
            if stripped.startswith(("#", ">", "```", "~~~", "<")):
                active_kind = None

        if fence:
            open_marker = fence.group(1)

    return "\n".join(lines)


def _annotate_source_list_markers(text: str) -> str:
    """Attach each source marker to its own AST list item."""

    lines = text.split("\n")
    open_marker: str | None = None
    for index, line in enumerate(lines):
        _, fence_content = _split_container_prefix(line, in_fence=open_marker is not None)
        fence = _FENCE_RE.match(fence_content)
        if open_marker is not None:
            if fence:
                marker = fence.group(1)
                if marker[0] == open_marker[0] and len(marker) >= len(open_marker) and not fence.group(2).strip():
                    open_marker = None
            continue

        match = _LIST_MARKER_RE.match(line)
        if match:
            marker = match.group("marker")
            annotation = f"\ue100{marker.encode().hex()}\ue101"
            rest = match.group("rest")
            task = re.match(r"(\[[ xX]\][ \t]+)(.*)", rest)
            quote = re.match(r"((?:>[ \t]?)+)(.*)", rest)
            fence_in_item = _FENCE_RE.match(rest)
            if task:
                rest = task.group(1) + annotation + task.group(2)
            elif quote:
                rest = quote.group(1) + annotation + quote.group(2)
            elif fence_in_item:
                rest = rest + " " + annotation
            else:
                rest = annotation + rest
            separator = match.group("separator") or " "
            lines[index] = match.group("prefix") + marker + separator + rest

        if fence:
            open_marker = fence.group(1)
    return "\n".join(lines)


def _protect_backslash_escapes(text: str) -> str:
    return _ESCAPABLE_RE.sub(lambda match: f"\ue000{ord(match.group(1)):x}\ue001", text)


def _restore_backslash_escapes(text: str) -> str:
    return _ESCAPE_SENTINEL_RE.sub(lambda match: "\\" + chr(int(match.group(1), 16)), text)


def _restore_token_escapes(tokens: list[Token]) -> None:
    for token in tokens:
        raw = token.get("raw")
        if isinstance(raw, str):
            token["raw"] = _restore_backslash_escapes(raw)
        attrs = token.get("attrs", {})
        for name, value in attrs.items():
            if isinstance(value, str):
                attrs[name] = _restore_backslash_escapes(value)
        _restore_token_escapes(token.get("children", []))


class Markdown:
    """A cached, ANSI-aware terminal markdown component.

    Repeated :meth:`set_text` or :meth:`append_text` calls are safe while a
    response is streaming. Every update invalidates the render cache, and
    incomplete fenced code blocks are rendered at a stable height.
    """

    def __init__(
        self,
        text: str = "",
        padding_x: int = 0,
        padding_y: int = 0,
        theme: MarkdownTheme | None = None,
        default_text_style: DefaultTextStyle | None = None,
        options: MarkdownOptions | None = None,
    ) -> None:
        self._text = text
        self._padding_x = padding_x
        self._padding_y = padding_y
        self._theme = theme or MarkdownTheme()
        self._default_text_style = default_text_style
        self._options = options or MarkdownOptions()
        self._default_style_prefix: str | None = None
        self._cached_text: str | None = None
        self._cached_width: int | None = None
        self._cached_lines: list[str] | None = None
        self._lock = threading.RLock()

    @property
    def text(self) -> str:
        with self._lock:
            return self._text

    def set_text(self, text: str) -> None:
        with self._lock:
            self._text = text
            self._invalidate_cache()

    def append_text(self, chunk: str) -> None:
        """Append a streaming chunk and invalidate the cached rendering."""

        if chunk:
            with self._lock:
                self._text += chunk
                self._invalidate_cache()

    def invalidate(self) -> None:
        with self._lock:
            self._invalidate_cache()

    def _invalidate_cache(self) -> None:
        self._cached_text = None
        self._cached_width = None
        self._cached_lines = None

    def render(self, width: int) -> list[str]:
        with self._lock:
            text = self._text
            if self._cached_lines is not None and self._cached_text == text and self._cached_width == width:
                return self._cached_lines

        if not text or not text.strip():
            result: list[str] = []
            self._cache(width, result, text)
            return result

        requested_width = width
        width = max(0, width)
        if width == 0:
            result = [""]
            self._cache(requested_width, result, text)
            return result

        padding_x = min(max(0, self._padding_x), max(0, (width - 1) // 2))
        content_width = max(1, width - padding_x * 2)
        normalized = text.replace("\t", "   ")
        normalized = _trim_streaming_partial_fence(normalized)
        normalized = _preserve_blank_lines_after_lists(normalized)
        if self._options.preserve_ordered_list_markers:
            normalized = _annotate_source_list_markers(normalized)
        if self._options.preserve_backslash_escapes:
            normalized = _protect_backslash_escapes(normalized)

        tokens = cast(list[Token], _MARKDOWN(normalized))
        if self._options.preserve_backslash_escapes:
            _restore_token_escapes(tokens)
        rendered: list[str] = []
        for index, token in enumerate(tokens):
            next_type = tokens[index + 1]["type"] if index + 1 < len(tokens) else None
            rendered.extend(self._render_token(token, content_width, next_type))
        rendered = [_SOURCE_MARKER_RE.sub("", line) for line in rendered]

        wrapped: list[str] = []
        for line in rendered:
            if is_image_line(line):
                wrapped.append(line)
            else:
                wrapped.extend(wrap_text_with_ansi(line, content_width))

        left_margin = " " * padding_x
        right_margin = " " * padding_x
        bg_fn = self._default_text_style.bg_color if self._default_text_style else None
        content_lines: list[str] = []
        for line in wrapped:
            if is_image_line(line):
                content_lines.append(line)
                continue
            line_with_margins = left_margin + line + right_margin
            if visible_width(line_with_margins) > width:
                line_with_margins = slice_by_column(line_with_margins, 0, width, strict=True)
            if bg_fn:
                content_lines.append(apply_background_to_line(line_with_margins, width, bg_fn))
            else:
                content_lines.append(line_with_margins + " " * max(0, width - visible_width(line_with_margins)))

        empty = " " * width
        empty_lines = [
            apply_background_to_line(empty, width, bg_fn) if bg_fn else empty for _ in range(self._padding_y)
        ]
        result = [*empty_lines, *content_lines, *empty_lines]
        self._cache(requested_width, result, text)
        return result if result else [""]

    def _cache(self, width: int, lines: list[str], text: str) -> None:
        with self._lock:
            if self._text != text:
                return
            self._cached_text = text
            self._cached_width = width
            self._cached_lines = lines

    def _apply_default_style(self, text: str) -> str:
        style = self._default_text_style
        if style is None:
            return text
        styled = style.color(text) if style.color else text
        if style.bold:
            styled = self._theme.bold(styled)
        if style.italic:
            styled = self._theme.italic(styled)
        if style.strikethrough:
            styled = self._theme.strikethrough(styled)
        if style.underline:
            styled = self._theme.underline(styled)
        return styled

    @staticmethod
    def _style_prefix(style: Style) -> str:
        sentinel = "\0"
        styled = style(sentinel)
        index = styled.find(sentinel)
        return styled[:index] if index >= 0 else ""

    def _default_context(self) -> _InlineStyleContext:
        if self._default_style_prefix is None:
            self._default_style_prefix = self._style_prefix(self._apply_default_style)
        return _InlineStyleContext(self._apply_default_style, self._default_style_prefix)

    def _render_token(
        self,
        token: Token,
        width: int,
        next_type: str | None = None,
        context: _InlineStyleContext | None = None,
    ) -> list[str]:
        token_type = token["type"]
        children = token.get("children", [])

        if token_type == "heading":
            level = token.get("attrs", {}).get("level", 1)
            prefix = f"{'#' * level} "

            def style(text: str) -> str:
                if level == 1:
                    return self._theme.heading(self._theme.bold(self._theme.underline(text)))
                return self._theme.heading(self._theme.bold(text))

            heading_context = _InlineStyleContext(style, self._style_prefix(style))
            text = self._render_inline(children, heading_context)
            line = style(prefix) + text if level >= 3 else text
            return [line, ""] if next_type and next_type != "blank_line" else [line]

        if token_type in {"paragraph", "block_text"}:
            line = self._render_inline(children, context)
            if token_type == "paragraph" and next_type and next_type not in {"list", "blank_line"}:
                return [line, ""]
            return [line]

        if token_type == "block_code":
            info = token.get("attrs", {}).get("info") or ""
            language = info.split(None, 1)[0] if info else None
            raw = token.get("raw", "")
            if raw.endswith("\n"):
                raw = raw[:-1]
            lines = [self._theme.code_block_border(f"```{info}")]
            if self._theme.highlight_code:
                highlighted = self._theme.highlight_code(raw, language)
                lines.extend(self._theme.code_block_indent + line for line in highlighted)
            else:
                lines.extend(self._theme.code_block_indent + self._theme.code_block(line) for line in raw.split("\n"))
            lines.append(self._theme.code_block_border("```"))
            if next_type and next_type != "blank_line":
                lines.append("")
            return lines

        if token_type == "list":
            return self._render_list(token, 0, width, context)

        if token_type == "table":
            return self._render_table(token, width, next_type, context)

        if token_type == "block_quote":

            def quote_style(text: str) -> str:
                return self._theme.quote(self._theme.italic(text))

            quote_prefix = self._style_prefix(quote_style)
            quote_context = _InlineStyleContext(_identity, quote_prefix)
            quote_width = max(1, width - 2)
            quote_lines: list[str] = []
            for index, child in enumerate(children):
                child_next = children[index + 1]["type"] if index + 1 < len(children) else None
                quote_lines.extend(self._render_token(child, quote_width, child_next, quote_context))
            while quote_lines and quote_lines[-1] == "":
                quote_lines.pop()
            lines: list[str] = []
            for line in quote_lines:
                if quote_prefix:
                    line = line.replace("\x1b[0m", f"\x1b[0m{quote_prefix}")
                styled = quote_style(line)
                for wrapped in wrap_text_with_ansi(styled, quote_width):
                    lines.append(self._theme.quote_border("│ ") + wrapped)
            if next_type and next_type != "blank_line":
                lines.append("")
            return lines

        if token_type == "thematic_break":
            lines = [self._theme.hr("─" * min(width, 80))]
            if next_type and next_type != "blank_line":
                lines.append("")
            return lines

        if token_type in {"block_html", "inline_html"}:
            raw = token.get("raw", "").strip()
            if raw == _LIST_BREAK:
                return [""]
            return [self._apply_default_style(raw)]

        if token_type == "blank_line":
            return [""]

        if children:
            return [self._render_inline(children, context)]
        if "raw" in token:
            return [self._apply_default_style(str(token["raw"]))]
        return []

    def _render_inline(
        self,
        tokens: list[Token],
        context: _InlineStyleContext | None = None,
        *,
        autolink: bool = True,
    ) -> str:
        resolved = context or self._default_context()
        result = ""
        for token in tokens:
            token_type = token["type"]
            children = token.get("children", [])
            if token_type == "text":
                raw = token.get("raw", "")
                if self._options.preserve_backslash_escapes:
                    raw = _restore_backslash_escapes(raw)
                if autolink:
                    result += self._render_plain_text(raw, resolved)
                else:
                    result += self._apply_text_lines(raw, resolved.apply_text)
            elif token_type in {"paragraph", "block_text"}:
                result += self._render_inline(children, resolved, autolink=autolink)
            elif token_type == "strong":
                result += (
                    self._theme.bold(self._render_inline(children, resolved, autolink=autolink)) + resolved.style_prefix
                )
            elif token_type == "emphasis":
                result += (
                    self._theme.italic(self._render_inline(children, resolved, autolink=autolink))
                    + resolved.style_prefix
                )
            elif token_type == "codespan":
                result += self._theme.code(token.get("raw", "")) + resolved.style_prefix
            elif token_type == "link":
                text = self._render_inline(children, resolved, autolink=False)
                raw_text = "".join(str(child.get("raw", "")) for child in children)
                result += self._render_link(
                    text,
                    raw_text,
                    token.get("attrs", {}).get("url", ""),
                    resolved.style_prefix,
                )
            elif token_type in {"linebreak", "softbreak"}:
                result += "\n"
            elif token_type == "strikethrough":
                result += (
                    self._theme.strikethrough(self._render_inline(children, resolved, autolink=autolink))
                    + resolved.style_prefix
                )
            elif token_type == "inline_html":
                result += resolved.apply_text(token.get("raw", ""))
            elif children:
                result += self._render_inline(children, resolved, autolink=autolink)
            elif "raw" in token:
                result += resolved.apply_text(str(token["raw"]))

        while resolved.style_prefix and result.endswith(resolved.style_prefix):
            result = result[: -len(resolved.style_prefix)]
        return result

    def _render_plain_text(self, text: str, context: _InlineStyleContext) -> str:
        # Mistune's URL plugin handles bare URLs, but not GFM email autolinks.
        result = ""
        position = 0
        for match in _EMAIL_RE.finditer(text):
            result += self._apply_text_lines(text[position : match.start()], context.apply_text)
            email = match.group(1)
            styled = self._theme.link(self._theme.underline(context.apply_text(email)))
            result += self._render_link(
                styled,
                email,
                f"mailto:{email}",
                context.style_prefix,
                already_styled=True,
            )
            position = match.end()
        result += self._apply_text_lines(text[position:], context.apply_text)
        return result

    @staticmethod
    def _apply_text_lines(text: str, style: Style) -> str:
        return "\n".join(style(part) for part in text.split("\n"))

    def _render_link(
        self,
        text: str,
        raw_text: str,
        url: str,
        style_prefix: str,
        *,
        already_styled: bool = False,
    ) -> str:
        styled = text if already_styled else self._theme.link(self._theme.underline(text))
        hyperlinks = self._options.hyperlinks
        if hyperlinks if hyperlinks is not None else _terminal_supports_hyperlinks():
            return _hyperlink(styled, url) + style_prefix
        comparable = url[7:] if url.startswith("mailto:") else url
        if raw_text in {url, comparable}:
            return styled + style_prefix
        return styled + self._theme.link_url(f" ({url})") + style_prefix

    def _take_source_marker(self, item: Token, fallback: str) -> str:
        for token in self._walk_tokens(item):
            raw = token.get("raw")
            if isinstance(raw, str) and (match := _SOURCE_MARKER_RE.search(raw)) is not None:
                token["raw"] = raw[: match.start()] + raw[match.end() :]
                return bytes.fromhex(match.group(1)).decode()
            attrs = token.get("attrs", {})
            for name, value in attrs.items():
                if not isinstance(value, str) or (match := _SOURCE_MARKER_RE.search(value)) is None:
                    continue
                attrs[name] = (value[: match.start()] + value[match.end() :]).rstrip()
                return bytes.fromhex(match.group(1)).decode()
        return fallback

    @staticmethod
    def _walk_tokens(token: Token):
        yield token
        for child in token.get("children", []):
            yield from Markdown._walk_tokens(child)

    def _render_list(
        self,
        token: Token,
        depth: int,
        width: int,
        context: _InlineStyleContext | None,
    ) -> list[str]:
        lines: list[str] = []
        attrs = token.get("attrs", {})
        ordered = bool(attrs.get("ordered"))
        start = int(attrs.get("start", 1))
        items = token.get("children", [])
        indent = "    " * depth
        loose = not token.get("tight", True)

        for index, item in enumerate(items):
            fallback = f"{start + index}." if ordered else "-"
            marker_text = self._take_source_marker(item, fallback)
            if item["type"] == "task_list_item":
                marker_text += f" [{'x' if item.get('attrs', {}).get('checked') else ' '}]"
            marker = marker_text + " "
            first_prefix = indent + self._theme.list_bullet(marker)
            continuation = indent + " " * visible_width(marker)
            item_width = max(1, width - visible_width(first_prefix))
            rendered_any = False
            for child in item.get("children", []):
                if child["type"] == "list":
                    lines.extend(self._render_list(child, depth + 1, width, context))
                    rendered_any = True
                    continue
                child_lines = self._render_token(child, item_width, context=context)
                for line in child_lines:
                    wrapped_lines = wrap_text_with_ansi(line, item_width)
                    for wrapped in wrapped_lines:
                        lines.append((continuation if rendered_any else first_prefix) + wrapped)
                        rendered_any = True
            if not rendered_any:
                lines.append(first_prefix)
            if loose and index < len(items) - 1:
                lines.append("")
        return lines

    @staticmethod
    def _longest_word_width(text: str, maximum: int = 30) -> int:
        return min(max((visible_width(word) for word in text.split()), default=0), maximum)

    def _render_table(
        self,
        token: Token,
        width: int,
        next_type: str | None,
        context: _InlineStyleContext | None,
    ) -> list[str]:
        children = token.get("children", [])
        head = next((child for child in children if child["type"] == "table_head"), None)
        body = next((child for child in children if child["type"] == "table_body"), None)
        headers = head.get("children", []) if head else []
        rows = body.get("children", []) if body else []
        column_count = len(headers)
        if not column_count:
            return []

        overhead = 3 * column_count + 1
        available = width - overhead
        if available < column_count:
            # A stable bordered table cannot fit. Keep all source content visible.
            raw_rows = [headers, *(row.get("children", []) for row in rows)]
            fallback = [
                " | ".join(self._render_inline(cell.get("children", []), context) for cell in row) for row in raw_rows
            ]
            result = [line for row in fallback for line in wrap_text_with_ansi(row, width)]
            if next_type and next_type != "blank_line":
                result.append("")
            return result

        rendered_headers = [self._render_inline(cell.get("children", []), context) for cell in headers]
        rendered_rows = [
            [self._render_inline(cell.get("children", []), context) for cell in row.get("children", [])] for row in rows
        ]
        natural = [visible_width(text) for text in rendered_headers]
        minimum = [max(1, self._longest_word_width(text)) for text in rendered_headers]
        for row in rendered_rows:
            for index in range(column_count):
                text = row[index] if index < len(row) else ""
                natural[index] = max(natural[index], visible_width(text))
                minimum[index] = max(minimum[index], max(1, self._longest_word_width(text)))

        minimum = self._fit_minimum_widths(minimum, available)
        total_natural = sum(natural) + overhead
        if total_natural <= width:
            column_widths = [max(natural[index], minimum[index]) for index in range(column_count)]
        else:
            growth_potential = sum(max(0, natural[index] - minimum[index]) for index in range(column_count))
            extra = max(0, available - sum(minimum))
            column_widths = [
                minimum[index]
                + (max(0, natural[index] - minimum[index]) * extra // growth_potential if growth_potential else 0)
                for index in range(column_count)
            ]
            remaining = available - sum(column_widths)
            while remaining:
                grew = False
                for index in range(column_count):
                    if remaining and column_widths[index] < natural[index]:
                        column_widths[index] += 1
                        remaining -= 1
                        grew = True
                if not grew:
                    break

        top = f"┌─{'─┬─'.join('─' * size for size in column_widths)}─┐"
        separator = f"├─{'─┼─'.join('─' * size for size in column_widths)}─┤"
        bottom = f"└─{'─┴─'.join('─' * size for size in column_widths)}─┘"
        lines: list[str] = [top]
        lines.extend(self._table_row_lines(rendered_headers, column_widths, header=True))
        lines.append(separator)
        for index, row in enumerate(rendered_rows):
            lines.extend(self._table_row_lines(row, column_widths))
            if index < len(rendered_rows) - 1:
                lines.append(separator)
        lines.append(bottom)
        if next_type and next_type != "blank_line":
            lines.append("")
        return lines

    @staticmethod
    def _fit_minimum_widths(minimum: list[int], available: int) -> list[int]:
        if sum(minimum) <= available:
            return minimum
        result = [1] * len(minimum)
        remaining = available - len(minimum)
        weights = [max(0, size - 1) for size in minimum]
        total = sum(weights)
        if remaining > 0:
            growth = [weight * remaining // total if total else 0 for weight in weights]
            result = [size + growth[index] for index, size in enumerate(result)]
            leftover = remaining - sum(growth)
            for index in range(len(result)):
                if not leftover:
                    break
                result[index] += 1
                leftover -= 1
        return result

    def _table_row_lines(self, cells: list[str], widths: list[int], *, header: bool = False) -> list[str]:
        wrapped = [
            wrap_text_with_ansi(cells[index] if index < len(cells) else "", widths[index])
            for index in range(len(widths))
        ]
        height = max((len(cell) for cell in wrapped), default=1)
        lines: list[str] = []
        for line_index in range(height):
            parts: list[str] = []
            for index, cell_lines in enumerate(wrapped):
                text = cell_lines[line_index] if line_index < len(cell_lines) else ""
                padded = text + " " * max(0, widths[index] - visible_width(text))
                parts.append(self._theme.bold(padded) if header else padded)
            lines.append(f"│ {' │ '.join(parts)} │")
        return lines


__all__ = ["DefaultTextStyle", "Markdown", "MarkdownOptions", "MarkdownTheme"]
