from __future__ import annotations

from saber_tui.utils import slice_by_column, truncate_to_width, visible_width


def _pad_or_clip(line: str, width: int) -> str:
    if width <= 0:
        return ""

    line_width = visible_width(line)
    if line_width < width:
        return line + " " * (width - line_width)
    if line_width > width:
        return slice_by_column(line, 0, width, strict=True)
    return line


def _truncate_plain_text(text: str, width: int) -> str:
    if width <= 0:
        return ""
    if visible_width(text) <= width:
        return text

    ellipsis = "..."
    ellipsis_width = visible_width(ellipsis)
    if ellipsis_width >= width:
        return ellipsis[:width]
    return text[: width - ellipsis_width] + ellipsis


class TruncatedText:
    def __init__(self, text: str = "", padding_x: int = 0, padding_y: int = 0) -> None:
        self._text = text
        self._padding_x = padding_x
        self._padding_y = padding_y
        self._cached_text: str | None = None
        self._cached_width: int | None = None
        self._cached_lines: list[str] | None = None

    def set_text(self, text: str) -> None:
        self._text = text
        self.invalidate()

    def invalidate(self) -> None:
        self._cached_text = None
        self._cached_width = None
        self._cached_lines = None

    def render(self, width: int) -> list[str]:
        if self._cached_lines is not None and self._cached_text == self._text and self._cached_width == width:
            return self._cached_lines

        render_width = max(0, width)
        result: list[str] = []
        empty_line = " " * render_width

        for _ in range(self._padding_y):
            result.append(empty_line)

        available_width = max(0, render_width - self._padding_x)
        single_line_text = self._text.split("\n", 1)[0]
        if "\x1b" in single_line_text or "\t" in single_line_text:
            display_text = truncate_to_width(single_line_text, available_width)
        else:
            display_text = _truncate_plain_text(single_line_text, available_width)

        line_with_padding = " " * self._padding_x + display_text + " " * self._padding_x
        result.append(_pad_or_clip(line_with_padding, render_width))

        for _ in range(self._padding_y):
            result.append(empty_line)

        self._cached_text = self._text
        self._cached_width = width
        self._cached_lines = result
        return result
