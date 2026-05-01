from saber_tui.tui import TUI
from tests.virtual_terminal import VirtualTerminal


class StaticComponent:
    def __init__(self, lines: list[str]) -> None:
        self.lines = lines

    def render(self, width: int) -> list[str]:
        return self.lines

    def invalidate(self) -> None:
        return None


class FocusableComponent(StaticComponent):
    focused = False


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


def test_overlay_visibility_change_restores_previous_focus_on_render() -> None:
    terminal = VirtualTerminal(columns=20, rows=5)
    base = FocusableComponent(["base content"])
    overlay_visible = True

    def is_visible(width: int, height: int) -> bool:
        _ = width, height
        return overlay_visible

    tui = TUI(terminal)
    tui.add_child(base)
    tui.set_focus(base)
    handle = tui.show_overlay(FocusableComponent(["MENU"]), {"visible": is_visible})
    tui.start()

    overlay_visible = False
    tui.request_render()

    assert not handle.is_focused()
    assert base.focused


def test_hiding_stacked_overlays_does_not_restore_removed_overlay_focus() -> None:
    terminal = VirtualTerminal(columns=20, rows=5)
    base = FocusableComponent(["base content"])
    overlay_a = FocusableComponent(["A"])
    overlay_b = FocusableComponent(["B"])
    tui = TUI(terminal)
    tui.add_child(base)
    tui.set_focus(base)
    handle_a = tui.show_overlay(overlay_a)
    handle_b = tui.show_overlay(overlay_b)
    tui.start()

    handle_a.hide()
    handle_b.hide()

    assert base.focused
    assert not overlay_a.focused
    assert not overlay_b.focused
