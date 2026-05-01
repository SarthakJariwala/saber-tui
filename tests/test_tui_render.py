from saber_tui.tui import CURSOR_MARKER, TUI
from tests.virtual_terminal import VirtualTerminal


class StaticComponent:
    def __init__(self, lines: list[str]) -> None:
        self.lines = lines

    def render(self, width: int) -> list[str]:
        return self.lines

    def invalidate(self) -> None:
        return None


def test_start_renders_children() -> None:
    terminal = VirtualTerminal(columns=20, rows=5)
    tui = TUI(terminal)
    tui.add_child(StaticComponent(["hello", "world"]))

    tui.start()

    assert terminal.get_viewport()[0] == "hello"
    assert terminal.get_viewport()[1] == "world"


def test_request_render_updates_changed_line() -> None:
    terminal = VirtualTerminal(columns=20, rows=5)
    component = StaticComponent(["one"])
    tui = TUI(terminal)
    tui.add_child(component)
    tui.start()
    terminal.clear_writes()

    component.lines = ["two"]
    tui.request_render(force=True)

    assert terminal.get_viewport()[0] == "two"
    assert any("two" in write for write in terminal.writes)


def test_cursor_marker_is_stripped_from_output() -> None:
    terminal = VirtualTerminal(columns=20, rows=5)
    tui = TUI(terminal, show_hardware_cursor=True)
    tui.add_child(StaticComponent([f"ab{CURSOR_MARKER}cd"]))

    tui.start()

    assert CURSOR_MARKER not in "\n".join(terminal.get_viewport())


def test_cursor_marker_above_viewport_is_stripped_from_writes() -> None:
    terminal = VirtualTerminal(columns=20, rows=3)
    tui = TUI(terminal, show_hardware_cursor=True)
    tui.add_child(StaticComponent([f"hidden{CURSOR_MARKER}", "line 2", "line 3", "line 4"]))

    tui.start()

    assert CURSOR_MARKER not in "".join(terminal.writes)
    assert CURSOR_MARKER not in "\n".join(terminal.get_viewport())


def test_first_render_clears_screen() -> None:
    terminal = VirtualTerminal(columns=20, rows=5)
    tui = TUI(terminal)
    tui.add_child(StaticComponent(["hello"]))

    tui.start()

    assert any("\x1b[2J\x1b[H" in write for write in terminal.writes)
