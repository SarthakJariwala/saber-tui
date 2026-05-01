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
