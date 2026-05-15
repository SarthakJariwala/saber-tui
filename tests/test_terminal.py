import ctypes
import sys
from collections.abc import Callable
from typing import Any

import pytest

from saber_tui.keys import matches_key
from saber_tui.terminal import (
    _ENABLE_ECHO_INPUT,
    _ENABLE_LINE_INPUT,
    _ENABLE_PROCESSED_INPUT,
    _ENABLE_PROCESSED_OUTPUT,
    _ENABLE_VIRTUAL_TERMINAL_INPUT,
    _ENABLE_VIRTUAL_TERMINAL_PROCESSING,
    _STD_INPUT_HANDLE,
    _STD_OUTPUT_HANDLE,
    PosixProcessTerminal,
    ProcessTerminal,
    WindowsProcessTerminal,
    _select_process_terminal_base,
)
from tests.virtual_terminal import VirtualTerminal

_ENABLE_QUICK_EDIT_MODE = 0x0040
_ENABLE_EXTENDED_FLAGS = 0x0080


class _FakeWinApiFunction:
    def __init__(self, func: Callable[..., int]) -> None:
        self._func = func
        self.argtypes: list[Any] | None = None
        self.restype: Any | None = None

    def __call__(self, *args: Any) -> int:
        return self._func(*args)


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
    class RecordingProcessTerminal(PosixProcessTerminal):
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


@pytest.mark.skipif(sys.platform == "win32", reason="termios and SIGWINCH are POSIX-only")
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

    terminal = PosixProcessTerminal()
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
    terminal = PosixProcessTerminal()

    assert terminal._decode_input(b"\xc3") == ""
    assert terminal._decode_input(b"\xa9") == "é"


def test_process_terminal_configures_stdin_escape_timeout() -> None:
    terminal = ProcessTerminal(escape_timeout=0.25)

    try:
        terminal._setup_stdin_buffer()

        assert terminal._stdin_buffer is not None
        assert terminal._stdin_buffer._timeout_seconds == 0.25
    finally:
        terminal._destroy_stdin_buffer()


def test_process_terminal_read_stdin_splits_batched_sequences(monkeypatch) -> None:
    class FakeStdin:
        def fileno(self) -> int:
            return 12

    events: list[str] = []
    reads = [b"\x1b[A\r", b""]

    terminal = PosixProcessTerminal()
    terminal._running = True
    terminal._on_input = events.append

    monkeypatch.setattr("sys.stdin", FakeStdin())
    monkeypatch.setattr("select.select", lambda read, write, error, timeout: (read, write, error))
    monkeypatch.setattr("os.read", lambda fd, size: reads.pop(0))

    terminal._read_stdin()

    assert events == ["\x1b[A", "\r"]


def test_process_terminal_read_stdin_rewraps_bracketed_paste(monkeypatch) -> None:
    class FakeStdin:
        def fileno(self) -> int:
            return 12

    events: list[str] = []
    reads = [b"a\x1b[200~pasted\x1b[201~b", b""]

    terminal = PosixProcessTerminal()
    terminal._running = True
    terminal._on_input = events.append

    monkeypatch.setattr("sys.stdin", FakeStdin())
    monkeypatch.setattr("select.select", lambda read, write, error, timeout: (read, write, error))
    monkeypatch.setattr("os.read", lambda fd, size: reads.pop(0))

    terminal._read_stdin()

    assert events == ["a", "\x1b[200~pasted\x1b[201~", "b"]


def test_virtual_terminal_progress_records_expected_sequences() -> None:
    terminal = VirtualTerminal(columns=10, rows=3)

    terminal.set_progress(True)
    terminal.set_progress(False)

    assert terminal.writes == ("\x1b]9;4;3\x07", "\x1b]9;4;0;\x07")


class _FakeKernel32:
    def __init__(self, *, input_mode: int, output_mode: int) -> None:
        self.handles = {
            _STD_INPUT_HANDLE: 101,
            _STD_OUTPUT_HANDLE: 102,
        }
        self.modes = {
            101: input_mode,
            102: output_mode,
        }
        self.set_calls: list[tuple[int, int]] = []
        self.GetStdHandle = _FakeWinApiFunction(self._get_std_handle)
        self.GetConsoleMode = _FakeWinApiFunction(self._get_console_mode)
        self.SetConsoleMode = _FakeWinApiFunction(self._set_console_mode)

    def _get_std_handle(self, handle_id: int) -> int:
        return self.handles[handle_id]

    def _get_console_mode(self, handle: int, mode: Any) -> int:
        mode._obj.value = self.modes[handle]
        return 1

    def _set_console_mode(self, handle: int, mode: int) -> int:
        self.modes[handle] = mode
        self.set_calls.append((handle, mode))
        return 1


