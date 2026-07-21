import struct
import zlib

from saber_tui.components.image import Image, ImageOptions
from saber_tui.terminal_image import CellSize, TerminalCapabilities
from saber_tui.tui import TUI
from tests.virtual_terminal import VirtualTerminal


def png(width: int = 40, height: int = 20) -> bytes:
    def chunk(chunk_type: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", zlib.crc32(chunk_type + data))

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    pixels = b"".join(b"\x00" + b"\x00\x00\x00\xff" * width for _ in range(height))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b"")


def test_kitty_component_reserves_rows_and_keeps_stable_id() -> None:
    tui = TUI(
        VirtualTerminal(),
        capabilities=TerminalCapabilities("kitty"),
        cell_size=CellSize(10, 20),
    )
    image = Image(tui, png(400, 200), "image/png", options=ImageOptions(max_width_cells=20, image_id=42))

    first = image.render(80)
    second = image.render(80)

    assert first is second
    assert len(first) == 5
    assert "i=42,c=20,r=5" in first[0]
    assert first[1:] == ["", "", "", ""]
    assert image.get_image_id() == 42


def test_iterm2_component_places_command_after_reserved_rows() -> None:
    tui = TUI(VirtualTerminal(), capabilities=TerminalCapabilities("iterm2"), cell_size=CellSize(10, 20))
    image = Image(tui, png(400, 200), "image/png", options=ImageOptions(max_width_cells=20))

    lines = image.render(80)

    assert lines[:-1] == ["", "", "", ""]
    assert lines[-1].startswith("\x1b[4A\x1b]1337;File=")


def test_iterm2_component_clamps_height_to_terminal_viewport() -> None:
    terminal = VirtualTerminal(rows=3)
    tui = TUI(terminal, capabilities=TerminalCapabilities("iterm2"), cell_size=CellSize(10, 20))
    image = Image(
        tui,
        png(20, 400),
        "image/png",
        options=ImageOptions(max_width_cells=20, max_height_cells=100),
    )

    lines = image.render(80)

    assert len(lines) <= 3
    assert f"height={len(lines)}" in lines[-1]


def test_unsupported_or_invalid_image_uses_descriptive_width_safe_fallback() -> None:
    tui = TUI(VirtualTerminal(), capabilities=TerminalCapabilities())
    image = Image(tui, png(), "image/png", options=ImageOptions(filename="cat\n.png"))

    fallback = image.render(24)[0]

    assert len(fallback) <= 24
    assert "Image:" in fallback
    assert "cat.png" in fallback


def test_kitty_rejects_non_png_without_transcoding() -> None:
    tui = TUI(VirtualTerminal(), capabilities=TerminalCapabilities("kitty"))
    gif = b"GIF89a" + struct.pack("<HH", 10, 10)

    assert Image(tui, gif, "image/gif").render(80)[0].startswith("[Image:")


def test_component_cache_retains_only_latest_render() -> None:
    tui = TUI(VirtualTerminal(), capabilities=TerminalCapabilities("kitty"))
    image = Image(tui, png(), "image/png")

    first = image.render(40)
    second = image.render(60)

    assert first is not second
    assert image._cached_lines is second
