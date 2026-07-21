from __future__ import annotations

import math
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from saber_tui.terminal_image import (
    ImageDimensions,
    encode_iterm2,
    encode_kitty,
    image_cell_size,
    image_dimensions,
    is_valid_image,
)
from saber_tui.utils import slice_by_column

if TYPE_CHECKING:
    from saber_tui.tui import TUI


@dataclass(frozen=True)
class ImageTheme:
    fallback_color: Callable[[str], str] | None = None


@dataclass(frozen=True)
class ImageOptions:
    max_width_cells: int = 60
    max_height_cells: int | None = None
    filename: str | None = None
    image_id: int | None = None


class Image:
    """An inline image with a width-safe textual fallback."""

    def __init__(
        self,
        tui: TUI,
        data: bytes | bytearray | memoryview,
        mime_type: str,
        theme: ImageTheme | None = None,
        options: ImageOptions | None = None,
        dimensions: ImageDimensions | None = None,
    ) -> None:
        self.tui = tui
        self.data = bytes(data)
        self.mime_type = mime_type.lower()
        self.theme = theme or ImageTheme()
        self.options = options or ImageOptions()
        self.dimensions = dimensions
        if self.options.image_id is not None and not 0 < self.options.image_id <= 0xFFFFFFFF:
            raise ValueError("Kitty image ID must be a nonzero uint32")
        self._image_id = self.options.image_id or secrets.randbelow(0xFFFFFFFF) + 1
        self._cached_key: tuple[object, ...] | None = None
        self._cached_lines: list[str] | None = None

    def get_image_id(self) -> int:
        return self._image_id

    def invalidate(self) -> None:
        self._cached_key = None
        self._cached_lines = None

    def _fallback(self, width: int) -> list[str]:
        filename = ""
        if self.options.filename:
            clean_filename = "".join(char for char in self.options.filename if char >= " " and char != "\x7f")
            filename = f" {clean_filename}"
        dimensions = self.dimensions or image_dimensions(self.data)
        size = f" {dimensions.width}x{dimensions.height}" if dimensions is not None else ""
        text = slice_by_column(f"[Image:{filename} [{self.mime_type}]{size}]", 0, max(0, width), True)
        if self.theme.fallback_color is not None:
            text = self.theme.fallback_color(text)
        return [text]

    def render(self, width: int) -> list[str]:
        protocol = self.tui.capabilities.image_protocol
        dimensions = image_dimensions(self.data)
        valid = dimensions is not None and is_valid_image(self.data, self.mime_type)
        if not valid or protocol is None or (protocol == "kitty" and self.mime_type != "image/png"):
            return self._fallback(width)
        dimensions = self.dimensions or dimensions
        max_columns = max(1, min(self.options.max_width_cells, width - 2))
        max_rows = self.options.max_height_cells or max(
            1, math.ceil(max_columns * self.tui.cell_size.width / self.tui.cell_size.height)
        )
        if protocol == "iterm2":
            max_rows = min(max_rows, max(1, self.tui.terminal.rows))
        size = image_cell_size(dimensions, self.tui.cell_size, max_columns=max_columns, max_rows=max_rows)
        key = (width, protocol, self.tui.cell_size, size)
        if key == self._cached_key and self._cached_lines is not None:
            return self._cached_lines
        blanks = ["" for _ in range(size.rows - 1)]
        if protocol == "kitty":
            result = [encode_kitty(self.data, self._image_id, size.columns, size.rows), *blanks]
        else:
            command = encode_iterm2(
                self.data,
                self.mime_type,
                size.columns,
                size.rows,
                filename=self.options.filename,
            )
            result = [*blanks, f"\x1b[{size.rows - 1}A{command}" if size.rows > 1 else command]
        self._cached_key = key
        self._cached_lines = result
        return result
