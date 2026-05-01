from __future__ import annotations

from saber_tui import TUI, ProcessTerminal, matches_key
from saber_tui.components import Input, Text


def build_app() -> tuple[TUI, Input]:
    terminal = ProcessTerminal()
    tui = TUI(terminal)
    tui.add_child(Text("Welcome to Simple Chat!\nType a message below. Press Ctrl+C to exit."))

    input_box = Input()

    def submit(value: str) -> None:
        if value.strip():
            tui.add_child(Text(f"You said: {value}", padding_x=1, padding_y=0))
            tui.request_render()

    input_box.on_submit = submit
    tui.add_child(input_box)
    tui.set_focus(input_box)

    def exit_on_ctrl_c(data: str):
        if matches_key(data, "ctrl+c"):
            tui.stop()
            raise SystemExit(0)
        return None

    tui.add_input_listener(exit_on_ctrl_c)
    return tui, input_box


def main() -> None:
    tui, _input_box = build_app()
    tui.start()


if __name__ == "__main__":
    main()
