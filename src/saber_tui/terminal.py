from collections.abc import Callable
from types import FrameType
from typing import Protocol

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
        self._old_termios: list[int | bytes] | None = None
        self._old_sigwinch_handler: object | None = None
        self._reader_thread: object | None = None

    def start(self, on_input: InputHandler, on_resize: ResizeHandler) -> None:
        import signal
        import sys
        import termios
        import threading
        import tty

        self._on_input = on_input
        self._on_resize = on_resize
        stdin = sys.stdin
        self._old_termios = termios.tcgetattr(stdin.fileno())
        tty.setraw(stdin.fileno())
        self._update_size()
        self.write("\x1b[?2004h")
        self._old_sigwinch_handler = signal.getsignal(signal.SIGWINCH)
        signal.signal(signal.SIGWINCH, self._handle_sigwinch)
        self._running = True
        self._reader_thread = threading.Thread(target=self._read_stdin, daemon=True)
        self._reader_thread.start()

    def stop(self) -> None:
        import signal
        import sys
        import termios

        if not self._running and self._old_termios is None:
            return
        self._running = False
        self.write("\x1b[?2004l")
        if self._old_termios is not None:
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self._old_termios)
            self._old_termios = None
        if self._old_sigwinch_handler is not None:
            signal.signal(signal.SIGWINCH, self._old_sigwinch_handler)
            self._old_sigwinch_handler = None
        self._on_input = None
        self._on_resize = None

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
        self.write("\x1b[2K")

    def clear_from_cursor(self) -> None:
        self.write("\x1b[0J")

    def clear_screen(self) -> None:
        self.write("\x1b[2J\x1b[H")

    def set_title(self, title: str) -> None:
        self.write(f"\x1b]0;{title}\x07")

    def set_progress(self, active: bool) -> None:
        _ = active

    def _read_stdin(self) -> None:
        import os
        import sys

        stdin_fd = sys.stdin.fileno()
        while self._running:
            data = os.read(stdin_fd, 4096)
            if not data:
                break
            if self._on_input is not None:
                self._on_input(data.decode(errors="replace"))

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