class _FakeMsvcrt:
    def __init__(self, chars: list[str] | None = None) -> None:
        self.chars = chars or []

    def kbhit(self) -> bool:
        return bool(self.chars)

    def getwch(self) -> str:
        return self.chars.pop(0)


def test_process_terminal_selects_windows_backend_for_win32() -> None:
    assert _select_process_terminal_base("win32") is WindowsProcessTerminal


def test_windows_terminal_start_stop_configures_and_restores_console_modes() -> None:
    input_mode = _ENABLE_PROCESSED_INPUT | _ENABLE_LINE_INPUT | _ENABLE_ECHO_INPUT
    output_mode = _ENABLE_PROCESSED_OUTPUT
    kernel32 = _FakeKernel32(input_mode=input_mode, output_mode=output_mode)
    terminal = WindowsProcessTerminal(_kernel32=kernel32, _msvcrt=_FakeMsvcrt())

    terminal.start(lambda data: None, lambda: None)
    terminal.stop()

    assert kernel32.set_calls[0] == (
        101,
        (input_mode & ~(_ENABLE_PROCESSED_INPUT | _ENABLE_LINE_INPUT | _ENABLE_ECHO_INPUT))
        | _ENABLE_EXTENDED_FLAGS
        | _ENABLE_VIRTUAL_TERMINAL_INPUT,
    )
    assert kernel32.set_calls[1] == (102, output_mode | _ENABLE_PROCESSED_OUTPUT | _ENABLE_VIRTUAL_TERMINAL_PROCESSING)
    assert kernel32.set_calls[-2:] == [(101, input_mode), (102, output_mode)]


def test_windows_terminal_start_clears_quick_edit_in_raw_mode() -> None:
    input_mode = _ENABLE_LINE_INPUT | _ENABLE_ECHO_INPUT | _ENABLE_QUICK_EDIT_MODE
    kernel32 = _FakeKernel32(input_mode=input_mode, output_mode=0)
    terminal = WindowsProcessTerminal(_kernel32=kernel32, _msvcrt=_FakeMsvcrt())

    terminal.start(lambda data: None, lambda: None)
    terminal.stop()

    assert kernel32.set_calls[0] == (
        101,
        (input_mode & ~(_ENABLE_LINE_INPUT | _ENABLE_ECHO_INPUT | _ENABLE_QUICK_EDIT_MODE))
        | _ENABLE_EXTENDED_FLAGS
        | _ENABLE_VIRTUAL_TERMINAL_INPUT,
    )
    assert kernel32.set_calls[-2] == (101, input_mode)


