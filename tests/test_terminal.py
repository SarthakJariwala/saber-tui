from saber_tui.terminal import ProcessTerminal
from tests.virtual_terminal import VirtualTerminal


def test_virtual_terminal_records_writes_and_viewport() -> None:
    terminal = VirtualTerminal(columns=10, rows=3)
    terminal.write("hello")

    assert terminal.get_viewport()[0] == "hello"


def test_virtual_terminal_resize_invokes_handler() -> None:
    terminal = VirtualTerminal(columns=10, rows=3)
    resized = False

    def on_resize() -> None:
        nonlocal resized
        resized = True

    terminal.start(lambda data: None, on_resize)
    terminal.resize(20, 4)

    assert resized
    assert terminal.columns == 20
    assert terminal.rows == 4


def test_virtual_terminal_start_and_stop_record_bracketed_paste() -> None:
    terminal = VirtualTerminal(columns=10, rows=3)

    terminal.start(lambda data: None, lambda: None)
    terminal.stop()

    assert terminal.writes == ("\x1b[?2004h", "\x1b[?2004l")


def test_virtual_terminal_clear_line_records_expected_sequence() -> None:
    terminal = VirtualTerminal(columns=10, rows=3)

    terminal.clear_line()

    assert terminal.writes == ("\x1b[K",)


def test_process_terminal_helpers_emit_expected_sequences() -> None:
    class RecordingProcessTerminal(ProcessTerminal):
        def __init__(self) -> None:
            super().__init__()
            self.writes: list[str] = []

        def write(self, data: str) -> None:
            self.writes.append(data)

    terminal = RecordingProcessTerminal()

    terminal.clear_line()
    terminal.set_progress(True)
    terminal.set_progress(False)

    assert terminal.writes == ["\x1b[K", "\x1b]9;4;3\x07", "\x1b]9;4;0;\x07"]


def test_process_terminal_stop_restores_termios_when_disable_write_fails(monkeypatch) -> None:
    class FakeStdin:
        def fileno(self) -> int:
            return 12

    restored_termios: list[tuple[int, int, list[int]]] = []
    restored_signals: list[tuple[int, object]] = []

    def fake_tcsetattr(fd: int, when: int, attrs: list[int]) -> None:
        restored_termios.append((fd, when, attrs))

    def fake_signal(signum: int, handler: object) -> None:
        restored_signals.append((signum, handler))

    def failing_write(data: str) -> None:
        _ = data
        raise RuntimeError("stdout failed")

    terminal = ProcessTerminal()
    old_handler = object()
    terminal._running = True
    terminal._old_termios = [1, 2, 3]
    terminal._old_sigwinch_handler = old_handler
    monkeypatch.setattr(terminal, "write", failing_write)

    monkeypatch.setattr("sys.stdin", FakeStdin())
    monkeypatch.setattr("termios.TCSADRAIN", 99)
    monkeypatch.setattr("termios.tcsetattr", fake_tcsetattr)
    monkeypatch.setattr("signal.SIGWINCH", 28)
    monkeypatch.setattr("signal.signal", fake_signal)

    terminal.stop()

    assert restored_termios == [(12, 99, [1, 2, 3])]
    assert restored_signals == [(28, old_handler)]
    assert not terminal._running
    assert terminal._old_termios is None
    assert terminal._old_sigwinch_handler is None


def test_process_terminal_decode_input_handles_split_utf8_bytes() -> None:
    terminal = ProcessTerminal()

    assert terminal._decode_input(b"\xc3") == ""
    assert terminal._decode_input(b"\xa9") == "é"


def test_virtual_terminal_progress_records_expected_sequences() -> None:
    terminal = VirtualTerminal(columns=10, rows=3)

    terminal.set_progress(True)
    terminal.set_progress(False)

    assert terminal.writes == ("\x1b]9;4;3\x07", "\x1b]9;4;0;\x07")
