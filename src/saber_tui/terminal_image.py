"""Pure helpers for terminal graphics protocols (Kitty and iTerm2)."""

from __future__ import annotations

import base64
import math
import os
import struct
import zlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

ImageProtocol = Literal["kitty", "iterm2"]


@dataclass(frozen=True)
class TerminalCapabilities:
    image_protocol: ImageProtocol | None = None

    @property
    def images(self) -> bool:
        return self.image_protocol is not None


@dataclass(frozen=True)
class CellSize:
    width: int = 9
    height: int = 18


@dataclass(frozen=True)
class ImageDimensions:
    width: int
    height: int


@dataclass(frozen=True)
class ImageCellSize:
    columns: int
    rows: int


def detect_terminal_capabilities(env: Mapping[str, str] | None = None) -> TerminalCapabilities:
    env = os.environ if env is None else env
    term = env.get("TERM", "").lower()
    if env.get("TMUX") or term.startswith(("tmux", "screen")):
        return TerminalCapabilities()
    program = env.get("TERM_PROGRAM", "").lower()
    emulator = env.get("TERMINAL_EMULATOR", "").lower()
    if emulator == "jetbrains-jediterm" or env.get("WT_SESSION") or program in {"vscode", "alacritty"}:
        return TerminalCapabilities()
    if env.get("ITERM_SESSION_ID") or program == "iterm.app":
        return TerminalCapabilities("iterm2")
    if (
        env.get("KITTY_WINDOW_ID")
        or env.get("GHOSTTY_RESOURCES_DIR")
        or env.get("WEZTERM_PANE")
        or env.get("WARP_SESSION_ID")
        or env.get("WARP_TERMINAL_SESSION_UUID")
        or program in {"kitty", "ghostty", "wezterm", "warpterminal"}
        or "ghostty" in term
    ):
        return TerminalCapabilities("kitty")
    return TerminalCapabilities()


def is_image_line(line: str) -> bool:
    return (
        line.startswith("\x1b_G") or line.startswith("\x1b]1337;File=") or "\x1b_G" in line or "\x1b]1337;File=" in line
    )


def encode_kitty(data: bytes, image_id: int, columns: int, rows: int) -> str:
    if not 0 < image_id <= 0xFFFFFFFF:
        raise ValueError("Kitty image ID must be a nonzero uint32")
    if columns < 1 or rows < 1:
        raise ValueError("Kitty image dimensions must be positive")
    payload = base64.b64encode(data).decode("ascii")
    chunks = [payload[i : i + 4096] for i in range(0, len(payload), 4096)] or [""]
    result: list[str] = []
    for index, chunk in enumerate(chunks):
        more = int(index != len(chunks) - 1)
        metadata = f"a=T,f=100,i={image_id},c={columns},r={rows},q=2,C=1,m={more}" if index == 0 else f"m={more}"
        result.append(f"\x1b_G{metadata};{chunk}\x1b\\")
    return "".join(result)


def encode_kitty_delete(image_id: int) -> str:
    if not 0 < image_id <= 0xFFFFFFFF:
        raise ValueError("Kitty image ID must be a nonzero uint32")
    return f"\x1b_Ga=d,d=I,i={image_id},q=2;\x1b\\"


def encode_iterm2(data: bytes, mime_type: str, columns: int, rows: int, filename: str | None = None) -> str:
    payload = base64.b64encode(data).decode("ascii")
    name = f"name={base64.b64encode(filename.encode()).decode()};" if filename else ""
    return (
        f"\x1b]1337;File=inline=1;{name}width={columns};height={rows};preserveAspectRatio=1;"
        f"type={mime_type};size={len(data)}:{payload}\x07"
    )


