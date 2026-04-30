from saber_tui.stdin_buffer import StdinBuffer


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
