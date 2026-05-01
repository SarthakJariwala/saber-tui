import codecs
import threading
from collections.abc import Callable
from contextlib import suppress
from types import FrameType
from typing import Any, Protocol

InputHandler = Callable[[str], None]
ResizeHandler = Callable[[], None]


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


class ProcessTerminal:
    def __init__(self) -> None:
        self._columns = 80
        self._rows = 24
        self._on_input: InputHandler | None = None
        self._on_resize: ResizeHandler | None = None
        self._running = False
        self._old_termios: Any | None = None
        self._old_sigwinch_handler: Any | None = None
        self._reader_thread: threading.Thread | None = None
        self._input_decoder = codecs.getincrementaldecoder("utf-8")()

    def start(self, on_input: InputHandler, on_resize: ResizeHandler) -> None:
        import signal
        import sys
        import termios
        import threading
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
            self._reader_thread = threading.Thread(target=self._read_stdin, daemon=True)
            self._reader_thread.start()
        except Exception:
            self._running = False
            self._disable_bracketed_paste_best_effort()
            self._restore_termios_best_effort()
            self._restore_signal_best_effort()
            self._on_input = None
            self._on_resize = None
            self._reader_thread = None
            self._input_decoder.reset()
            raise

    def stop(self) -> None:
        if not self._running and self._old_termios is None and self._old_sigwinch_handler is None:
            return
        self._running = False
        self._disable_bracketed_paste_best_effort()
        self._restore_termios_best_effort()
        self._restore_signal_best_effort()
        reader_thread = self._reader_thread
        if reader_thread is not None and reader_thread is not threading.current_thread():
            reader_thread.join(timeout=0.2)
        self._reader_thread = None
        self._on_input = None
        self._on_resize = None
        self._input_decoder.reset()

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
        return False

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

    def _read_stdin(self) -> None:
        import os
        import select
        import sys

        stdin_fd = sys.stdin.fileno()
        while self._running:
            ready, _, _ = select.select([stdin_fd], [], [], 0.05)
            if not ready:
                continue
            data = os.read(stdin_fd, 4096)
            if not data:
                break
            text = self._decode_input(data)
            if text and self._on_input is not None:
                self._on_input(text)

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

    def _restore_termios_best_effort(self) -> None:
        if self._old_termios is None:
            return

        import sys
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

    def _update_size(self) -> None:
        import shutil

        size = shutil.get_terminal_size(fallback=(80, 24))
        self._columns = size.columns
        self._rows = size.lines
