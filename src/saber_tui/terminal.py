import codecs
import re
import sys
import threading
import time
from collections.abc import Callable
from contextlib import suppress
from types import FrameType
from typing import Any, Protocol

from saber_tui.keys import set_kitty_protocol_active
from saber_tui.stdin_buffer import BRACKETED_PASTE_END, BRACKETED_PASTE_START, DEFAULT_ESCAPE_TIMEOUT, StdinBuffer

InputHandler = Callable[[str], None]
ResizeHandler = Callable[[], None]

_KITTY_PROTOCOL_RESPONSE_RE = re.compile(r"^\x1b\[\?(\d+)u$")
_STD_INPUT_HANDLE = -10
_STD_OUTPUT_HANDLE = -11
_ENABLE_PROCESSED_INPUT = 0x0001
_ENABLE_LINE_INPUT = 0x0002
_ENABLE_ECHO_INPUT = 0x0004
_ENABLE_QUICK_EDIT_MODE = 0x0040
_ENABLE_EXTENDED_FLAGS = 0x0080
_ENABLE_PROCESSED_OUTPUT = 0x0001
_ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
_ENABLE_VIRTUAL_TERMINAL_INPUT = 0x0200
_WINDOWS_POLL_INTERVAL_SECONDS = 0.05
_WINDOWS_EXTENDED_KEY_SEQUENCES = {
    "\x00": {
        ";": "\x1bOP",
        "<": "\x1bOQ",
        "=": "\x1bOR",
        ">": "\x1bOS",
        "?": "\x1b[15~",
        "@": "\x1b[17~",
        "A": "\x1b[18~",
        "B": "\x1b[19~",
        "C": "\x1b[20~",
        "D": "\x1b[21~",
        "\x85": "\x1b[23~",
        "\x86": "\x1b[24~",
    },
    "\xe0": {
        "H": "\x1b[A",
        "P": "\x1b[B",
        "K": "\x1b[D",
        "M": "\x1b[C",
        "G": "\x1b[H",
        "O": "\x1b[F",
        "I": "\x1b[5~",
        "Q": "\x1b[6~",
        "R": "\x1b[2~",
        "S": "\x1b[3~",
        "s": "\x1b[1;5D",
        "t": "\x1b[1;5C",
        "\x85": "\x1b[23~",
        "\x86": "\x1b[24~",
    },
}


class Terminal(Protocol):
    def start(self, on_input: InputHandler, on_resize: ResizeHandler) -> None: ...

    def stop(self) -> None: ...

    def drain_input(self, max_ms: int = 1000, idle_ms: int = 50) -> None: ...

    def write(self, data: str) -> None: ...

    @property
    def columns(self) -> int: ...

    @property
    def rows(self) -> int: ...

    @property
    def kitty_protocol_active(self) -> bool: ...

    def move_by(self, lines: int) -> None: ...

    def hide_cursor(self) -> None: ...

    def show_cursor(self) -> None: ...

    def clear_line(self) -> None: ...

    def clear_from_cursor(self) -> None: ...

    def clear_screen(self) -> None: ...

    def set_title(self, title: str) -> None: ...

    def set_progress(self, active: bool) -> None: ...


