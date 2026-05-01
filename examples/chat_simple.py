from __future__ import annotations

import threading
from collections.abc import Callable

from saber_tui import TUI, ProcessTerminal, Terminal, matches_key
from saber_tui.components import Input, Text


def build_app(terminal: Terminal | None = None, on_exit: Callable[[], None] | None = None) -> tuple[TUI, Input]:
    terminal = terminal or ProcessTerminal()
    tui = TUI(terminal)
    tui.add_child(Text("Welcome to Simple Chat!\nType a message below. Press Ctrl+C to exit."))

    input_box = Input()

    def submit(value: str) -> None:
        tui.add_child(Text(f"You said: {value}", padding_x=1, padding_y=0))
        tui.request_render()

    input_box.on_submit = submit
    tui.add_child(input_box)
    tui.set_focus(input_box)

    def exit_on_ctrl_c(data: str):
        if matches_key(data, "ctrl+c"):
            tui.stop()
            if on_exit is not None:
                on_exit()
            return {"consume": True}
        return None

    tui.add_input_listener(exit_on_ctrl_c)
    return tui, input_box


def run_app(tui: TUI, stop_event: threading.Event) -> None:
    try:
        tui.start()
        stop_event.wait()
    except KeyboardInterrupt:
        pass
    finally:
        tui.stop()


def main() -> None:
    stop_event = threading.Event()
    tui, _input_box = build_app(on_exit=stop_event.set)
    run_app(tui, stop_event)


if __name__ == "__main__":
    main()
