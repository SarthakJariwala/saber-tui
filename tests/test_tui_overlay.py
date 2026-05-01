from saber_tui.tui import TUI
from tests.virtual_terminal import VirtualTerminal


class StaticComponent:
    def __init__(self, lines: list[str]) -> None:
        self.lines = lines

    def render(self, width: int) -> list[str]:
        return self.lines

    def invalidate(self) -> None:
        return None


def test_overlay_composites_over_base_content() -> None:
    terminal = VirtualTerminal(columns=20, rows=5)
    tui = TUI(terminal)
    tui.add_child(StaticComponent(["base content"]))

    tui.show_overlay(StaticComponent(["MENU"]), {"width": 6, "row": 0, "col": 2})
    tui.start()

    assert terminal.get_viewport()[0].startswith("baMENU")


def test_overlay_handle_can_hide_overlay() -> None:
    terminal = VirtualTerminal(columns=20, rows=5)
    tui = TUI(terminal)
    tui.add_child(StaticComponent(["base content"]))
    handle = tui.show_overlay(StaticComponent(["MENU"]), {"width": 6, "row": 0, "col": 2})
    tui.start()

    handle.hide()

    assert terminal.get_viewport()[0].startswith("base content")
