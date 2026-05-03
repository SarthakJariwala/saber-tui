from saber_tui.tui import CURSOR_MARKER, TUI
from tests.virtual_terminal import VirtualTerminal


class StaticComponent:
    def __init__(self, lines: list[str]) -> None:
        self.lines = lines

    def render(self, width: int) -> list[str]:
        return self.lines

    def invalidate(self) -> None:
        return None


class CountingComponent(StaticComponent):
    def __init__(self, lines: list[str]) -> None:
        super().__init__(lines)
        self.render_calls = 0

    def render(self, width: int) -> list[str]:
        self.render_calls += 1
        return super().render(width)


def test_request_render_is_scheduled_until_flush() -> None:
    terminal = VirtualTerminal(columns=20, rows=5)
    component = StaticComponent(["one"])
    tui = TUI(terminal)
    tui.add_child(component)
    tui.start()
    tui.flush_render()
    terminal.clear_writes()

    component.lines = ["two"]
    tui.request_render()

    assert terminal.get_viewport()[0] == "one"
    tui.flush_render()
    assert terminal.get_viewport()[0] == "two"


def test_multiple_request_render_calls_coalesce_to_one_render() -> None:
    terminal = VirtualTerminal(columns=20, rows=5)
    component = CountingComponent(["one"])
    tui = TUI(terminal)
    tui.add_child(component)
    tui.start()
    tui.flush_render()
    component.render_calls = 0

    component.lines = ["two"]
    tui.request_render()
    component.lines = ["three"]
    tui.request_render()
    tui.flush_render()

    assert component.render_calls == 1
    assert terminal.get_viewport()[0] == "three"


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
    tui.request_render()
    tui.flush_render()

    assert terminal.get_viewport()[0] == "two"
    assert any("two" in write for write in terminal.writes)


def test_incremental_offscreen_change_preserves_visible_viewport() -> None:
    terminal = VirtualTerminal(columns=20, rows=3)
    component = StaticComponent(["offscreen", "visible 1", "visible 2", "visible 3"])
    tui = TUI(terminal)
    tui.add_child(component)
    tui.start()
    terminal.clear_writes()

    component.lines = ["changed offscreen", "visible 1", "visible 2", "visible 3"]
    tui.request_render()

    assert terminal.get_viewport() == ["visible 1", "visible 2", "visible 3"]
    assert "changed offscreen" not in "\n".join(terminal.get_viewport())


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


def test_first_render_does_not_clear_screen() -> None:
    terminal = VirtualTerminal(columns=20, rows=5)
    tui = TUI(terminal)
    tui.add_child(StaticComponent(["hello"]))

    tui.start()

    assert not any("\x1b[2J\x1b[H" in write for write in terminal.writes)


def test_forced_render_still_clears_screen() -> None:
    terminal = VirtualTerminal(columns=20, rows=5)
    tui = TUI(terminal)
    tui.add_child(StaticComponent(["hello"]))
    tui.start()
    terminal.clear_writes()

    tui.request_render(force=True)
    tui.flush_render()

    assert any("\x1b[2J\x1b[H\x1b[3J" in write for write in terminal.writes)


def test_clear_on_shrink_can_be_configured() -> None:
    terminal = VirtualTerminal(columns=20, rows=5)
    tui = TUI(terminal)

    assert tui.get_clear_on_shrink() is False
    tui.set_clear_on_shrink(True)
    assert tui.get_clear_on_shrink() is True
    tui.set_clear_on_shrink(False)
    assert tui.get_clear_on_shrink() is False


def test_hardware_cursor_can_be_toggled_at_runtime() -> None:
    terminal = VirtualTerminal(columns=20, rows=5)
    tui = TUI(terminal)
    tui.add_child(StaticComponent([f"ab{CURSOR_MARKER}cd"]))
    tui.start()
    terminal.clear_writes()

    assert tui.get_show_hardware_cursor() is False
    tui.set_show_hardware_cursor(True)
    tui.flush_render()

    assert tui.get_show_hardware_cursor() is True
    assert "\x1b[1;3H" in terminal.writes
    assert terminal.writes[-1] == "\x1b[?25h"

    terminal.clear_writes()
    tui.set_show_hardware_cursor(False)

    assert tui.get_show_hardware_cursor() is False
    assert terminal.writes == ("\x1b[?25l",)
