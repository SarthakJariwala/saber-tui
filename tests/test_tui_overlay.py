from saber_tui.tui import TUI, Container
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


def test_hiding_overlay_restores_focus_to_nested_child() -> None:
    terminal = VirtualTerminal(columns=20, rows=5)
    container = Container()
    nested = FocusableComponent(["nested content"])
    container.add_child(nested)
    tui = TUI(terminal)
    tui.add_child(container)
    tui.set_focus(nested)
    handle = tui.show_overlay(FocusableComponent(["overlay"]))
    tui.start()

    handle.hide()

    assert nested.focused
    assert handle.is_focused() is False


def test_overlay_focus_restores_by_focus_order_not_stack_order() -> None:
    terminal = VirtualTerminal(columns=20, rows=5)
    base = FocusableComponent(["base content"])
    overlay_a = FocusableComponent(["A"])
    overlay_b = FocusableComponent(["B"])
    overlay_c = FocusableComponent(["C"])
    tui = TUI(terminal)
    tui.add_child(base)
    tui.set_focus(base)
    handle_a = tui.show_overlay(overlay_a)
    handle_b = tui.show_overlay(overlay_b)
    tui.show_overlay(overlay_c)
    tui.start()

    handle_a.focus()
    handle_b.focus()
    handle_b.hide()

    assert handle_a.is_focused()
    assert overlay_a.focused
    assert not overlay_b.focused
    assert not overlay_c.focused


def test_hiding_top_overlay_restores_focus_to_nested_child_in_visible_overlay() -> None:
    terminal = VirtualTerminal(columns=20, rows=5)
    overlay_container = Container()
    nested = FocusableComponent(["nested overlay content"])
    overlay_container.add_child(nested)
    tui = TUI(terminal)
    tui.show_overlay(overlay_container)
    tui.set_focus(nested)
    top_handle = tui.show_overlay(FocusableComponent(["top overlay"]))
    tui.start()

    top_handle.hide()

    assert nested.focused
    assert not top_handle.is_focused()


def test_hiding_overlay_container_clears_focus_from_nested_child() -> None:
    terminal = VirtualTerminal(columns=20, rows=5)
    base = FocusableComponent(["base content"])
    overlay_container = Container()
    nested = FocusableComponent(["nested overlay content"])
    overlay_container.add_child(nested)
    tui = TUI(terminal)
    tui.add_child(base)
    tui.set_focus(base)
    handle = tui.show_overlay(overlay_container)
    tui.set_focus(nested)
    tui.start()

    handle.set_hidden(True)

    assert base.focused
    assert not nested.focused
    assert not tui.has_overlay()


def test_invisible_overlay_container_clears_focus_from_nested_child_on_render() -> None:
    terminal = VirtualTerminal(columns=20, rows=5)
    base = FocusableComponent(["base content"])
    overlay_container = Container()
    nested = FocusableComponent(["nested overlay content"])
    overlay_container.add_child(nested)
    overlay_visible = True

    def is_visible(width: int, height: int) -> bool:
        _ = width, height
        return overlay_visible

    tui = TUI(terminal)
    tui.add_child(base)
    tui.set_focus(base)
    handle = tui.show_overlay(overlay_container, {"visible": is_visible})
    tui.set_focus(nested)
    tui.start()

    overlay_visible = False
    tui.request_render()

    assert base.focused
    assert not nested.focused
    assert not handle.is_focused()