def test_windows_terminal_configures_winapi_handle_signatures() -> None:
    from ctypes import wintypes

    kernel32 = _FakeKernel32(input_mode=0, output_mode=0)
    terminal = WindowsProcessTerminal(_kernel32=kernel32, _msvcrt=_FakeMsvcrt())

    terminal._configure_console()

    assert kernel32.GetStdHandle.argtypes == [wintypes.DWORD]
    assert kernel32.GetStdHandle.restype is wintypes.HANDLE
    assert kernel32.GetConsoleMode.argtypes == [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    assert kernel32.GetConsoleMode.restype is wintypes.BOOL
    assert kernel32.SetConsoleMode.argtypes == [wintypes.HANDLE, wintypes.DWORD]
    assert kernel32.SetConsoleMode.restype is wintypes.BOOL


def test_windows_terminal_reads_text_and_maps_extended_keys() -> None:
    terminal = WindowsProcessTerminal(
        _kernel32=_FakeKernel32(input_mode=0, output_mode=0),
        _msvcrt=_FakeMsvcrt(["a", "\xe0", "H", "\r"]),
    )
    events: list[str] = []
    terminal._on_input = events.append
    terminal._setup_stdin_buffer()

    terminal._read_available_input()

    assert events == ["a", "\x1b[A", "\r"]


def test_windows_terminal_maps_ctrl_arrow_extended_keys() -> None:
    terminal = WindowsProcessTerminal(
        _kernel32=_FakeKernel32(input_mode=0, output_mode=0),
        _msvcrt=_FakeMsvcrt(["\xe0", "s", "\xe0", "t"]),
    )
    events: list[str] = []
    terminal._on_input = events.append
    terminal._setup_stdin_buffer()

    terminal._read_available_input()

    assert events == ["\x1b[1;5D", "\x1b[1;5C"]
    assert matches_key(events[0], "ctrl+left")
    assert matches_key(events[1], "ctrl+right")


def test_windows_terminal_maps_nul_prefixed_function_keys() -> None:
    terminal = WindowsProcessTerminal(
        _kernel32=_FakeKernel32(input_mode=0, output_mode=0),
        _msvcrt=_FakeMsvcrt(["\x00", "\x86"]),
    )
    events: list[str] = []
    terminal._on_input = events.append
    terminal._setup_stdin_buffer()

    terminal._read_available_input()

    assert events == ["\x1b[24~"]
    assert matches_key(events[0], "f12")


def test_windows_terminal_passes_lone_nul_as_ctrl_space() -> None:
    terminal = WindowsProcessTerminal(
        _kernel32=_FakeKernel32(input_mode=0, output_mode=0),
        _msvcrt=_FakeMsvcrt(["\x00"]),
    )
    events: list[str] = []
    terminal._on_input = events.append
    terminal._setup_stdin_buffer()

    terminal._read_available_input()

    assert events == ["\x00"]
    assert matches_key(events[0], "ctrl+space")


def test_windows_terminal_preserves_ctrl_space_before_queued_input() -> None:
    terminal = WindowsProcessTerminal(
        _kernel32=_FakeKernel32(input_mode=0, output_mode=0),
        _msvcrt=_FakeMsvcrt(["\x00", "H"]),
    )
    events: list[str] = []
    terminal._on_input = events.append
    terminal._setup_stdin_buffer()

    terminal._read_available_input()

    assert events == ["\x00", "H"]
    assert matches_key(events[0], "ctrl+space")


def test_windows_terminal_preserves_ambiguous_nul_before_mapped_printable_input() -> None:
    terminal = WindowsProcessTerminal(
        _kernel32=_FakeKernel32(input_mode=0, output_mode=0),
        _msvcrt=_FakeMsvcrt(["\x00", "A", "\x00", ";"]),
    )
    events: list[str] = []
    terminal._on_input = events.append
    terminal._setup_stdin_buffer()

    terminal._read_available_input()

    assert events == ["\x00", "A", "\x00", ";"]
    assert matches_key(events[0], "ctrl+space")
    assert matches_key(events[2], "ctrl+space")


def test_windows_terminal_passes_lone_e0_as_literal_input() -> None:
    terminal = WindowsProcessTerminal(
        _kernel32=_FakeKernel32(input_mode=0, output_mode=0),
        _msvcrt=_FakeMsvcrt(["\xe0"]),
    )
    events: list[str] = []
    terminal._on_input = events.append
    terminal._setup_stdin_buffer()

    terminal._read_available_input()

    assert events == ["\xe0"]


def test_windows_terminal_preserves_e0_literal_before_unmapped_input() -> None:
    terminal = WindowsProcessTerminal(
        _kernel32=_FakeKernel32(input_mode=0, output_mode=0),
        _msvcrt=_FakeMsvcrt(["\xe0", "b"]),
    )
    events: list[str] = []
    terminal._on_input = events.append
    terminal._setup_stdin_buffer()

    terminal._read_available_input()

    assert events == ["\xe0", "b"]


def test_windows_terminal_poll_resize_invokes_handler_when_size_changes(monkeypatch) -> None:
    terminal = WindowsProcessTerminal(
        _kernel32=_FakeKernel32(input_mode=0, output_mode=0),
        _msvcrt=_FakeMsvcrt(),
    )
    terminal._columns = 80
    terminal._rows = 24
    resized = False

    def on_resize() -> None:
        nonlocal resized
        resized = True

    terminal._on_resize = on_resize
    monkeypatch.setattr(terminal, "_get_terminal_size", lambda: (100, 30))

    terminal._poll_resize()

    assert resized
    assert terminal.columns == 100
    assert terminal.rows == 30
