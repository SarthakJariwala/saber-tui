from __future__ import annotations

from collections.abc import Callable

from saber_tui.utils import apply_background_to_line, slice_by_column, visible_width, wrap_text_with_ansi


def _pad_or_clip(line: str, width: int) -> str:
    if width <= 0:
        return ""

    line_width = visible_width(line)
    if line_width < width:
        return line + " " * (width - line_width)
    if line_width > width:
        return slice_by_column(line, 0, width, strict=True)
    return line


class Text:
    def __init__(
        self,
        text: str = "",
        padding_x: int = 1,
        padding_y: int = 1,
        custom_bg_fn: Callable[[str], str] | None = None,
    ) -> None:
        self._text = text
        self._padding_x = padding_x
        self._padding_y = padding_y
        self._custom_bg_fn = custom_bg_fn
        self._cached_text: str | None = None
        self._cached_width: int | None = None
        self._cached_lines: list[str] | None = None

    def set_text(self, text: str) -> None:
        self._text = text
        self.invalidate()

    def set_custom_bg_fn(self, custom_bg_fn: Callable[[str], str] | None = None) -> None:
        self._custom_bg_fn = custom_bg_fn
        self.invalidate()

    def invalidate(self) -> None:
        self._cached_text = None
        self._cached_width = None
        self._cached_lines = None

    def _apply_background(self, line: str, width: int) -> str:
        padded = _pad_or_clip(line, width)
        if self._custom_bg_fn is not None:
            return apply_background_to_line(padded, width, self._custom_bg_fn)
        return padded

    def render(self, width: int) -> list[str]:
        can_use_cache = self._custom_bg_fn is None
        if (
            can_use_cache
            and self._cached_lines is not None
            and self._cached_text == self._text
            and self._cached_width == width
        ):
            return self._cached_lines

        if not self._text or self._text.strip() == "":
            result: list[str] = []
            if can_use_cache:
                self._cached_text = self._text
                self._cached_width = width
                self._cached_lines = result
            return result

        render_width = max(0, width)
        normalized_text = self._text.replace("\t", "   ")
        content_width = max(1, render_width - self._padding_x * 2)
        wrapped_lines = wrap_text_with_ansi(normalized_text, content_width)
        left_margin = " " * self._padding_x
        right_margin = " " * self._padding_x

        content_lines = [
            self._apply_background(left_margin + line + right_margin, render_width) for line in wrapped_lines
        ]

        empty_line = " " * render_width
        empty_lines = [self._apply_background(empty_line, render_width) for _ in range(self._padding_y)]
        result = [*empty_lines, *content_lines, *empty_lines]

        if can_use_cache:
            self._cached_text = self._text
            self._cached_width = width
            self._cached_lines = result
        return result if result else [""]
