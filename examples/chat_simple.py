from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass

from saber_tui import (
    CURSOR_MARKER,
    TUI,
    Container,
    OverlayHandle,
    ProcessTerminal,
    Terminal,
    decode_printable_key,
    matches_key,
)
from saber_tui.components import Box, Loader, SelectItem, SelectList, Text
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

STREAM_RESPONSE_TEMPLATE = (
    "Streaming response: I can update this transcript in small chunks while focus stays on the composer, "
    "so you can keep typing, open the palette, scroll history, or exit immediately."
)


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
        scroll_label = f" scroll +{self.app.transcript_scroll}" if self.app.transcript_scroll else ""
        lines = [bold(theme.accent(f"Transcript{scroll_label}"))]

        content_lines: list[str] = []
        for message in self.app.messages:
            content_lines.extend(self._render_message(message, max(1, width)))

        if self.app.loader is not None:
            content_lines.extend(self.app.loader.render(width)[-1:])

        max_scroll = max(0, len(content_lines) - self.max_rows)
        self.app.transcript_scroll = min(self.app.transcript_scroll, max_scroll)
        start = max(0, len(content_lines) - self.max_rows - self.app.transcript_scroll)
        visible = content_lines[start : start + self.max_rows]
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
                            "Enter: send | Shift+Enter: newline | Alt+Up/Down: scroll | Ctrl+P: palette | Ctrl+C: exit"
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


class Composer:
    def __init__(self, app: ShowcaseApp) -> None:
        self.app = app
        self.value = ""
        self.focused = False
        self.on_submit: Callable[[str], None] | None = None
        self.on_escape: Callable[[], None] | None = None
        self._paste_buffer = ""
        self._is_in_paste = False

    def get_value(self) -> str:
        return self.value

    def set_value(self, value: str) -> None:
        self.value = value

    def invalidate(self) -> None:
        pass

    def handle_input(self, data: str) -> None:
        if "\x1b[200~" in data:
            self._is_in_paste = True
            self._paste_buffer = ""
            data = data.replace("\x1b[200~", "")

        if self._is_in_paste:
            self._paste_buffer += data
            end_index = self._paste_buffer.find("\x1b[201~")
            if end_index != -1:
                paste_content = self._paste_buffer[:end_index]
                remaining = self._paste_buffer[end_index + len("\x1b[201~") :]
                self._insert_text(paste_content.replace("\r\n", "\n").replace("\r", "\n"))
                self._is_in_paste = False
                self._paste_buffer = ""
                if remaining:
                    self.handle_input(remaining)
            return

        if matches_key(data, "escape"):
            if self.on_escape is not None:
                self.on_escape()
            return

        if matches_key(data, "shift+enter"):
            self._insert_text("\n")
            return

        if matches_key(data, "enter"):
            if self.on_submit is not None:
                self.on_submit(self.value)
            return

        if matches_key(data, "backspace"):
            self.value = self.value[:-1]
            return

        if matches_key(data, "ctrl+u"):
            self.value = ""
            return

        printable = decode_printable_key(data)
        if printable is not None:
            self._insert_text(printable)
            return

        if data and not any(_is_control_character(char) for char in data):
            self._insert_text(data)

    def _insert_text(self, text: str) -> None:
        self.value += text

    def render(self, width: int) -> list[str]:
        theme = self.app.theme
        render_width = max(1, width)
        lines = [f"{theme.accent('Composer')} {theme.muted('Enter sends. Shift+Enter adds a line. Ctrl+U clears.')}"]
        raw_lines = self.value.split("\n") if self.value else [""]
        visible_lines = raw_lines[-4:]

        for index, line in enumerate(visible_lines):
            prompt = "> " if index == 0 and len(raw_lines) == len(visible_lines) else "  "
            rendered = f"{prompt}{line}"
            if index == len(visible_lines) - 1 and self.focused:
                rendered += f"{CURSOR_MARKER}\x1b[7m \x1b[27m"
            lines.append(rendered)

        return [theme.panel_bg(truncate_to_width(line, render_width, "")) for line in lines]


def _is_control_character(char: str) -> bool:
    code = ord(char)
    return code < 32 or code == 0x7F or 0x80 <= code <= 0x9F


