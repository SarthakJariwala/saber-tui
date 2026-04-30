from saber_tui.utils import (
    extract_ansi_code,
    extract_segments,
    slice_by_column,
    truncate_to_width,
    visible_width,
    wrap_text_with_ansi,
)


def test_visible_width_handles_ascii_cjk_emoji_and_ansi() -> None:
    assert visible_width("abc") == 3
    assert visible_width("コン") == 4
    assert visible_width("a\x1b[31mb\x1b[0m") == 2
    assert visible_width("👩‍💻") == 2


def test_extract_ansi_code_supports_csi_osc_and_apc() -> None:
    assert extract_ansi_code("\x1b[31mred", 0) == ("\x1b[31m", 5)
    assert extract_ansi_code("\x1b]8;;https://example.com\x07x", 0) == (
        "\x1b]8;;https://example.com\x07",
        25,
    )
    assert extract_ansi_code("\x1b_pi:c\x07x", 0) == ("\x1b_pi:c\x07", 7)


def test_truncate_to_width_preserves_width_and_adds_reset() -> None:
    result = truncate_to_width("\x1b[31mabcdef", 4)

    assert visible_width(result) == 4
    assert result.endswith("\x1b[0m...\x1b[0m")


def test_wrap_text_with_ansi_preserves_active_style() -> None:
    lines = wrap_text_with_ansi("\x1b[31mhello world", 6)

    assert len(lines) == 2
    assert lines[1].startswith("\x1b[31m")
    assert all(visible_width(line) <= 6 for line in lines)


def test_slice_by_column_handles_wide_boundaries() -> None:
    assert slice_by_column("aコンb", 1, 2, strict=True) == "コ"
    assert slice_by_column("aコンb", 1, 1, strict=True) == ""


def test_extract_segments_preserves_before_and_after_text() -> None:
    segments = extract_segments("hello world", before_end=5, after_start=8, after_len=3)

    assert segments.before == "hello"
    assert segments.before_width == 5
    assert segments.after == "rld"
    assert segments.after_width == 3
