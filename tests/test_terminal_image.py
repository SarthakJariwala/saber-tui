import base64
import struct
import zlib

import pytest

from saber_tui.terminal_image import (
    CellSize,
    ImageDimensions,
    detect_terminal_capabilities,
    encode_iterm2,
    encode_kitty,
    encode_kitty_delete,
    image_cell_size,
    image_dimensions,
    is_image_line,
    parse_kitty_metadata,
)


def png(width: int = 40, height: int = 20, payload: bytes = b"") -> bytes:
    def chunk(chunk_type: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", zlib.crc32(chunk_type + data))

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    pixels = b"".join(b"\x00" + bytes([payload[0] if payload else 0, 0, 0, 255]) * width for _ in range(height))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b"")


@pytest.mark.parametrize(
    ("env", "protocol"),
    [
        ({"KITTY_WINDOW_ID": "1"}, "kitty"),
        ({"TERM_PROGRAM": "ghostty"}, "kitty"),
        ({"WEZTERM_PANE": "1"}, "kitty"),
        ({"WARP_SESSION_ID": "1"}, "kitty"),
        ({"ITERM_SESSION_ID": "1"}, "iterm2"),
        ({"WT_SESSION": "1"}, None),
        ({"TERM_PROGRAM": "vscode"}, None),
        ({}, None),
    ],
)
def test_detect_terminal_capabilities(env: dict[str, str], protocol: str | None) -> None:
    assert detect_terminal_capabilities(env).image_protocol == protocol


def test_multiplexer_disables_outer_terminal_images() -> None:
    assert detect_terminal_capabilities({"TMUX": "1", "KITTY_WINDOW_ID": "1"}).image_protocol is None
    assert detect_terminal_capabilities({"TERM": "screen-256color", "ITERM_SESSION_ID": "1"}).image_protocol is None


def test_image_line_detection_handles_prefixes_and_large_payloads() -> None:
    assert is_image_line("prefix\x1b_Ga=T;data\x1b\\")
    assert is_image_line("\x1b[2A\x1b]1337;File=inline=1:data\x07")
    assert is_image_line("\x1b_Ga=T;" + "a" * 300_000 + "\x1b\\")
    assert not is_image_line("plain _G text")


def test_kitty_encoding_chunks_payload_and_suppresses_cursor_movement() -> None:
    data = b"x" * 4_000
    encoded = encode_kitty(data, image_id=7, columns=10, rows=3)

    assert "a=T,f=100,i=7,c=10,r=3,q=2,C=1,m=1" in encoded
    assert encoded.count("\x1b_G") == 2
    assert ";m=0" not in encoded
    assert "\x1b_Gm=0;" in encoded
    assert encoded.endswith("\x1b\\")
    assert base64.b64encode(data).decode()[:100] in encoded
    assert parse_kitty_metadata(encoded)["i"] == "7"


def test_kitty_delete_frees_image_data_and_placement() -> None:
    assert encode_kitty_delete(7) == "\x1b_Ga=d,d=I,i=7,q=2;\x1b\\"
    with pytest.raises(ValueError):
        encode_kitty_delete(0)


def test_iterm2_encoding_contains_inline_dimensions_and_payload() -> None:
    encoded = encode_iterm2(b"abc", "image/png", columns=4, rows=2, filename="cat.png")
    assert encoded.startswith("\x1b]1337;File=inline=1;name=Y2F0LnBuZw==;width=4;height=2;")
    assert encoded.endswith("YWJj\x07")


def test_image_dimensions_parses_supported_headers() -> None:
    gif = b"GIF89a" + struct.pack("<HH", 12, 34)
    vp8x = b"RIFF" + b"\x00" * 4 + b"WEBPVP8X" + b"\x00" * 8 + (19).to_bytes(3, "little") + (9).to_bytes(3, "little")

    assert image_dimensions(png(40, 20)) == ImageDimensions(40, 20)
    assert image_dimensions(gif) == ImageDimensions(12, 34)
    assert image_dimensions(vp8x) == ImageDimensions(20, 10)
    assert image_dimensions(b"not an image") is None


def test_malformed_png_header_is_not_a_valid_component_payload() -> None:
    malformed = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8 + struct.pack(">II", 40, 20)

    assert image_dimensions(malformed) is None


def test_cell_sizing_preserves_aspect_ratio_with_physical_cells() -> None:
    size = image_cell_size(ImageDimensions(400, 200), CellSize(10, 20), max_columns=20, max_rows=20)
    assert size.columns == 20
    assert size.rows == 5