class ShowcaseApp:
    def __init__(
        self,
        terminal: Terminal | None = None,
        on_exit: Callable[[], None] | None = None,
        auto_stream: bool = True,
        stream_interval: float = 0.08,
    ) -> None:
        self.terminal = terminal or ProcessTerminal()
        self.on_exit = on_exit
        self.auto_stream = auto_stream
        self.stream_interval = stream_interval
        self.tui = TUI(self.terminal)
        self.theme_index = 0
        self.mode = "Chat"
        self.messages: list[Message] = []
        self.transcript_scroll = 0
        self.loader: Loader | None = None
        self.palette_handle: OverlayHandle | None = None
        self.input_box = Composer(self)
        self._stream_message: Message | None = None
        self._stream_chunks: list[str] = []
        self._stream_timer: threading.Timer | None = None
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
        if matches_key(data, "alt+up") or matches_key(data, "pageUp"):
            self.scroll_transcript(3)
            return {"consume": True}
        if matches_key(data, "alt+down") or matches_key(data, "pageDown"):
            self.scroll_transcript(-3)
            return {"consume": True}
        return None

    @property
    def is_streaming(self) -> bool:
        return self._stream_message is not None

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
        self.start_streaming_response(value)

    def execute_command(self, command: str) -> None:
        command = command.strip().split(maxsplit=1)[0].lower()
        if command == "/help":
            self.add_system(
                "Commands: /help, /clear, /theme, /loading, /quit. Keyboard: Ctrl+P opens commands, Ctrl+C exits."
            )
        elif command == "/clear":
            self.cancel_stream()
            self.stop_loader()
            self.messages = []
            self.transcript_scroll = 0
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

    def start_streaming_response(self, prompt: str) -> None:
        self.cancel_stream()
        response = STREAM_RESPONSE_TEMPLATE
        if "\n" in prompt:
            response += " I also received your multiline prompt."
        self._stream_message = Message("Assistant", "", self.theme.assistant)
        self.messages.append(self._stream_message)
        self._stream_chunks = self._split_stream_chunks(response)
        self.transcript_scroll = 0
        self.tui.set_focus(self.input_box)
        self.tui.request_render()
        self._schedule_stream()

    def _split_stream_chunks(self, text: str) -> list[str]:
        words = text.split(" ")
        chunks: list[str] = []
        for index, word in enumerate(words):
            suffix = "" if index == len(words) - 1 else " "
            chunks.append(f"{word}{suffix}")
        return chunks

    def _schedule_stream(self) -> None:
        if not self.auto_stream or not self._stream_chunks:
            return
        self._stream_timer = threading.Timer(self.stream_interval, self._stream_tick)
        self._stream_timer.daemon = True
        self._stream_timer.start()

    def _stream_tick(self) -> None:
        if self.advance_stream():
            self._schedule_stream()

    def advance_stream(self) -> bool:
        if self._stream_message is None or not self._stream_chunks:
            self._stream_message = None
            return False
        self._stream_message.text += self._stream_chunks.pop(0)
        if not self._stream_chunks:
            self._stream_message = None
        self.transcript_scroll = 0
        self.tui.set_focus(self.input_box)
        self.tui.request_render()
        return True

    def cancel_stream(self) -> None:
        if self._stream_timer is not None:
            self._stream_timer.cancel()
            self._stream_timer = None
        self._stream_message = None
        self._stream_chunks = []

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
        if self.transcript_scroll == 0:
            self.transcript_scroll = 0
        self.tui.request_render()

    def scroll_transcript(self, delta: int) -> None:
        self.transcript_scroll = max(0, self.transcript_scroll + delta)
        self.tui.set_focus(self.input_box)
        self.tui.request_render()

    def request_exit(self) -> None:
        if self._exit_requested:
            return
        self._exit_requested = True
        self.stop()
        if self.on_exit is not None:
            self.on_exit()

    def stop(self) -> None:
        self.cancel_stream()
        self.stop_loader()
        self.tui.stop()


def create_app(
    terminal: Terminal | None = None,
    on_exit: Callable[[], None] | None = None,
    auto_stream: bool = True,
    stream_interval: float = 0.08,
) -> ShowcaseApp:
    return ShowcaseApp(
        terminal=terminal,
        on_exit=on_exit,
        auto_stream=auto_stream,
        stream_interval=stream_interval,
    )


def build_app(terminal: Terminal | None = None, on_exit: Callable[[], None] | None = None) -> tuple[TUI, Composer]:
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