class _BaseProcessTerminal:
    def __init__(self, *, escape_timeout: float | None = DEFAULT_ESCAPE_TIMEOUT) -> None:
        self._columns = 80
        self._rows = 24
        self._on_input: InputHandler | None = None
        self._on_resize: ResizeHandler | None = None
        self._running = False
        self._reader_thread: threading.Thread | None = None
        self._input_decoder = codecs.getincrementaldecoder("utf-8")()
        self._stdin_buffer: StdinBuffer | None = None
        self._kitty_protocol_active = False
        self._escape_timeout = escape_timeout

    def start(self, on_input: InputHandler, on_resize: ResizeHandler) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError

    def drain_input(self, max_ms: int = 1000, idle_ms: int = 50) -> None:
        _ = max_ms, idle_ms

    def write(self, data: str) -> None:
        import sys

        sys.stdout.write(data)
        sys.stdout.flush()

    @property
    def columns(self) -> int:
        return self._columns

    @property
    def rows(self) -> int:
        return self._rows

    @property
    def kitty_protocol_active(self) -> bool:
        return self._kitty_protocol_active

    def move_by(self, lines: int) -> None:
        if lines > 0:
            self.write(f"\x1b[{lines}B")
        elif lines < 0:
            self.write(f"\x1b[{-lines}A")

    def hide_cursor(self) -> None:
        self.write("\x1b[?25l")

    def show_cursor(self) -> None:
        self.write("\x1b[?25h")

    def clear_line(self) -> None:
        self.write("\x1b[K")

    def clear_from_cursor(self) -> None:
        self.write("\x1b[0J")

    def clear_screen(self) -> None:
        self.write("\x1b[2J\x1b[H")

    def set_title(self, title: str) -> None:
        self.write(f"\x1b]0;{title}\x07")

    def set_progress(self, active: bool) -> None:
        if active:
            self.write("\x1b]9;4;3\x07")
        else:
            self.write("\x1b]9;4;0;\x07")

    def _setup_stdin_buffer(self) -> None:
        def on_data(sequence: str) -> None:
            if not self._kitty_protocol_active and _KITTY_PROTOCOL_RESPONSE_RE.fullmatch(sequence):
                self._kitty_protocol_active = True
                set_kitty_protocol_active(True)
                self.write("\x1b[>7u")
                return
            if self._on_input is not None:
                self._on_input(sequence)

        def on_paste(content: str) -> None:
            if self._on_input is not None:
                self._on_input(f"{BRACKETED_PASTE_START}{content}{BRACKETED_PASTE_END}")

        self._stdin_buffer = StdinBuffer(on_data=on_data, on_paste=on_paste, timeout=self._escape_timeout)

    def _destroy_stdin_buffer(self) -> None:
        if self._stdin_buffer is not None:
            self._stdin_buffer.destroy()
            self._stdin_buffer = None

    def _decode_input(self, data: bytes) -> str:
        try:
            return self._input_decoder.decode(data, final=False)
        except UnicodeDecodeError:
            self._input_decoder.reset()
            if len(data) == 1 and data[0] > 127:
                return f"\x1b{chr(data[0] - 128)}"
            raise

    def _disable_bracketed_paste_best_effort(self) -> None:
        with suppress(Exception):
            self.write("\x1b[?2004l")

    def _join_reader_thread(self) -> None:
        reader_thread = self._reader_thread
        if reader_thread is not None and reader_thread is not threading.current_thread():
            reader_thread.join(timeout=0.2)
        self._reader_thread = None

    def _clear_runtime_state(self) -> None:
        self._on_input = None
        self._on_resize = None
        self._reader_thread = None
        self._input_decoder.reset()
        self._destroy_stdin_buffer()
        if self._kitty_protocol_active:
            self._kitty_protocol_active = False
            set_kitty_protocol_active(False)

    def _get_terminal_size(self) -> tuple[int, int]:
        import shutil

        size = shutil.get_terminal_size(fallback=(80, 24))
        return size.columns, size.lines

    def _update_size(self) -> None:
        self._columns, self._rows = self._get_terminal_size()


