from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from saber_tui.utils import apply_background_to_line, slice_by_column, visible_width


class _Component(Protocol):
    def render(self, width: int) -> list[str]: ...

    def invalidate(self) -> None: ...


@dataclass
class _RenderCache:
    child_lines: list[str]
    width: int
    bg_sample: str | None
    lines: list[str]


def _pad_or_clip(line: str, width: int) -> str:
    if width <= 0:
        return ""

    line_width = visible_width(line)
    if line_width < width:
        return line + " " * (width - line_width)
    if line_width > width:
        return slice_by_column(line, 0, width, strict=True)
    return line


class Box:
    def __init__(
        self,
        padding_x: int = 1,
        padding_y: int = 1,
        bg_fn: Callable[[str], str] | None = None,
    ) -> None:
        self.children: list[_Component] = []
        self._padding_x = padding_x
        self._padding_y = padding_y
        self._bg_fn = bg_fn
        self._cache: _RenderCache | None = None

    def add_child(self, component: _Component) -> None:
        self.children.append(component)
        self._invalidate_cache()

    def remove_child(self, component: _Component) -> None:
        if component in self.children:
            self.children.remove(component)
            self._invalidate_cache()

    def clear(self) -> None:
        self.children.clear()
        self._invalidate_cache()

    def set_bg_fn(self, bg_fn: Callable[[str], str] | None = None) -> None:
        self._bg_fn = bg_fn
        self._invalidate_cache()

    def _invalidate_cache(self) -> None:
        self._cache = None

    def _matches_cache(self, width: int, child_lines: list[str]) -> bool:
        cache = self._cache
        bg_sample = self._bg_fn("test") if self._bg_fn is not None else None
        return (
            cache is not None
            and cache.width == width
            and cache.bg_sample == bg_sample
            and len(cache.child_lines) == len(child_lines)
            and all(line == child_lines[index] for index, line in enumerate(cache.child_lines))
        )

    def invalidate(self) -> None:
        self._invalidate_cache()
        for child in self.children:
            invalidate = getattr(child, "invalidate", None)
            if invalidate is not None:
                invalidate()

    def _apply_background(self, line: str, width: int) -> str:
        padded = _pad_or_clip(line, width)
        if self._bg_fn is not None:
            return apply_background_to_line(padded, width, self._bg_fn)
        return padded

    def render(self, width: int) -> list[str]:
        if len(self.children) == 0:
            return []

        render_width = max(0, width)
        content_width = max(1, render_width - self._padding_x * 2)
        left_pad = " " * self._padding_x

        child_lines: list[str] = []
        for child in self.children:
            for line in child.render(content_width):
                child_lines.append(left_pad + line)

        if len(child_lines) == 0:
            return []

        if self._matches_cache(width, child_lines):
            return self._cache.lines  # type: ignore[union-attr]

        result: list[str] = []
        for _ in range(self._padding_y):
            result.append(self._apply_background("", render_width))

        for line in child_lines:
            result.append(self._apply_background(line, render_width))

        for _ in range(self._padding_y):
            result.append(self._apply_background("", render_width))

        bg_sample = self._bg_fn("test") if self._bg_fn is not None else None
        self._cache = _RenderCache(child_lines=child_lines, width=width, bg_sample=bg_sample, lines=result)
        return result