def image_dimensions(data: bytes) -> ImageDimensions | None:
    if len(data) >= 33 and data.startswith(b"\x89PNG\r\n\x1a\n") and data[12:16] == b"IHDR":
        width, height = struct.unpack(">II", data[16:24])
    elif data.startswith((b"GIF87a", b"GIF89a")) and len(data) >= 10:
        width, height = struct.unpack("<HH", data[6:10])
    elif (
        len(data) >= 30
        and data.startswith(b"RIFF")
        and data[8:12] == b"WEBP"
        and int.from_bytes(data[4:8], "little") + 8 <= len(data)
    ):
        if data[12:16] == b"VP8X":
            width = 1 + int.from_bytes(data[24:27], "little")
            height = 1 + int.from_bytes(data[27:30], "little")
        elif data[12:16] == b"VP8 " and data[23:26] == b"\x9d\x01\x2a":
            width = int.from_bytes(data[26:28], "little") & 0x3FFF
            height = int.from_bytes(data[28:30], "little") & 0x3FFF
        elif data[12:16] == b"VP8L" and data[20] == 0x2F:
            bits = int.from_bytes(data[21:25], "little")
            width = (bits & 0x3FFF) + 1
            height = ((bits >> 14) & 0x3FFF) + 1
        else:
            return None
    elif data.startswith(b"\xff\xd8"):
        pos = 2
        while pos + 9 <= len(data):
            if data[pos] != 0xFF:
                pos += 1
                continue
            marker = data[pos + 1]
            if marker in range(0xC0, 0xC4) and pos + 9 <= len(data):
                segment_length = int.from_bytes(data[pos + 2 : pos + 4], "big")
                if segment_length < 7 or pos + 2 + segment_length > len(data):
                    return None
                height, width = struct.unpack(">HH", data[pos + 5 : pos + 9])
                break
            if pos + 4 > len(data):
                return None
            segment_length = int.from_bytes(data[pos + 2 : pos + 4], "big")
            if segment_length < 2 or pos + 2 + segment_length > len(data):
                return None
            pos += 2 + segment_length
        else:
            return None
    else:
        return None
    return ImageDimensions(width, height) if width > 0 and height > 0 else None


def is_valid_image(data: bytes, mime_type: str) -> bool:
    dimensions = image_dimensions(data)
    if dimensions is None:
        return False
    if mime_type == "image/png":
        return _is_valid_png(data)
    if mime_type == "image/jpeg":
        return data.startswith(b"\xff\xd8") and data.endswith(b"\xff\xd9")
    if mime_type == "image/gif":
        return len(data) >= 14 and data.startswith((b"GIF87a", b"GIF89a")) and data.endswith(b"\x3b")
    if mime_type == "image/webp":
        return (
            len(data) >= 30
            and data.startswith(b"RIFF")
            and data[8:12] == b"WEBP"
            and int.from_bytes(data[4:8], "little") + 8 == len(data)
        )
    return False


def _is_valid_png(data: bytes) -> bool:
    offset = 8
    saw_header = False
    saw_data = False
    while offset + 12 <= len(data):
        length = int.from_bytes(data[offset : offset + 4], "big")
        chunk_type = data[offset + 4 : offset + 8]
        chunk_end = offset + 12 + length
        if chunk_end > len(data):
            return False
        chunk_data = data[offset + 8 : offset + 8 + length]
        expected_crc = int.from_bytes(data[offset + 8 + length : chunk_end], "big")
        if zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF != expected_crc:
            return False
        if not saw_header:
            if chunk_type != b"IHDR" or length != 13:
                return False
            width, height, bit_depth, color_type, compression, filtering, interlace = struct.unpack(
                ">IIBBBBB", chunk_data
            )
            valid_depths = {0: {1, 2, 4, 8, 16}, 2: {8, 16}, 3: {1, 2, 4, 8}, 4: {8, 16}, 6: {8, 16}}
            if (
                width < 1
                or height < 1
                or bit_depth not in valid_depths.get(color_type, set())
                or compression != 0
                or filtering != 0
                or interlace not in {0, 1}
            ):
                return False
            saw_header = True
        elif chunk_type == b"IDAT":
            saw_data = True
        elif chunk_type == b"IEND":
            return length == 0 and saw_data and chunk_end == len(data)
        offset = chunk_end
    return False


def image_cell_size(
    dimensions: ImageDimensions, cell_size: CellSize | None = None, *, max_columns: int, max_rows: int
) -> ImageCellSize:
    cell_size = cell_size or CellSize()
    if dimensions.width < 1 or dimensions.height < 1 or cell_size.width < 1 or cell_size.height < 1:
        raise ValueError("Image and cell dimensions must be positive")
    max_columns = max(1, max_columns)
    max_rows = max(1, max_rows)
    width_scale = max_columns * cell_size.width / dimensions.width
    height_scale = max_rows * cell_size.height / dimensions.height
    scale = min(width_scale, height_scale)
    columns = min(max_columns, max(1, math.ceil(dimensions.width * scale / cell_size.width)))
    rows = min(max_rows, max(1, math.ceil(dimensions.height * scale / cell_size.height)))
    return ImageCellSize(columns, rows)


def parse_kitty_metadata(line: str) -> dict[str, str] | None:
    start = line.find("\x1b_G")
    if start < 0:
        return None
    end = line.find(";", start + 3)
    if end < 0:
        return None
    return dict(item.split("=", 1) for item in line[start + 3 : end].split(",") if "=" in item)


# Descriptive aliases kept convenient for callers.
encode_kitty_image = encode_kitty
encode_iterm2_image = encode_iterm2
delete_kitty_image = encode_kitty_delete
detect_capabilities = detect_terminal_capabilities
get_image_dimensions = image_dimensions
calculate_image_cell_size = image_cell_size
