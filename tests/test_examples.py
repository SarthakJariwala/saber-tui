import importlib.util
import sys
import threading
from pathlib import Path

from tests.virtual_terminal import VirtualTerminal


def test_chat_simple_example_imports() -> None:
    module = _load_chat_simple()
    assert hasattr(module, "build_app")
    assert hasattr(module, "create_app")


def test_showcase_renders_header_and_command_hints() -> None:
    module = _load_chat_simple()
    terminal = VirtualTerminal()
    app = module.create_app(terminal=terminal)

    app.tui.start()

    viewport = "\n".join(terminal.get_viewport())
    assert "Saber TUI Showcase" in viewport
    assert "Ctrl+P" in viewport
    assert "/help" in viewport
    app.stop()


def test_showcase_submits_message_and_clears_input() -> None:
    module = _load_chat_simple()
    terminal = VirtualTerminal(columns=80, rows=18)
    app = module.create_app(terminal=terminal)

    app.tui.start()
    _send_keys(terminal, "hello\r")

    viewport = "\n".join(terminal.get_viewport())
    assert "You: hello" in viewport
    assert "Assistant:" in viewport
    assert app.input_box.get_value() == ""
    app.stop()


def test_showcase_composer_inserts_shift_enter_newline() -> None:
    module = _load_chat_simple()
    terminal = VirtualTerminal(columns=80, rows=18)
    app = module.create_app(terminal=terminal, auto_stream=False)

    app.tui.start()
    _send_keys(terminal, "first")
    terminal.send_input("\x1b[13;2u")
    _send_keys(terminal, "second")

    assert app.input_box.get_value() == "first\nsecond"

    terminal.send_input("\r")

    viewport = "\n".join(terminal.get_viewport())
    assert "You: first" in viewport
    assert "second" in viewport
    assert app.input_box.get_value() == ""
    app.stop()


def test_showcase_streams_assistant_response_while_input_stays_focused() -> None:
    module = _load_chat_simple()
    terminal = VirtualTerminal(columns=80, rows=18)
    app = module.create_app(terminal=terminal, auto_stream=False)

    app.tui.start()
    _send_keys(terminal, "stream this\r")

    assert app.is_streaming
    assert app.input_box.focused

    first = app.advance_stream()
    second = app.advance_stream()

    assert first
    assert second
    assert "Assistant:" in "\n".join(terminal.get_viewport())
    assert app.input_box.focused
    app.stop()


def test_showcase_transcript_scrolls_without_losing_input_focus() -> None:
    module = _load_chat_simple()
    terminal = VirtualTerminal(columns=80, rows=18)
    app = module.create_app(terminal=terminal, auto_stream=False)

    app.tui.start()
    for index in range(14):
        app.add_system(f"scroll item {index}")

    assert "scroll item 13" in "\n".join(terminal.get_viewport())

    terminal.send_input("\x1bp")

    viewport = "\n".join(terminal.get_viewport())
    assert app.transcript_scroll > 0
    assert "scroll item 13" not in viewport
    assert app.input_box.focused

    terminal.send_input("\x1bn")

    assert app.transcript_scroll == 0
    assert "scroll item 13" in "\n".join(terminal.get_viewport())
    app.stop()


def test_showcase_clear_command_resets_transcript() -> None:
    module = _load_chat_simple()
    terminal = VirtualTerminal(columns=80, rows=18)
    app = module.create_app(terminal=terminal)

    app.tui.start()
    _send_keys(terminal, "hello\r")
    _send_keys(terminal, "/clear\r")

    viewport = "\n".join(terminal.get_viewport())
    assert "Transcript cleared." in viewport
    assert "You: hello" not in viewport
    app.stop()


def test_showcase_command_palette_selects_help_and_restores_input_focus() -> None:
    module = _load_chat_simple()
    terminal = VirtualTerminal(columns=80, rows=18)
    app = module.create_app(terminal=terminal)

    app.tui.start()
    terminal.send_input("\x10")

    assert app.tui.has_overlay()
    assert "Command Palette" in "\n".join(terminal.get_viewport())

    terminal.send_input("\r")

    viewport = "\n".join(terminal.get_viewport())
    assert not app.tui.has_overlay()
    assert "Commands:" in viewport
    assert app.input_box.focused
    app.stop()


def test_showcase_ctrl_c_stops_tui_and_signals_exit() -> None:
    module = _load_chat_simple()
    terminal = VirtualTerminal()
    exited: list[bool] = []

    app = module.create_app(terminal=terminal, on_exit=lambda: exited.append(True))
    app.tui.start()
    terminal.send_input("\x03")

    assert app.tui.stopped
    assert exited == [True]


def test_showcase_run_app_waits_and_stops() -> None:
    module = _load_chat_simple()
    terminal = VirtualTerminal()
    app = module.create_app(terminal=terminal)
    stop_event = RecordingEvent()

    module.run_app(app, stop_event)

    assert stop_event.wait_called
    assert app.tui.stopped


class RecordingEvent(threading.Event):
    def __init__(self) -> None:
        super().__init__()
        self.wait_called = False

    def wait(self, timeout: float | None = None) -> bool:
        self.wait_called = True
        return True


def _load_chat_simple():
    path = Path("examples/chat_simple.py")
    spec = importlib.util.spec_from_file_location("chat_simple", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _send_keys(terminal: VirtualTerminal, text: str) -> None:
    for char in text:
        terminal.send_input(char)
