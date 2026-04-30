from saber_tui.utils import (
    apply_background_to_line,
    extract_ansi_code,
    extract_segments,
    normalize_terminal_output,
    slice_by_column,
    slice_with_width,
    strip_ansi,
    truncate_to_width,
    visible_width,
    wrap_text_with_ansi,
)


def test_visible_width_handles_ascii_cjk_emoji_and_ansi() -> None:
    assert visible_width("abc") == 3
    assert visible_width("コン") == 4
    assert visible_width("a\x1b[31mb\x1b[0m") == 2
    assert visible_width("👩‍💻") == 2
    assert visible_width("a\tb") == 5
    assert visible_width("a\u0301\u0327") == 1


def test_extract_ansi_code_supports_csi_osc_apc_and_dcs() -> None:
    assert extract_ansi_code("\x1b[31mred", 0) == ("\x1b[31m", 5)
    assert extract_ansi_code("\x1b]8;;https://example.com\x07x", 0) == (
        "\x1b]8;;https://example.com\x07",
        25,
    )
    assert extract_ansi_code("\x1b_pi:c\x07x", 0) == ("\x1b_pi:c\x07", 7)
    assert extract_ansi_code("\x1bP>|abc\x1b\\x", 0) == ("\x1bP>|abc\x1b\\", 9)


def test_strip_ansi_removes_supported_sequences() -> None:
    assert (
        strip_ansi("a\x1b[31mb\x1b]8;;https://example.com\x07c\x1b_pi:c\x07d\x1bP>|abc\x1b\\e")
        == "abcde"
    )


def test_truncate_to_width_preserves_width_and_adds_reset() -> None:
    result = truncate_to_width("\x1b[31mabcdef", 4)

    assert visible_width(result) == 4
    assert result.endswith("\x1b[0m...\x1b[0m")


def test_wrap_text_with_ansi_preserves_active_style() -> None:
    lines = wrap_text_with_ansi("\x1b[31mhello world", 6)

    assert len(lines) == 2
    assert lines[1].startswith("\x1b[31m")
    assert all(visible_width(line) <= 6 for line in lines)


def test_wrap_text_with_ansi_does_not_emit_overwide_grapheme() -> None:
    lines = wrap_text_with_ansi("👩‍💻", 1)

    assert lines == [""]
    assert all(visible_width(line) <= 1 for line in lines)


def test_slice_by_column_handles_wide_boundaries() -> None:
    assert slice_by_column("aコンb", 1, 2, strict=True) == "コ"
    assert slice_by_column("aコンb", 1, 1, strict=True) == ""


def test_slice_with_width_returns_text_and_width() -> None:
    result = slice_with_width("aコンb", 1, 2, strict=True)

    assert result.text == "コ"
    assert result.width == 2


def test_extract_segments_preserves_before_and_after_text() -> None:
    segments = extract_segments("hello world", before_end=5, after_start=8, after_len=3)

    assert segments.before == "hello"
    assert segments.before_width == 5
    assert segments.after == "rld"
    assert segments.after_width == 3


def test_extract_segments_respects_wide_boundaries() -> None:
    segments = extract_segments("aコンb", before_end=2, after_start=3, after_len=2)

    assert segments.before == "a"
    assert segments.before_width == 1
    assert segments.after == "ン"
    assert segments.after_width == 2

    segments = extract_segments("aコンb", before_end=1, after_start=1, after_len=1)

    assert segments.before == "a"
    assert segments.before_width == 1
    assert segments.after == ""
    assert segments.after_width == 0


def test_extract_segments_strict_after_flag_controls_after_boundary() -> None:
    default_segments = extract_segments("aコンb", before_end=1, after_start=1, after_len=1)
    loose_segments = extract_segments("aコンb", before_end=1, after_start=1, after_len=1, strict_after=False)
    strict_segments = extract_segments("aコンb", before_end=1, after_start=1, after_len=1, strict_after=True)

    assert default_segments.after == ""
    assert default_segments.after_width == 0
    assert loose_segments.after == "コ"
    assert loose_segments.after_width == 2
    assert strict_segments.after == ""
    assert strict_segments.after_width == 0


def test_apply_background_to_line_pads_then_calls_bg_function() -> None:
    assert apply_background_to_line("ab", 5, lambda text: f"[{text}]") == "[ab   ]"


def test_normalize_terminal_output_decomposes_thai_and_lao_am() -> None:
    assert normalize_terminal_output("\u0e33\u0eb3") == "\u0e4d\u0e32\u0ecd\u0eb2"
