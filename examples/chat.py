"""Streaming chat demo with terminal-style scrollback.

Run with:

    uv run python examples/chat.py

Type a message and Enter to send. The assistant streams an echo response
word-by-word. The transcript behaves like a terminal pty: PgUp / PgDn paginate,
g jumps to the very first line, G follows the latest output again. Ctrl+C to
quit.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from saber_tui import (
    TUI,
    ProcessTerminal,
    Terminal,
    matches_key,
)
from saber_tui.components import Input
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


USER_FG    = fg(125, 211, 252)   # sky
ASST_FG    = fg(134, 239, 172)   # mint
SYSTEM_FG  = fg(251, 191, 36)    # amber
MUTED      = fg(148, 163, 184)   # slate
HEADER_BG  = bg(30,  58, 138)    # indigo-900
FOOTER_BG  = bg(15,  23,  42)    # slate-950


# ── Streaming config ──────────────────────────────────────────────────────

STREAM_INTERVAL_MS = 40
STREAM_TEMPLATE = (
    "Sure — here is what you said, streamed back word by word as if I were a "
    "real LLM. The point of this demo is the streaming UI itself; the "
    "transcript scrolls like a terminal pty, so try PgUp and PgDn while I "
    "talk. Your message was: "
)


# Three lines of chrome around the transcript: header, input, footer.
CHROME_ROWS = 3


# ── Messages ──────────────────────────────────────────────────────────────

@dataclass
class Message:
    role: str    # "user" | "assistant" | "system"
    text: str    # current visible text (grows during streaming)


# ── Transcript component ──────────────────────────────────────────────────

class _Transcript:
    """Renders the scrollback buffer into a fixed-height window.

    Acts like a tiny pty: when scrolled to the bottom (anchor=None), new content
    pushes into view. When the user scrolls up (anchor set to a line index), the
    viewport stays anchored to that line as more content arrives.
    """

    def __init__(self, app: ChatApp) -> None:
        self._app = app

    def invalidate(self) -> None:
        pass

    def render(self, width: int) -> list[str]:
        height = max(1, self._app.tui.terminal.rows - CHROME_ROWS)
        all_lines = self._build_lines(width)
        total = len(all_lines)

        # Publish layout info for the input listener to use when scrolling.
        self._app.transcript_total = total
        self._app.transcript_height = height

        if total <= height:
            self._app.scroll_anchor = None
            return all_lines + [""] * (height - total)

        if self._app.scroll_anchor is None:
            return all_lines[total - height:]

        anchor = max(0, min(self._app.scroll_anchor, total - height))
        self._app.scroll_anchor = anchor
        return all_lines[anchor : anchor + height]

    def _build_lines(self, width: int) -> list[str]:
        if not self._app.messages:
            return [MUTED("  Type a message and press Enter. Ctrl+C to quit.")]

        lines: list[str] = []
        for index, msg in enumerate(self._app.messages):
            label, body_style = _role_styling(msg.role)
            label_plain = f"  {label}: "
            prefix_width = len(label_plain)
            label_styled = bold(body_style(label))
            prefix_styled = f"  {label_styled}: "
            indent = " " * prefix_width

            content = msg.text
            is_last = index == len(self._app.messages) - 1
            if (
                self._app.streaming
                and is_last
                and msg.role == "assistant"
            ):
                content = (content + " ▌") if content else "▌"

            content_width = max(1, width - prefix_width - 2)
            wrapped = wrap_text_with_ansi(content, content_width) or [""]

            for i, line in enumerate(wrapped):
                styled = body_style(line)
                if i == 0:
                    lines.append(prefix_styled + styled)
                else:
                    lines.append(indent + styled)
            lines.append("")  # blank between messages

        while lines and lines[-1] == "":
            lines.pop()
        return lines


def _role_styling(role: str) -> tuple[str, Callable[[str], str]]:
    if role == "user":
        return "You", USER_FG
    if role == "assistant":
        return "Assistant", ASST_FG
    if role == "system":
        return "System", SYSTEM_FG
    return "?", MUTED


# ── Live header / footer ──────────────────────────────────────────────────

class _LiveText:
    def __init__(self, getter: Callable[[int], str]) -> None:
        self._getter = getter

    def render(self, width: int) -> list[str]:
        return [self._getter(width)]

    def invalidate(self) -> None:
        pass


def _pad_to_width(text: str, width: int) -> str:
    visual = visible_width(text)
    if visual < width:
        return text + " " * (width - visual)
    if visual > width:
        # Trim by characters until fits — adequate for plain ASCII headers/footers.
        while text and visible_width(text) > width:
            text = text[:-1]
    return text


def _format_header(app: ChatApp, width: int) -> str:
    title = "  Saber TUI · Streaming Chat Demo"
    if app.scroll_anchor is not None and app.transcript_total > app.transcript_height:
        scrolled = app.transcript_total - (app.scroll_anchor + app.transcript_height)
        info = f"↑ {scrolled} more below  "
    elif app.streaming:
        info = "● streaming  "
    else:
        info = ""
    gap = max(1, width - visible_width(title) - visible_width(info))
    raw = _pad_to_width(title + " " * gap + info, width)
    return HEADER_BG(USER_FG(bold(raw)))


def _format_footer(app: ChatApp, width: int) -> str:
    hint = "  PgUp/PgDn scroll  ·  g top  ·  G bottom  ·  Enter send  ·  Ctrl+C quit"
    return FOOTER_BG(MUTED(_pad_to_width(hint, width)))


# ── App ───────────────────────────────────────────────────────────────────

@dataclass
class ChatApp:
    tui: TUI
    input_box: Input

    messages: list[Message] = field(default_factory=list)

    # None = follow newest output (anchor to bottom). Otherwise an absolute
    # line index in the wrapped transcript that the viewport top is pinned to.
    scroll_anchor: int | None = None

    # Updated by _Transcript.render so scroll keys can compute page steps.
    transcript_total: int = 0
    transcript_height: int = 1

    # Streaming state
    streaming: bool = False
    _stream_words: list[str] = field(default_factory=list)
    _stream_cursor: int = 0
    _stream_timer: threading.Timer | None = None

    on_exit: Callable[[], None] | None = None

    # ── Submission & streaming ────────────────────────────────────────────

    def submit(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        self.messages.append(Message("user", text))
        self.input_box.set_value("")
        self.scroll_anchor = None  # follow new content
        self._start_stream(text)
        self.tui.request_render()

    def _start_stream(self, prompt: str) -> None:
        self._cancel_stream()
        self.messages.append(Message("assistant", ""))
        self._stream_words = (STREAM_TEMPLATE + prompt).split()
        self._stream_cursor = 0
        self.streaming = True
        self._schedule_stream_tick()

    def _schedule_stream_tick(self) -> None:
        timer = threading.Timer(STREAM_INTERVAL_MS / 1000, self._stream_tick)
        timer.daemon = True
        self._stream_timer = timer
        timer.start()

    def _stream_tick(self) -> None:
        if not self.streaming:
            return
        self._stream_cursor += 1
        partial = " ".join(self._stream_words[: self._stream_cursor])
        self.messages[-1].text = partial
        self.tui.request_render()
        if self._stream_cursor < len(self._stream_words):
            self._schedule_stream_tick()
        else:
            self.streaming = False
            self._stream_timer = None
            self.tui.request_render()

    def _cancel_stream(self) -> None:
        self.streaming = False
        if self._stream_timer is not None:
            self._stream_timer.cancel()
            self._stream_timer = None

    # ── Scrolling ─────────────────────────────────────────────────────────

    def page_up(self) -> None:
        height = self.transcript_height
        total = self.transcript_total
        if total <= height:
            return
        new = (
            max(0, total - height - height)
            if self.scroll_anchor is None
            else max(0, self.scroll_anchor - height)
        )
        self.scroll_anchor = new
        self.tui.request_render()

    def page_down(self) -> None:
        height = self.transcript_height
        total = self.transcript_total
        if self.scroll_anchor is None or total <= height:
            return
        new = self.scroll_anchor + height
        if new + height >= total:
            self.scroll_anchor = None
        else:
            self.scroll_anchor = new
        self.tui.request_render()

    def scroll_to_top(self) -> None:
        if self.transcript_total <= self.transcript_height:
            return
        self.scroll_anchor = 0
        self.tui.request_render()

    def scroll_to_bottom(self) -> None:
        self.scroll_anchor = None
        self.tui.request_render()

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
        if matches_key(data, "pageUp"):
            app.page_up()
            return {"consume": True}
        if matches_key(data, "pageDown"):
            app.page_down()
            return {"consume": True}
        # 'g' / 'G' jump to top/bottom only when the composer is empty so they
        # don't swallow letters mid-message.
        if not app.input_box.get_value():
            if data == "g":
                app.scroll_to_top()
                return {"consume": True}
            if data == "G":
                app.scroll_to_bottom()
                return {"consume": True}
        return None

    return listener


def build_app(
    terminal: Terminal | None = None,
    on_exit: Callable[[], None] | None = None,
) -> ChatApp:
    term = terminal if terminal is not None else ProcessTerminal()
    tui = TUI(term)

    input_box = Input()
    app = ChatApp(tui=tui, input_box=input_box, on_exit=on_exit)
    input_box.on_submit = app.submit

    transcript = _Transcript(app)
    header = _LiveText(lambda w: _format_header(app, w))
    footer = _LiveText(lambda w: _format_footer(app, w))

    tui.add_child(header)
    tui.add_child(transcript)
    tui.add_child(input_box)
    tui.add_child(footer)

    tui.set_focus(input_box)
    tui.add_input_listener(_make_global_listener(app))

    app.messages.append(Message(
        "system",
        "Welcome. Type a message — I'll echo it back, streamed word by word. "
        "Use PgUp/PgDn (or g/G) to scroll the transcript like a terminal.",
    ))
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
