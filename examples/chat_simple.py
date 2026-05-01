from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass

from saber_tui import TUI, Container, OverlayHandle, ProcessTerminal, Terminal, matches_key
from saber_tui.components import Box, Input, Loader, SelectItem, SelectList, Text
from saber_tui.utils import truncate_to_width, visible_width, wrap_text_with_ansi


def fg(r: int, g: int, b: int) -> Callable[[str], str]:
    def apply(text: str) -> str:
        return f"\x1b[38;2;{r};{g};{b}m{text}\x1b[39m"

    return apply


def bg(r: int, g: int, b: int) -> Callable[[str], str]:
    def apply(text: str) -> str:
        return f"\x1b[48;2;{r};{g};{b}m{text}\x1b[49m"

    return apply


def bold(text: str) -> str:
    return f"\x1b[1m{text}\x1b[22m"


@dataclass(frozen=True)
class Theme:
    name: str
    accent: Callable[[str], str]
    muted: Callable[[str], str]
    user: Callable[[str], str]
    assistant: Callable[[str], str]
    system: Callable[[str], str]
    panel_bg: Callable[[str], str]


THEMES = [
    Theme(
        "Ocean",
        fg(125, 211, 252),
        fg(148, 163, 184),
        fg(134, 239, 172),
        fg(191, 219, 254),
        fg(253, 224, 71),
        bg(20, 32, 48),
    ),
    Theme(
        "Ember",
        fg(251, 146, 60),
        fg(161, 161, 170),
        fg(253, 186, 116),
        fg(254, 215, 170),
        fg(250, 204, 21),
        bg(48, 31, 24),
    ),
    Theme(
        "Violet",
        fg(196, 181, 253),
        fg(148, 163, 184),
        fg(216, 180, 254),
        fg(221, 214, 254),
        fg(251, 191, 36),
        bg(35, 30, 58),
    ),
]


COMMANDS = [
    SelectItem("/help", "/help", "Show available commands and keyboard shortcuts"),
    SelectItem("/clear", "/clear", "Clear the transcript while keeping the UI running"),
    SelectItem("/theme", "/theme", "Cycle the ANSI color theme"),
    SelectItem("/loading", "/loading", "Toggle the loader component in the transcript"),
    SelectItem("/quit", "/quit", "Stop the TUI and return to the shell"),
]


@dataclass
class Message:
    role: str
    text: str
    style: Callable[[str], str]


class HeroPanel:
    def __init__(self, app: ShowcaseApp) -> None:
        self.app = app

    def invalidate(self) -> None:
        pass

    def render(self, width: int) -> list[str]:
        theme = self.app.theme
        box = Box(padding_x=1, padding_y=1, bg_fn=theme.panel_bg)
        box.add_child(
            Text(
                "\n".join(
                    [
                        bold(theme.accent("Saber TUI Showcase")),
                        "A compact demo of Text, Box, Input, overlays, key listeners, and ANSI styling.",
                        theme.muted("Type a message, try /help, or press Ctrl+P for the command palette."),
                    ]
                ),
                padding_x=0,
                padding_y=0,
            )
        )
        return box.render(width)


class TranscriptPanel:
    def __init__(self, app: ShowcaseApp, max_rows: int = 8) -> None:
        self.app = app
        self.max_rows = max_rows

    def invalidate(self) -> None:
        pass

    def render(self, width: int) -> list[str]:
        theme = self.app.theme
        lines = [bold(theme.accent("Transcript"))]

        content_lines: list[str] = []
        for message in self.app.messages[-self.max_rows :]:
            content_lines.extend(self._render_message(message, max(1, width)))

        if self.app.loader is not None:
            content_lines.extend(self.app.loader.render(width)[-1:])

        visible = content_lines[-self.max_rows :]
        while len(visible) < self.max_rows:
            visible.append("")
        return [*lines, *visible]

    def _render_message(self, message: Message, width: int) -> list[str]:
        prefix = message.style(f"{message.role}: ")
        prefix_width = visible_width(f"{message.role}: ")
        body_width = max(1, width - prefix_width)
        wrapped = wrap_text_with_ansi(message.text, body_width) or [""]
        lines = [truncate_to_width(f"{prefix}{wrapped[0]}", width, "")]
        continuation = " " * prefix_width
        for line in wrapped[1:]:
            lines.append(truncate_to_width(f"{continuation}{line}", width, ""))
        return lines


class StatusPanel:
    def __init__(self, app: ShowcaseApp) -> None:
        self.app = app

    def invalidate(self) -> None:
        pass

    def render(self, width: int) -> list[str]:
        theme = self.app.theme
        box = Box(padding_x=1, padding_y=0, bg_fn=theme.panel_bg)
        box.add_child(
            Text(
                "\n".join(
                    [
                        f"{theme.accent('Mode')} {self.app.mode}  {theme.accent('Theme')} {theme.name}",
                        theme.muted(
                            "Enter: send | Ctrl+P: palette | /help /clear /theme /loading /quit | Ctrl+C: exit"
                        ),
                    ]
                ),
                padding_x=0,
                padding_y=0,
            )
        )
        return box.render(width)


class CommandPalette:
    def __init__(self, title: str, select_list: SelectList, theme: Theme) -> None:
        self.title = title
        self.select_list = select_list
        self.theme = theme
        self.focused = False

    def invalidate(self) -> None:
        self.select_list.invalidate()

    def handle_input(self, data: str) -> None:
        self.select_list.handle_input(data)

    def render(self, width: int) -> list[str]:
        box = Box(padding_x=1, padding_y=1, bg_fn=self.theme.panel_bg)
        container = Container()
        container.add_child(Text(bold(self.theme.accent(self.title)), padding_x=0, padding_y=0))
        container.add_child(self.select_list)
        box.add_child(container)
        return box.render(width)