class PosixProcessTerminal(_BaseProcessTerminal):
    def __init__(self, *, escape_timeout: float | None = DEFAULT_ESCAPE_TIMEOUT) -> None:
        super().__init__(escape_timeout=escape_timeout)
        self._old_termios: Any | None = None
        self._old_sigwinch_handler: Any | None = None

    def start(self, on_input: InputHandler, on_resize: ResizeHandler) -> None:
        import signal
        import termios
        import tty

        self._on_input = on_input
        self._on_resize = on_resize
        stdin = sys.stdin
        stdin_fd = stdin.fileno()
        self._old_termios = termios.tcgetattr(stdin_fd)
        try:
            tty.setraw(stdin_fd)
            self._update_size()
            self.write("\x1b[?2004h")
            self._old_sigwinch_handler = signal.getsignal(signal.SIGWINCH)
            signal.signal(signal.SIGWINCH, self._handle_sigwinch)
            self._running = True
            self._input_decoder.reset()
            self._setup_stdin_buffer()
            self._reader_thread = threading.Thread(target=self._read_stdin, daemon=True)
            self._reader_thread.start()
        except Exception:
            self._running = False
            self._disable_bracketed_paste_best_effort()
            self._restore_termios_best_effort()
            self._restore_signal_best_effort()
            self._clear_runtime_state()
            raise

    def stop(self) -> None:
        if not self._running and self._old_termios is None and self._old_sigwinch_handler is None:
            return
        self._running = False
        self._disable_bracketed_paste_best_effort()
        self._restore_termios_best_effort()
        self._restore_signal_best_effort()
        self._join_reader_thread()
        self._clear_runtime_state()

    def _read_stdin(self) -> None:
        import os
        import select

        if self._stdin_buffer is None:
            self._setup_stdin_buffer()
        stdin_fd = sys.stdin.fileno()
        while self._running:
            ready, _, _ = select.select([stdin_fd], [], [], 0.05)
            if not ready:
                continue
            data = os.read(stdin_fd, 4096)
            if not data:
                break
            if self._stdin_buffer is not None:
                self._stdin_buffer.process(data)

    def _restore_termios_best_effort(self) -> None:
        if self._old_termios is None:
            return

        import termios

        try:
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self._old_termios)
        except Exception:
            pass
        finally:
            self._old_termios = None

    def _restore_signal_best_effort(self) -> None:
        if self._old_sigwinch_handler is None:
            return

        import signal

        try:
            signal.signal(signal.SIGWINCH, self._old_sigwinch_handler)
        except Exception:
            pass
        finally:
            self._old_sigwinch_handler = None

    def _handle_sigwinch(self, signum: int, frame: FrameType | None) -> None:
        _ = signum, frame
        self._update_size()
        if self._on_resize is not None:
            self._on_resize()


