import struct
import zlib

import pytest

from saber_tui.components.image import Image, ImageOptions
from saber_tui.terminal_image import CellSize, TerminalCapabilities, encode_kitty
from saber_tui.tui import SEGMENT_RESET, TUI
from tests.virtual_terminal import VirtualTerminal


def png(width: int = 40, height: int = 20, suffix: bytes = b"") -> bytes:
    def chunk(chunk_type: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", zlib.crc32(chunk_type + data))

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    pixel = bytes([suffix[0] if suffix else 0, 0, 0, 255])
    pixels = b"".join(b"\x00" + pixel * width for _ in range(height))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b"")


class StaticComponent:
    def __init__(self, lines: list[str]) -> None:
        self.lines = lines
        self.invalidations = 0

    def render(self, width: int) -> list[str]:
        return self.lines

    def invalidate(self) -> None:
        self.invalidations += 1


class WriteThenFailTerminal(VirtualTerminal):
    def __init__(self) -> None:
        super().__init__(columns=40, rows=12)
        self.fail_image_write = True

    def write(self, data: str) -> None:
        super().write(data)
        if self.fail_image_write and "\x1b_Ga=T" in data:
            self.fail_image_write = False
            raise OSError("flush failed")


def kitty_tui() -> tuple[TUI, VirtualTerminal]:
    terminal = VirtualTerminal(columns=40, rows=12)
    tui = TUI(
        terminal,
        capabilities=TerminalCapabilities("kitty"),
        cell_size=CellSize(10, 20),
    )
    return tui, terminal


def test_start_queries_cell_size_and_image_line_bypasses_segment_reset() -> None:
    tui, terminal = kitty_tui()
    command = encode_kitty(png(), image_id=7, columns=4, rows=1)
    tui.add_child(StaticComponent([command]))

    tui.start()

    assert "\x1b[16t" in terminal.writes
    render = next(write for write in terminal.writes if command in write)
    assert command + SEGMENT_RESET not in render


def test_unchanged_image_is_not_retransmitted() -> None:
    tui, terminal = kitty_tui()
    image = Image(tui, png(), "image/png", options=ImageOptions(image_id=7))
    tui.add_child(image)
    tui.start()
    terminal.clear_writes()

    tui.request_render()
    tui.flush_render()

    assert not any("\x1b_Ga=T" in write for write in terminal.writes)


def test_changed_image_deletes_before_clear_and_replacement() -> None:
    tui, terminal = kitty_tui()
    first = Image(tui, png(suffix=b"first"), "image/png", options=ImageOptions(image_id=7))
    tui.add_child(first)
    tui.start()
    terminal.clear_writes()

    tui.clear()
    tui.add_child(Image(tui, png(suffix=b"second"), "image/png", options=ImageOptions(image_id=8)))
    tui.request_render()
    tui.flush_render()

    output = "".join(terminal.writes)
    assert output.index("a=d,d=I,i=7") < output.index("\x1b[2J") < output.index("a=T,f=100,i=8")


def test_forced_redraw_and_stop_cleanup_owned_ids() -> None:
    tui, terminal = kitty_tui()
    tui.add_child(Image(tui, png(), "image/png", options=ImageOptions(image_id=7)))
    tui.start()
    terminal.clear_writes()

    tui.request_render(force=True)
    tui.flush_render()
    assert "a=d,d=I,i=7" in "".join(terminal.writes)

    terminal.clear_writes()
    tui.stop()
    assert "a=d,d=I,i=7" in "".join(terminal.writes)


def test_cell_size_reply_is_per_tui_and_invalidates_components() -> None:
    first_tui, first_terminal = kitty_tui()
    second_tui, _ = kitty_tui()
    component = StaticComponent(["plain"])
    first_tui.add_child(component)
    first_tui.start()

    first_terminal.send_input("\x1b[6;24;12t")
    first_tui.flush_render()

    assert first_tui.cell_size == CellSize(12, 24)
    assert second_tui.cell_size == CellSize(10, 20)
    assert component.invalidations == 1


def test_overlay_cannot_emit_an_image() -> None:
    tui, _ = kitty_tui()
    tui.add_child(StaticComponent(["base"]))
    tui.show_overlay(StaticComponent([encode_kitty(png(), image_id=7, columns=4, rows=1)]))

    with pytest.raises(ValueError, match="Overlay components cannot render terminal images"):
        tui.start()


def test_write_failure_retains_new_id_for_stop_cleanup() -> None:
    terminal = WriteThenFailTerminal()
    tui = TUI(terminal, capabilities=TerminalCapabilities("kitty"))
    tui.add_child(Image(tui, png(), "image/png", options=ImageOptions(image_id=7)))

    with pytest.raises(OSError, match="flush failed"):
        tui.start()

    assert tui._kitty_image_ids == {7}
    terminal.clear_writes()
    tui.stop()
    assert "a=d,d=I,i=7" in "".join(terminal.writes)
