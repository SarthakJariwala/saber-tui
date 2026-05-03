"""Streaming chat demo with native terminal scrollback.

Run with:

    uv run python examples/chat.py

Type a message and Enter to send. The assistant streams an echo response
word-by-word. The chat log is appended to the normal TUI render tree, like the
pi coding-agent interactive mode, so terminal scrollback owns history. Ctrl+C
quits.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from saber_tui import (
    TUI,
    Container,
    ProcessTerminal,
    Terminal,
    matches_key,
)
from saber_tui.components import Editor, EditorTheme, Spacer
from saber_tui.components.select_list import SelectListTheme
from saber_tui.utils import visible_width, wrap_text_with_ansi

# ── ANSI helpers ──────────────────────────────────────────────────────────

def fg(r: int, g: int, b: int) -> Callable[[str], str]:
    code = f"\x1b[38;2;{r};{g};{b}m"
    return lambda text: f"{code}{text}\x1b[39m"


def bg(r: int, g: int, b: int) -> Callable[[str], str]:
    code = f"\x1b[48;2;{r};{g};{b}m"
    return lambda text: f"{code}{text}\x1b[49m"


def bold(text: str) -> str:
    return f"\x1b[1m{text}\x1b[22m"


USER_FG = fg(125, 211, 252)  # sky
ASST_FG = fg(134, 239, 172)  # mint
SYSTEM_FG = fg(251, 191, 36)  # amber
MUTED = fg(148, 163, 184)  # slate
HEADER_BG = bg(30, 58, 138)  # indigo-900
FOOTER_BG = bg(15, 23, 42)  # slate-950


# ── Streaming config ──────────────────────────────────────────────────────

STREAM_INTERVAL_MS = 40
STREAM_TEMPLATE = (
    "Sure — here is what you said, streamed back word by word as if I were a "
    "real LLM. The point of this demo is the streaming UI itself; completed "
    "turns flow into terminal scrollback while the editor remains live. "
    "Your message was: "
)


# ── Messages ──────────────────────────────────────────────────────────────

@dataclass
class Message:
    role: str  # "user" | "assistant" | "system"
    text: str  # current visible text (grows during streaming)


def _role_styling(role: str) -> tuple[str, Callable[[str], str]]:
    if role == "user":
        return "You", USER_FG
    if role == "assistant":
        return "Assistant", ASST_FG
    if role == "system":
        return "System", SYSTEM_FG
    return "?", MUTED


class _MessageComponent:
    def __init__(self, message: Message, show_stream_cursor: bool = False) -> None:
        self.message = message
        self.show_stream_cursor = show_stream_cursor

    def invalidate(self) -> None:
        return None

    def render(self, width: int) -> list[str]:
        label, body_style = _role_styling(self.message.role)
        label_plain = f"  {label}: "
        prefix_width = len(label_plain)
        label_styled = bold(body_style(label))
        prefix_styled = f"  {label_styled}: "
        indent = " " * prefix_width

        content = self.message.text
        if self.show_stream_cursor and self.message.role == "assistant":
            content = (content + " ▌") if content else "▌"

        content_width = max(1, width - prefix_width - 2)
        wrapped = wrap_text_with_ansi(content, content_width) or [""]

        lines: list[str] = []
        for index, line in enumerate(wrapped):
            styled = body_style(line)
            lines.append(prefix_styled + styled if index == 0 else indent + styled)
        return lines


# ── Live header / footer ──────────────────────────────────────────────────

class _LiveText:
    def __init__(self, getter: Callable[[int], str]) -> None:
        self._getter = getter

    def render(self, width: int) -> list[str]:
        return [self._getter(width)]

    def invalidate(self) -> None:
        return None


def _pad_to_width(text: str, width: int) -> str:
    visual = visible_width(text)
    if visual < width:
        return text + " " * (width - visual)
    while text and visible_width(text) > width:
        text = text[:-1]
    return text


def _format_header(width: int) -> str:
    raw = _pad_to_width("  Saber TUI · Streaming Chat Demo", width)
    return HEADER_BG(USER_FG(bold(raw)))


def _format_footer(width: int) -> str:
    hint = "  terminal scrollback for history  ·  ↑↓ history  ·  Enter send  ·  Ctrl+C quit"
    return FOOTER_BG(MUTED(_pad_to_width(hint, width)))


# ── App ───────────────────────────────────────────────────────────────────

@dataclass
class ChatApp:
    tui: TUI
    editor: Editor
    chat_container: Container

    messages: list[Message] = field(default_factory=list)

    # Streaming state
    streaming: bool = False
    _stream_words: list[str] = field(default_factory=list)
    _stream_cursor: int = 0
    _stream_timer: threading.Timer | None = None
    _streaming_component: _MessageComponent | None = None

    on_exit: Callable[[], None] | None = None

    # ── Submission & streaming ────────────────────────────────────────────

    def submit(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        self._append_message(Message("user", text))
        self.editor.set_text("")
        self.editor.add_to_history(text)
        self._start_stream(text)
        self.tui.request_render()

    def _append_message(self, message: Message, show_stream_cursor: bool = False) -> _MessageComponent:
        if self.chat_container.children:
            self.chat_container.add_child(Spacer(1))
        self.messages.append(message)
        component = _MessageComponent(message, show_stream_cursor)
        self.chat_container.add_child(component)
        return component

    def _start_stream(self, prompt: str) -> None:
        self._cancel_stream()
        self._stream_words = (STREAM_TEMPLATE + prompt).split()
        self._stream_cursor = 0
        self.streaming = True
        self._streaming_component = self._append_message(Message("assistant", ""), show_stream_cursor=True)
        self._schedule_stream_tick()

    def _schedule_stream_tick(self) -> None:
        timer = threading.Timer(STREAM_INTERVAL_MS / 1000, self._stream_tick)
        timer.daemon = True
        self._stream_timer = timer
        timer.start()

    def _stream_tick(self) -> None:
        if not self.streaming or self._streaming_component is None:
            return
        self._stream_cursor += 1
        partial = " ".join(self._stream_words[: self._stream_cursor])
        self._streaming_component.message.text = partial
        self.tui.request_render()
        if self._stream_cursor < len(self._stream_words):
            self._schedule_stream_tick()
            return
        self.streaming = False
        self._stream_timer = None
        self._streaming_component.show_stream_cursor = False
        self._streaming_component = None
        self.tui.request_render()

    def _cancel_stream(self) -> None:
        self.streaming = False
        if self._stream_timer is not None:
            self._stream_timer.cancel()
            self._stream_timer = None
        if self._streaming_component is not None:
            self._streaming_component.show_stream_cursor = False
            self._streaming_component = None

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def stop(self) -> None:
        self._cancel_stream()
        if not self.tui.stopped:
            self.tui.stop()
        if self.on_exit is not None:
            self.on_exit()


# ── Build & run ───────────────────────────────────────────────────────────

def _make_global_listener(app: ChatApp) -> Callable[[str], dict[str, Any] | None]:
    def listener(data: str) -> dict[str, Any] | None:
        if matches_key(data, "ctrl+c"):
            app.stop()
            return {"consume": True}
        return None

    return listener


def build_app(
    terminal: Terminal | None = None,
    on_exit: Callable[[], None] | None = None,
) -> ChatApp:
    term = terminal if terminal is not None else ProcessTerminal()
    tui = TUI(term)
    tui.set_show_hardware_cursor(True)
    # Match pi coding-agent: chat history grows in the normal render tree and
    # terminal scrollback owns history, so avoid shrink clears.
    tui.set_clear_on_shrink(False)

    editor = Editor(
        tui,
        theme=EditorTheme(border_color=MUTED, select_list=SelectListTheme()),
    )
    chat_container = Container()
    app = ChatApp(tui=tui, editor=editor, chat_container=chat_container, on_exit=on_exit)
    editor.on_submit = app.submit

    header = _LiveText(_format_header)
    footer = _LiveText(_format_footer)

    tui.add_child(header)
    tui.add_child(chat_container)
    tui.add_child(editor)
    tui.add_child(footer)

    tui.set_focus(editor)
    tui.add_input_listener(_make_global_listener(app))

    app._append_message(
        Message(
            "system",
            "Welcome. Type a message — I'll echo it back, streamed word by word. "
            "Use your terminal scrollback for history. Streaming renders are coalesced by the TUI core.",
        )
    )
    return app


def run_app(app: ChatApp, stop_event: threading.Event) -> None:
    app.tui.start()
    try:
        stop_event.wait()
    finally:
        app.stop()


def main() -> None:
    stop_event = threading.Event()
    app = build_app(on_exit=stop_event.set)
    run_app(app, stop_event)


if __name__ == "__main__":
    main()