class ShowcaseApp:
    def __init__(self, terminal: Terminal | None = None, on_exit: Callable[[], None] | None = None) -> None:
        self.terminal = terminal or ProcessTerminal()
        self.on_exit = on_exit
        self.tui = TUI(self.terminal)
        self.theme_index = 0
        self.mode = "Chat"
        self.messages: list[Message] = []
        self.loader: Loader | None = None
        self.palette_handle: OverlayHandle | None = None
        self.input_box = Input()
        self._exit_requested = False

        self._build()
        self.add_system("Welcome. This example is intentionally small, but it exercises the core TUI primitives.")
        self.add_system("Commands: /help, /clear, /theme, /loading, /quit. Press Ctrl+P for a SelectList overlay.")

    @property
    def theme(self) -> Theme:
        return THEMES[self.theme_index]

    def _build(self) -> None:
        self.tui.add_child(HeroPanel(self))
        self.tui.add_child(TranscriptPanel(self))
        self.tui.add_child(StatusPanel(self))
        self.input_box.on_submit = self.submit
        self.input_box.on_escape = self.open_palette
        self.tui.add_child(self.input_box)
        self.tui.set_focus(self.input_box)
        self.tui.add_input_listener(self._handle_global_input)

    def _handle_global_input(self, data: str):
        if matches_key(data, "ctrl+c"):
            self.request_exit()
            return {"consume": True}
        if matches_key(data, "ctrl+p"):
            self.open_palette()
            return {"consume": True}
        return None

    def submit(self, value: str) -> None:
        value = value.strip()
        self.input_box.set_value("")
        if not value:
            self.add_system("Empty messages are ignored.")
            return
        if value.startswith("/"):
            self.execute_command(value)
            return
        self.add_message("You", value, self.theme.user)
        self.add_message(
            "Assistant",
            "Echoed your message. Try Ctrl+P to run a command without typing it.",
            self.theme.assistant,
        )

    def execute_command(self, command: str) -> None:
        command = command.strip().split(maxsplit=1)[0].lower()
        if command == "/help":
            self.add_system(
                "Commands: /help, /clear, /theme, /loading, /quit. Keyboard: Ctrl+P opens commands, Ctrl+C exits."
            )
        elif command == "/clear":
            self.stop_loader()
            self.messages = []
            self.add_system("Transcript cleared.")
            self.tui.request_render()
        elif command == "/theme":
            self.theme_index = (self.theme_index + 1) % len(THEMES)
            self.add_system(f"Theme switched to {self.theme.name}.")
            self.tui.invalidate()
            self.tui.request_render()
        elif command == "/loading":
            self.toggle_loader()
        elif command == "/quit":
            self.request_exit()
        else:
            self.add_system(f"Unknown command: {command}. Type /help for options.")

    def open_palette(self) -> None:
        if self.palette_handle is not None and not self.palette_handle.is_hidden():
            return

        select_list = SelectList(COMMANDS, max_visible=len(COMMANDS))
        select_list.on_select = lambda item: self._select_command(item.value)
        select_list.on_cancel = self.close_palette
        overlay = CommandPalette("Command Palette", select_list, self.theme)
        self.palette_handle = self.tui.show_overlay(
            overlay,
            {
                "width": "72%",
                "maxHeight": 10,
                "anchor": "bottom-center",
                "margin": 1,
            },
        )

    def _select_command(self, command: str) -> None:
        self.close_palette()
        self.execute_command(command)
        self.tui.set_focus(self.input_box)
        self.tui.request_render()

    def close_palette(self) -> None:
        if self.palette_handle is None:
            return
        self.palette_handle.hide()
        self.palette_handle = None
        self.tui.set_focus(self.input_box)

    def toggle_loader(self) -> None:
        if self.loader is not None:
            self.stop_loader()
            self.add_system("Loader stopped.")
            return
        self.loader = Loader(
            self.tui,
            spinner_style=self.theme.accent,
            text_style=self.theme.muted,
            text="Simulating loader animation...",
            indicator={"frames": ["-", "\\", "|", "/"], "intervalMs": 120},
        )
        self.add_system("Loader started. Run /loading again to stop it.")

    def stop_loader(self) -> None:
        if self.loader is not None:
            self.loader.stop()
            self.loader = None

    def add_system(self, text: str) -> None:
        self.add_message("System", text, self.theme.system)

    def add_message(self, role: str, text: str, style: Callable[[str], str]) -> None:
        self.messages.append(Message(role, text, style))
        self.tui.request_render()

    def request_exit(self) -> None:
        if self._exit_requested:
            return
        self._exit_requested = True
        self.stop()
        if self.on_exit is not None:
            self.on_exit()

    def stop(self) -> None:
        self.stop_loader()
        self.tui.stop()


def create_app(terminal: Terminal | None = None, on_exit: Callable[[], None] | None = None) -> ShowcaseApp:
    return ShowcaseApp(terminal=terminal, on_exit=on_exit)


def build_app(terminal: Terminal | None = None, on_exit: Callable[[], None] | None = None) -> tuple[TUI, Input]:
    app = create_app(terminal=terminal, on_exit=on_exit)
    return app.tui, app.input_box


def run_app(app: ShowcaseApp | TUI, stop_event: threading.Event) -> None:
    tui = app.tui if isinstance(app, ShowcaseApp) else app
    try:
        tui.start()
        stop_event.wait()
    except KeyboardInterrupt:
        pass
    finally:
        if isinstance(app, ShowcaseApp):
            app.stop()
        else:
            tui.stop()


def main() -> None:
    stop_event = threading.Event()
    app = create_app(on_exit=stop_event.set)
    run_app(app, stop_event)


if __name__ == "__main__":
    main()