class WindowsProcessTerminal(_BaseProcessTerminal):
    def __init__(
        self,
        *,
        escape_timeout: float | None = DEFAULT_ESCAPE_TIMEOUT,
        _kernel32: Any | None = None,
        _msvcrt: Any | None = None,
    ) -> None:
        super().__init__(escape_timeout=escape_timeout)
        self._kernel32 = _kernel32
        self._msvcrt = _msvcrt
        self._stdin_handle: int | None = None
        self._stdout_handle: int | None = None
        self._old_stdin_mode: int | None = None
        self._old_stdout_mode: int | None = None
        self._pending_windows_input: list[str] = []

    def start(self, on_input: InputHandler, on_resize: ResizeHandler) -> None:
        self._on_input = on_input
        self._on_resize = on_resize
        try:
            self._configure_console()
            self._update_size()
            self.write("\x1b[?2004h")
            self._running = True
            self._input_decoder.reset()
            self._setup_stdin_buffer()
            self._reader_thread = threading.Thread(target=self._read_stdin, daemon=True)
            self._reader_thread.start()
        except Exception:
            self._running = False
            self._disable_bracketed_paste_best_effort()
            self._restore_console_best_effort()
            self._clear_runtime_state()
            raise

    def stop(self) -> None:
        if not self._running and self._old_stdin_mode is None and self._old_stdout_mode is None:
            return
        self._running = False
        self._disable_bracketed_paste_best_effort()
        self._restore_console_best_effort()
        self._join_reader_thread()
        self._clear_runtime_state()

    def _configure_console(self) -> None:
        kernel32 = self._get_kernel32()
        self._configure_kernel32_signatures(kernel32)
        self._stdin_handle = kernel32.GetStdHandle(_STD_INPUT_HANDLE)
        self._stdout_handle = kernel32.GetStdHandle(_STD_OUTPUT_HANDLE)
        self._old_stdin_mode = self._get_console_mode(self._stdin_handle)
        self._old_stdout_mode = self._get_console_mode(self._stdout_handle)

        stdin_mode = (
            self._old_stdin_mode
            & ~(_ENABLE_PROCESSED_INPUT | _ENABLE_LINE_INPUT | _ENABLE_ECHO_INPUT | _ENABLE_QUICK_EDIT_MODE)
        ) | (_ENABLE_EXTENDED_FLAGS | _ENABLE_VIRTUAL_TERMINAL_INPUT)
        stdout_mode = self._old_stdout_mode | _ENABLE_PROCESSED_OUTPUT | _ENABLE_VIRTUAL_TERMINAL_PROCESSING

        self._set_console_mode(self._stdin_handle, stdin_mode)
        self._set_console_mode(self._stdout_handle, stdout_mode)

    def _get_kernel32(self) -> Any:
        if self._kernel32 is None:
            import ctypes

            windll = getattr(ctypes, "windll", None)
            if windll is None:
                raise OSError("Windows console APIs are unavailable")
            self._kernel32 = windll.kernel32
        return self._kernel32

    def _configure_kernel32_signatures(self, kernel32: Any) -> None:
        import ctypes
        from ctypes import wintypes

        kernel32.GetStdHandle.argtypes = [wintypes.DWORD]
        kernel32.GetStdHandle.restype = wintypes.HANDLE
        kernel32.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel32.GetConsoleMode.restype = wintypes.BOOL
        kernel32.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel32.SetConsoleMode.restype = wintypes.BOOL

    def _get_msvcrt(self) -> Any:
        if self._msvcrt is None:
            import msvcrt

            self._msvcrt = msvcrt
        return self._msvcrt

    def _get_console_mode(self, handle: int) -> int:
        import ctypes
        from ctypes import wintypes

        mode = wintypes.DWORD()
        if not self._get_kernel32().GetConsoleMode(handle, ctypes.byref(mode)):
            raise OSError(self._get_last_error(), "GetConsoleMode failed")
        return mode.value

    def _set_console_mode(self, handle: int, mode: int) -> None:
        if not self._get_kernel32().SetConsoleMode(handle, mode):
            raise OSError(self._get_last_error(), "SetConsoleMode failed")

    def _get_last_error(self) -> int:
        import ctypes

        get_last_error = getattr(ctypes, "get_last_error", None)
        return get_last_error() if get_last_error is not None else 0

    def _restore_console_best_effort(self) -> None:
        if self._stdin_handle is not None and self._old_stdin_mode is not None:
            with suppress(Exception):
                self._set_console_mode(self._stdin_handle, self._old_stdin_mode)
        if self._stdout_handle is not None and self._old_stdout_mode is not None:
            with suppress(Exception):
                self._set_console_mode(self._stdout_handle, self._old_stdout_mode)
        self._stdin_handle = None
        self._stdout_handle = None
        self._old_stdin_mode = None
        self._old_stdout_mode = None
        self._pending_windows_input.clear()

    def _read_stdin(self) -> None:
        if self._stdin_buffer is None:
            self._setup_stdin_buffer()
        while self._running:
            self._poll_resize()
            self._read_available_input()
            time.sleep(_WINDOWS_POLL_INTERVAL_SECONDS)

    def _read_available_input(self) -> None:
        msvcrt = self._get_msvcrt()
        if self._stdin_buffer is None:
            self._setup_stdin_buffer()
        while self._pending_windows_input or msvcrt.kbhit():
            sequence = self._read_next_sequence(msvcrt)
            if sequence is not None and self._stdin_buffer is not None:
                self._stdin_buffer.process(sequence)

    def _read_next_sequence(self, msvcrt: Any) -> str | None:
        if self._pending_windows_input:
            return self._pending_windows_input.pop(0)

        char = msvcrt.getwch()
        extended_key_sequences = _WINDOWS_EXTENDED_KEY_SEQUENCES.get(char)
        if extended_key_sequences is None:
            return char
        if not msvcrt.kbhit():
            return char
        extended = msvcrt.getwch()
        if char == "\x00" and len(extended) == 1 and 32 <= ord(extended) <= 126:
            self._pending_windows_input.append(extended)
            return char
        sequence = extended_key_sequences.get(extended)
        if sequence is None:
            self._pending_windows_input.append(extended)
            return char
        return sequence

    def _poll_resize(self) -> None:
        columns, rows = self._get_terminal_size()
        if columns == self._columns and rows == self._rows:
            return
        self._columns = columns
        self._rows = rows
        if self._on_resize is not None:
            self._on_resize()


def _select_process_terminal_base(
    platform: str = sys.platform,
) -> type[PosixProcessTerminal] | type[WindowsProcessTerminal]:
    if platform == "win32":
        return WindowsProcessTerminal
    return PosixProcessTerminal


if _select_process_terminal_base() is WindowsProcessTerminal:

    class ProcessTerminal(WindowsProcessTerminal):
        pass

else:

    class ProcessTerminal(PosixProcessTerminal):
        pass
