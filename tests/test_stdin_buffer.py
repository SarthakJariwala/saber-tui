import threading

from saber_tui.components import SettingItem, SettingsList
from saber_tui.stdin_buffer import BRACKETED_PASTE_END, BRACKETED_PASTE_START, StdinBuffer


def test_emits_plain_characters_individually() -> None:
    events: list[str] = []
    buffer = StdinBuffer(on_data=events.append)

    buffer.process("ab")

    assert events == ["a", "b"]


def test_buffers_split_utf8_bytes_until_complete_character() -> None:
    events: list[str] = []
    buffer = StdinBuffer(on_data=events.append)
    data = "é".encode()

    buffer.process(data[:1])
    assert events == []
    buffer.process(data[1:])

    assert events == ["é"]


def test_incomplete_utf8_bytes_do_not_raise_or_emit() -> None:
    events: list[str] = []
    buffer = StdinBuffer(on_data=events.append)

    buffer.process(bytes([0xE2, 0x82]))

    assert events == []


def test_flush_clears_pending_utf8_decoder_state() -> None:
    events: list[str] = []
    buffer = StdinBuffer(on_data=events.append)

    buffer.process(bytes([0xE2, 0x82]))
    assert buffer.flush() == []
    buffer.process(bytes([0xAC]))

    assert "€" not in events


def test_buffers_partial_csi_sequence_until_complete() -> None:
    events: list[str] = []
    buffer = StdinBuffer(on_data=events.append)

    buffer.process("\x1b[")
    assert events == []
    buffer.process("A")

    assert events == ["\x1b[A"]


def test_timeout_does_not_flush_partial_csi_prefix() -> None:
    events: list[str] = []
    buffer = StdinBuffer(on_data=events.append, timeout=0.01)

    try:
        buffer.process("\x1b[")
        threading.Event().wait(0.05)

        assert events == []
        assert buffer.get_buffer() == "\x1b["

        buffer.process("A")
        assert events == ["\x1b[A"]
    finally:
        buffer.destroy()


def test_default_timeout_preserves_slow_split_alt_sequence() -> None:
    events: list[str] = []
    buffer = StdinBuffer(on_data=events.append)

    try:
        buffer.process("\x1b")
        threading.Event().wait(0.05)
        assert events == []

        buffer.process("b")
        assert events == ["\x1bb"]
    finally:
        buffer.destroy()


def test_escape_timeout_preserves_pending_utf8_decoder_state() -> None:
    events: list[str] = []
    buffer = StdinBuffer(on_data=events.append, timeout=0.01)
    data = "é".encode()

    try:
        buffer.process(b"\x1b")
        buffer.process(data[:1])
        threading.Event().wait(0.05)

        assert events == ["\x1b"]

        buffer.process(data[1:])
        assert events == ["\x1b", "é"]
    finally:
        buffer.destroy()


def test_flushes_bare_escape_after_timeout_to_focused_component() -> None:
    cancelled = threading.Event()
    settings = SettingsList(
        [SettingItem(id="theme", label="Theme", current_value="dark")],
        on_cancel=cancelled.set,
    )
    buffer = StdinBuffer(on_data=settings.handle_input, timeout=0.01)

    try:
        buffer.process("\x1b")

        assert cancelled.wait(0.2)
        assert buffer.get_buffer() == ""
    finally:
        buffer.destroy()


def test_rapid_double_escape_reaches_focused_component_as_two_cancels() -> None:
    cancelled: list[bool] = []
    settings = SettingsList(
        [SettingItem(id="theme", label="Theme", current_value="dark")],
        on_cancel=lambda: cancelled.append(True),
    )
    buffer = StdinBuffer(on_data=settings.handle_input, timeout=0.01)

    try:
        buffer.process("\x1b")
        buffer.process("\x1b")
        threading.Event().wait(0.05)

        assert cancelled == [True, True]
        assert buffer.get_buffer() == ""
    finally:
        buffer.destroy()


def test_batched_double_escape_reaches_focused_component_as_two_cancels() -> None:
    cancelled: list[bool] = []
    settings = SettingsList(
        [SettingItem(id="theme", label="Theme", current_value="dark")],
        on_cancel=lambda: cancelled.append(True),
    )
    buffer = StdinBuffer(on_data=settings.handle_input, timeout=0.01)

    try:
        buffer.process("\x1b\x1b")
        threading.Event().wait(0.05)

        assert cancelled == [True, True]
        assert buffer.get_buffer() == ""
    finally:
        buffer.destroy()


def test_batched_escape_before_escape_sequence_splits_events() -> None:
    events: list[str] = []
    buffer = StdinBuffer(on_data=events.append, timeout=0.01)

    buffer.process("\x1b\x1b[A")

    assert events == ["\x1b", "\x1b[A"]
    assert buffer.get_buffer() == ""


def test_emits_complete_non_mouse_csi_sequence_starting_with_angle_bracket() -> None:
    events: list[str] = []
    buffer = StdinBuffer(on_data=events.append)

    buffer.process("\x1b[<0c")

    assert events == ["\x1b[<0c"]
    assert buffer.get_buffer() == ""


def test_emits_paste_content_separately() -> None:
    events: list[str] = []
    pastes: list[str] = []
    buffer = StdinBuffer(on_data=events.append, on_paste=pastes.append)

    buffer.process("a\x1b[200~hello\nworld\x1b[201~b")

    assert events == ["a", "b"]
    assert pastes == ["hello\nworld"]


def test_timeout_does_not_flush_bare_escape_inside_bracketed_paste() -> None:
    events: list[str] = []
    pastes: list[str] = []
    buffer = StdinBuffer(on_data=events.append, on_paste=pastes.append, timeout=0.01)

    try:
        buffer.process(f"{BRACKETED_PASTE_START}abc\x1b")
        threading.Event().wait(0.05)

        assert events == []
        assert pastes == []

        buffer.process(f"Z{BRACKETED_PASTE_END}x")
        assert events == ["x"]
        assert pastes == ["abc\x1bZ"]
    finally:
        buffer.destroy()


def test_paste_marker_inside_osc_payload_is_data_not_paste() -> None:
    events: list[str] = []
    pastes: list[str] = []
    buffer = StdinBuffer(on_data=events.append, on_paste=pastes.append)

    buffer.process("\x1b]0;title \x1b[200~ marker\x07x")

    assert events == ["\x1b]0;title \x1b[200~ marker\x07", "x"]
    assert pastes == []


def test_flush_emits_incomplete_sequence() -> None:
    events: list[str] = []
    buffer = StdinBuffer(on_data=events.append)

    buffer.process("\x1b[")
    assert buffer.flush() == ["\x1b["]


def test_flush_emits_incomplete_paste_content_and_clears_state() -> None:
    events: list[str] = []
    pastes: list[str] = []
    buffer = StdinBuffer(on_data=events.append, on_paste=pastes.append)

    buffer.process("\x1b[200~abc")

    assert events == []
    assert pastes == []
    assert buffer.flush() == ["abc"]
    assert buffer.get_buffer() == ""
    buffer.process("x")
    assert events == ["x"]
    assert pastes == []
