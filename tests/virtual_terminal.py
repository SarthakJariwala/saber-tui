import pyte

from saber_tui.terminal import InputHandler, ResizeHandler


class VirtualTerminal:
    def __init__(self, columns: int = 80, rows: int = 24) -> None:
        self._columns = columns
        self._rows = rows
        self._screen = pyte.Screen(columns, rows)
        self._stream = pyte.Stream(self._screen)
        self._writes: list[str] = []
        self._on_input: InputHandler | None = None
        self._on_resize: ResizeHandler | None = None

    def start(self, on_input: InputHandler, on_resize: ResizeHandler) -> None:
        self._on_input = on_input
        self._on_resize = on_resize
        self.write("\x1b[?2004h")

    def stop(self) -> None:
        self.write("\x1b[?2004l")
        self._on_input = None
        self._on_resize = None

    def drain_input(self, max_ms: int = 1000, idle_ms: int = 50) -> None:
        _ = max_ms, idle_ms

    def write(self, data: str) -> None:
        self._writes.append(data)
        self._stream.feed(data)

    @property
    def columns(self) -> int:
        return self._columns

    @property
    def rows(self) -> int:
        return self._rows

    @property
    def kitty_protocol_active(self) -> bool:
        return True

    def send_input(self, data: str) -> None:
        if self._on_input is not None:
            self._on_input(data)

    def resize(self, columns: int, rows: int) -> None:
        self._columns = columns
        self._rows = rows
        self._screen.resize(rows, columns)
        if self._on_resize is not None:
            self._on_resize()

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

    def clear_writes(self) -> None:
        self._writes.clear()

    def get_viewport(self) -> list[str]:
        return [line.rstrip() for line in self._screen.display]

    @property
    def writes(self) -> tuple[str, ...]:
        return tuple(self._writes)
