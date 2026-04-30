from saber_tui.stdin_buffer import StdinBuffer


def test_emits_plain_characters_individually() -> None:
    events: list[str] = []
    buffer = StdinBuffer(on_data=events.append)

    buffer.process("ab")

    assert events == ["a", "b"]


def test_buffers_partial_csi_sequence_until_complete() -> None:
    events: list[str] = []
    buffer = StdinBuffer(on_data=events.append)

    buffer.process("\x1b[")
    assert events == []
    buffer.process("A")

    assert events == ["\x1b[A"]


def test_emits_paste_content_separately() -> None:
    events: list[str] = []
    pastes: list[str] = []
    buffer = StdinBuffer(on_data=events.append, on_paste=pastes.append)

    buffer.process("a\x1b[200~hello\nworld\x1b[201~b")

    assert events == ["a", "b"]
    assert pastes == ["hello\nworld"]


def test_flush_emits_incomplete_sequence() -> None:
    events: list[str] = []
    buffer = StdinBuffer(on_data=events.append)

    buffer.process("\x1b[")
    assert buffer.flush() == ["\x1b["]
