import importlib.util
import threading
from pathlib import Path

from tests.virtual_terminal import VirtualTerminal


def test_chat_simple_example_imports() -> None:
    module = _load_chat_simple()
    assert hasattr(module, "build_app")


def test_chat_simple_ctrl_c_stops_tui_and_signals_exit() -> None:
    module = _load_chat_simple()
    terminal = VirtualTerminal()
    exited: list[bool] = []

    tui, _input_box = module.build_app(terminal=terminal, on_exit=lambda: exited.append(True))
    tui.start()
    terminal.send_input("\x03")

    assert tui.stopped
    assert exited == [True]


def test_chat_simple_run_app_waits_and_stops() -> None:
    module = _load_chat_simple()
    terminal = VirtualTerminal()
    tui, _input_box = module.build_app(terminal=terminal)
    stop_event = RecordingEvent()

    module.run_app(tui, stop_event)

    assert stop_event.wait_called
    assert tui.stopped


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
    spec.loader.exec_module(module)
    return module
