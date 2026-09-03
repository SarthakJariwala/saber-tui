"""Saber TUI Component Gallery — a paged tour of every public component.

Run with:

    uv run python examples/showcase.py

Keys (always available):
  Tab / Shift+Tab    Move between pages
  Ctrl+P             Command palette overlay
  Ctrl+C             Quit

Per-page keys are listed in the footer.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from saber_tui import (
    TUI,
    Container,
    OverlayHandle,
    ProcessTerminal,
    Terminal,
    matches_key,
)
from saber_tui.autocomplete import CombinedAutocompleteProvider, SlashCommand
from saber_tui.components import (
    Box,
    CancellableLoader,
    DefaultTextStyle,
    Editor,
    EditorTheme,
    Loader,
    Markdown,
    MarkdownOptions,
    MarkdownTheme,
    SelectItem,
    SelectList,
    SettingItem,
    SettingsList,
    SettingsListOptions,
    SettingsListTheme,
    Spacer,
    Text,
    TruncatedText,
)
from saber_tui.components.select_list import SelectListLayoutOptions, SelectListTheme
from saber_tui.utils import truncate_to_width, visible_width

# ── ANSI helpers ───────────────────────────────────────────────────────────


def fg(r: int, g: int, b: int) -> Callable[[str], str]:
    code = f"\x1b[38;2;{r};{g};{b}m"
    return lambda text: f"{code}{text}\x1b[39m"


def bg(r: int, g: int, b: int) -> Callable[[str], str]:
    code = f"\x1b[48;2;{r};{g};{b}m"
    return lambda text: f"{code}{text}\x1b[49m"


def bold(text: str) -> str:
    return f"\x1b[1m{text}\x1b[22m"


PALETTE: dict[str, Callable[[str], str]] = {
    "brand": fg(196, 181, 253),  # lavender
    "accent": fg(103, 232, 249),  # cyan
    "text": fg(226, 232, 240),  # slate-200
    "muted": fg(148, 163, 184),  # slate
    "good": fg(110, 231, 183),  # mint
    "warn": fg(253, 224, 71),  # amber
    "danger": fg(251, 113, 133),  # rose
    "panel": bg(15, 23, 42),  # slate-950
    "panel_alt": bg(30, 41, 59),  # slate panel
    "chrome_bg": bg(17, 24, 39),  # gray-900
    "key_bg": bg(51, 65, 85),  # slate-700
}


# ── Pages ──────────────────────────────────────────────────────────────────

PAGE_TITLES = [
    "Welcome",
    "Text & TruncatedText",
    "Box & Spacer",
    "Editor — multiline editor",
    "SelectList — filter & pick",
    "SettingsList — toggles & search",
    "Loader & CancellableLoader",
    "Markdown — streaming renderer",
    "Overlays — modal & palette",
]

PAGE_HINTS: list[list[tuple[str, str]]] = [
    [("Tab", "next"), ("Ctrl+P", "menu"), ("Ctrl+C", "quit")],
    [("Tab", "next"), ("Shift+Tab", "back"), ("Ctrl+P", "menu")],
    [("Tab", "next"), ("Shift+Tab", "back"), ("Ctrl+P", "menu")],
    [("Enter", "submit"), ("↑↓", "history"), ("Ctrl+Z", "undo"), ("/", "commands")],
    [("↑↓", "move"), ("type", "filter"), ("Enter", "pick")],
    [("↑↓", "move"), ("type", "search"), ("Enter", "change"), ("Esc", "cancel")],
    [("Space", "pause"), ("Ctrl+G", "cancel"), ("Tab", "next")],
    [("R", "replay"), ("Tab", "next"), ("Shift+Tab", "back")],
    [("M", "modal"), ("Ctrl+P", "menu"), ("Esc", "close")],
]


# ── Live components ────────────────────────────────────────────────────────


class _LiveText:
    """A Text-like component that recomputes its content on every render."""

    def __init__(self, getter: Callable[[int], str]) -> None:
        self._getter = getter

    def render(self, width: int) -> list[str]:
        return [self._getter(width)]

    def invalidate(self) -> None:
        pass


class _Hidden:
    """Zero-height component used to swallow focus on pages without widgets."""

    focused: bool = False

    def render(self, width: int) -> list[str]:
        return []

    def invalidate(self) -> None:
        pass

    def handle_input(self, data: str) -> None:  # pragma: no cover - intentional no-op
        pass


class _FilterableSelectList(SelectList):
    """SelectList with a small search row for the interactive examples."""

    def __init__(
        self,
        items: list[SelectItem],
        max_visible: int = 5,
        theme: SelectListTheme | None = None,
        layout: SelectListLayoutOptions | None = None,
    ) -> None:
        super().__init__(items, max_visible=max_visible, theme=theme, layout=layout)
        self._query = ""

    def render(self, width: int) -> list[str]:
        query = PALETTE["text"](self._query) if self._query else PALETTE["muted"]("Type to filter…")
        search = truncate_to_width(f"{PALETTE['brand'](bold('FILTER'))}  {query}", width, "")
        return [search, "", *super().render(width)]

    def handle_input(self, data: str) -> None:
        if matches_key(data, "backspace"):
            self._query = self._query[:-1]
            self._filter_items()
            return
        if data and all(character.isprintable() for character in data):
            self._query += data
            self._filter_items()
            return
        super().handle_input(data)

    def _filter_items(self) -> None:
        query = self._query.casefold()
        self.filtered_items = [
            item for item in self.items if query in item.value.casefold() or query in item.label.casefold()
        ]
        self.selected_index = 0
        self._notify_selection_change()


# ── App state ──────────────────────────────────────────────────────────────


@dataclass
class ShowcaseApp:
    tui: TUI
    body: Container

    # Page state
    page_index: int = 0
    transcript: list[str] = field(default_factory=list)

    # Active widgets per page (tracked so we can tear them down)
    editor: Editor | None = None
    select_list: SelectList | None = None
    settings_list: SettingsList | None = None
    loader: Loader | None = None
    cancellable: CancellableLoader | None = None
    markdown: Markdown | None = None
    markdown_timer: threading.Timer | None = None

    # Overlays
    palette_handle: OverlayHandle | None = None
    modal_handle: OverlayHandle | None = None

    # Misc
    hidden_focus: _Hidden = field(default_factory=_Hidden)

    # exit hook
    on_exit: Callable[[], None] | None = None

    def stop(self) -> None:
        self._teardown_page()
        if self.palette_handle is not None:
            self.palette_handle.hide()
            self.palette_handle = None
        if self.modal_handle is not None:
            self.modal_handle.hide()
            self.modal_handle = None
        if not self.tui.stopped:
            self.tui.stop()
        if self.on_exit is not None:
            self.on_exit()

    def _teardown_page(self) -> None:
        if self.loader is not None:
            self.loader.stop()
        if self.cancellable is not None:
            self.cancellable.dispose()
        if self.markdown_timer is not None:
            self.markdown_timer.cancel()
        self.editor = None
        self.select_list = None
        self.settings_list = None
        self.loader = None
        self.cancellable = None
        self.markdown = None
        self.markdown_timer = None


# ── Frame builders (header/footer) ─────────────────────────────────────────


def _fit_line(text: str, width: int) -> str:
    fitted = truncate_to_width(text, max(0, width), "")
    return fitted + " " * max(0, width - visible_width(fitted))


def _keycap(key: str) -> str:
    return PALETTE["key_bg"](PALETTE["text"](bold(f" {key} ")))


def _format_header(app: ShowcaseApp, width: int) -> str:
    brand = PALETTE["brand"](bold("◆ SABER"))
    context = PALETTE["muted"]("  /  COMPONENT GALLERY")
    page = PALETTE["text"](f"[{app.page_index + 1}/{len(PAGE_TITLES)}]  {PAGE_TITLES[app.page_index]}")
    left = f"  {brand}{context}"
    gap = " " * max(2, width - visible_width(left) - visible_width(page) - 2)
    return PALETTE["chrome_bg"](_fit_line(f"{left}{gap}{page}  ", width))


def _format_footer(app: ShowcaseApp, width: int) -> str:
    actions = [f"{_keycap(key)} {PALETTE['muted'](label)}" for key, label in PAGE_HINTS[app.page_index]]
    hint = "   ".join(actions)
    return _fit_line(f"  {hint}", width)


# ── Page builders ──────────────────────────────────────────────────────────


def _heading(text: str) -> Text:
    return Text(
        PALETTE["brand"]("◆ ") + PALETTE["text"](bold(text)),
        padding_x=1,
        padding_y=0,
    )


def _para(text: str) -> Text:
    return Text(PALETTE["muted"](text), padding_x=1, padding_y=0)


def _select_list_theme() -> SelectListTheme:
    return SelectListTheme(
        selected_prefix=lambda _: PALETTE["brand"]("› "),
        selected_text=lambda text: PALETTE["accent"](bold(text)),
        description=PALETTE["muted"],
        scroll_info=PALETTE["muted"],
        no_match=PALETTE["danger"],
    )


def _settings_list_theme() -> SettingsListTheme:
    return SettingsListTheme(
        label=lambda text, selected: PALETTE["text"](bold(text)) if selected else PALETTE["text"](text),
        value=lambda text, selected: PALETTE["accent"](text) if selected else PALETTE["muted"](text),
        description=PALETTE["muted"],
        cursor=PALETTE["brand"]("› "),
        hint=PALETTE["muted"],
    )


def build_page_welcome(app: ShowcaseApp) -> None:
    hero = Box(padding_x=3, padding_y=1, bg_fn=PALETTE["panel"])
    hero.add_child(
        Text(
            PALETTE["brand"](bold("SABER TUI")) + PALETTE["muted"]("  /  PYTHON"),
            padding_x=0,
            padding_y=0,
        )
    )
    hero.add_child(Spacer(1))
    hero.add_child(
        Text(
            PALETTE["text"](bold("Build focused terminal interfaces.")),
            padding_x=0,
            padding_y=0,
        )
    )
    hero.add_child(
        Text(
            PALETTE["muted"](
                "Composable components, overlays, focus management, and smooth streaming output in a small Python API."
            ),
            padding_x=0,
            padding_y=0,
        )
    )
    hero.add_child(
        Text(
            PALETTE["accent"](bold("09 guided pages")) + PALETTE["muted"]("  ·  live controls  ·  zero boilerplate"),
            padding_x=0,
            padding_y=0,
        )
    )
    app.body.add_child(hero)
    app.body.add_child(Spacer(1))
    app.body.add_child(_heading("Start here"))
    app.body.add_child(
        Text(
            f"{_keycap('Tab')}  {PALETTE['text']('Browse the component gallery')}",
            padding_x=2,
            padding_y=0,
        )
    )
    app.body.add_child(
        Text(
            f"{_keycap('Ctrl+P')}  {PALETTE['text']('Jump straight to any page')}",
            padding_x=2,
            padding_y=0,
        )
    )
    app.body.add_child(
        Text(
            f"{_keycap('Ctrl+C')}  {PALETTE['text']('Leave the gallery')}",
            padding_x=2,
            padding_y=0,
        )
    )
    app.tui.set_focus(app.hidden_focus)


def build_page_text(app: ShowcaseApp) -> None:
    long_para = (
        "Text wraps ANSI-styled content to the available width while keeping words and colors intact. "
        "Resize the terminal and this paragraph reflows without any layout bookkeeping."
    )
    single_line = (
        "TruncatedText keeps status rows compact when labels, paths, or command output run beyond the available width."
    )

    wrap_box = Box(padding_x=2, padding_y=1, bg_fn=PALETTE["panel"])
    wrap_box.add_child(
        Text(
            PALETTE["brand"](bold("TEXT")) + PALETTE["muted"]("  /  responsive wrapping"),
            padding_x=0,
            padding_y=0,
        )
    )
    wrap_box.add_child(Spacer(1))
    wrap_box.add_child(Text(PALETTE["text"](long_para), padding_x=0, padding_y=0))

    trunc_box = Box(padding_x=2, padding_y=1, bg_fn=PALETTE["panel_alt"])
    trunc_box.add_child(
        Text(
            PALETTE["accent"](bold("TRUNCATED TEXT")) + PALETTE["muted"]("  /  one clean line"),
            padding_x=0,
            padding_y=0,
        )
    )
    trunc_box.add_child(Spacer(1))
    trunc_box.add_child(TruncatedText(PALETTE["text"](single_line), padding_x=0, padding_y=0))

    app.body.add_child(_heading("Text that respects the terminal"))
    app.body.add_child(Spacer(1))
    app.body.add_child(wrap_box)
    app.body.add_child(Spacer(1))
    app.body.add_child(trunc_box)
    app.tui.set_focus(app.hidden_focus)


def build_page_box(app: ShowcaseApp) -> None:
    inner = Box(padding_x=2, padding_y=1, bg_fn=PALETTE["panel_alt"])
    inner.add_child(
        Text(PALETTE["accent"](bold("INNER BOX")) + PALETTE["muted"]("  padding_x=2"), padding_x=0, padding_y=0)
    )
    inner.add_child(Text(PALETTE["text"]("Boxes compose like any other component."), padding_x=0, padding_y=0))

    outer = Box(padding_x=2, padding_y=1, bg_fn=PALETTE["panel"])
    outer.add_child(
        Text(PALETTE["brand"](bold("OUTER BOX")) + PALETTE["muted"]("  padding_y=1"), padding_x=0, padding_y=0)
    )
    outer.add_child(Spacer(1))
    outer.add_child(inner)
    outer.add_child(Spacer(2))
    outer.add_child(Text(PALETTE["muted"]("↑  Spacer(2) creates this breathing room."), padding_x=0, padding_y=0))

    app.body.add_child(_heading("Layout from two small primitives"))
    app.body.add_child(_para("Box owns padding and background. Spacer owns the gap between components."))
    app.body.add_child(Spacer(1))
    app.body.add_child(outer)
    app.tui.set_focus(app.hidden_focus)


def build_page_input(app: ShowcaseApp) -> None:
    editor = Editor(
        app.tui,
        theme=EditorTheme(border_color=PALETTE["accent"], select_list=_select_list_theme()),
    )
    editor.set_autocomplete_provider(
        CombinedAutocompleteProvider(
            commands=[
                SlashCommand("/help", description="Show available commands"),
                SlashCommand("/clear", description="Clear the submission history"),
                SlashCommand("/quit", description="Stop the TUI and exit"),
            ]
        )
    )
    transcript_text = Text("", padding_x=0, padding_y=0)

    def update_transcript() -> None:
        if not app.transcript:
            transcript_text.set_text(PALETTE["muted"]("No submissions yet. Press Enter to add one."))
        else:
            recent = app.transcript[-5:]
            lines = "\n".join(f"●  {line}" for line in recent)
            transcript_text.set_text(PALETTE["good"](lines))

    def on_submit(value: str) -> None:
        if value:
            app.transcript.append(value)
            editor.add_to_history(value)
            editor.set_text("")
            update_transcript()
            app.tui.request_render()

    editor.on_submit = on_submit
    app.editor = editor

    input_box = Box(padding_x=2, padding_y=1, bg_fn=PALETTE["panel"])
    input_box.add_child(
        Text(
            PALETTE["brand"](bold("MESSAGE")) + PALETTE["muted"]("  /  multiline editor"),
            padding_x=0,
            padding_y=0,
        )
    )
    input_box.add_child(Spacer(1))
    input_box.add_child(editor)
    input_box.add_child(Spacer(1))
    input_box.add_child(
        Text(
            PALETTE["muted"]("Try /help for autocomplete. History, undo, kill, and yank all work here."),
            padding_x=0,
            padding_y=0,
        )
    )

    transcript_box = Box(padding_x=2, padding_y=1, bg_fn=PALETTE["panel_alt"])
    transcript_box.add_child(Text(PALETTE["accent"](bold("RECENT SUBMISSIONS")), padding_x=0, padding_y=0))
    transcript_box.add_child(Spacer(1))
    transcript_box.add_child(transcript_text)

    app.body.add_child(_heading("A composer that remembers"))
    app.body.add_child(_para("Type, submit, recall history, and discover slash commands without leaving the editor."))
    app.body.add_child(Spacer(1))
    app.body.add_child(input_box)
    app.body.add_child(Spacer(1))
    app.body.add_child(transcript_box)
    update_transcript()
    app.tui.set_focus(editor)


def build_page_select(app: ShowcaseApp) -> None:
    items = [
        SelectItem("python", "Python", "Readable, batteries included"),
        SelectItem("rust", "Rust", "Memory-safe systems language"),
        SelectItem("go", "Go", "Simple, fast, concurrent"),
        SelectItem("typescript", "TypeScript", "Typed JavaScript"),
        SelectItem("zig", "Zig", "Manual memory, no hidden control flow"),
        SelectItem("ocaml", "OCaml", "ML family, strong inference"),
        SelectItem("haskell", "Haskell", "Lazy, pure, type-rich"),
        SelectItem("elixir", "Elixir", "BEAM, actor model"),
        SelectItem("julia", "Julia", "Numerics & multiple dispatch"),
    ]
    select = _FilterableSelectList(items, max_visible=6, theme=_select_list_theme())
    result_text = Text(PALETTE["muted"]("Browsing: Python"), padding_x=0, padding_y=0)

    def on_select(item: SelectItem) -> None:
        result_text.set_text(PALETTE["good"](f"Selected: {item.label}  ·  {item.description or ''}"))
        app.tui.request_render()

    def on_change(item: SelectItem) -> None:
        result_text.set_text(PALETTE["muted"](f"Browsing: {item.label}"))
        app.tui.request_render()

    select.on_select = on_select
    select.on_selection_change = on_change
    app.select_list = select

    list_box = Box(padding_x=2, padding_y=1, bg_fn=PALETTE["panel"])
    list_box.add_child(select)
    list_box.add_child(Spacer(1))
    list_box.add_child(result_text)

    app.body.add_child(_heading("Pick quickly, even from a long list"))
    app.body.add_child(_para("Move with the arrow keys or type a language name to filter."))
    app.body.add_child(Spacer(1))
    app.body.add_child(list_box)
    app.tui.set_focus(select)


def build_page_settings(app: ShowcaseApp) -> None:
    status = Text(PALETTE["muted"]("Change a value or search by typing."), padding_x=0, padding_y=0)
    model_values = [
        SelectItem("gpt-4.1", "gpt-4.1", "Balanced default"),
        SelectItem("gpt-5", "gpt-5", "More capable"),
        SelectItem("local", "local", "Local provider"),
    ]

    def model_submenu(current_value: str, done: Callable[[str | None], None]) -> SelectList:
        selector = SelectList(model_values, max_visible=4, theme=_select_list_theme())
        current_index = next((index for index, item in enumerate(model_values) if item.value == current_value), 0)
        selector.set_selected_index(current_index)
        selector.on_select = lambda item: done(item.value)
        selector.on_cancel = lambda: done(None)
        return selector

    items = [
        SettingItem(
            id="theme",
            label="Theme",
            description="Cycle through color modes with Enter or Space.",
            current_value="dark",
            values=["dark", "light", "system"],
        ),
        SettingItem(
            id="autocomplete",
            label="Autocomplete",
            description="Toggle command and path suggestions in the editor.",
            current_value="enabled",
            values=["enabled", "disabled"],
        ),
        SettingItem(
            id="model",
            label="Model",
            description="Open a SelectList submenu for larger option sets.",
            current_value="gpt-4.1",
            submenu=model_submenu,
        ),
        SettingItem(
            id="streaming",
            label="Streaming",
            description="Render partial output as it arrives.",
            current_value="on",
            values=["on", "off"],
        ),
    ]

    def on_change(id: str, new_value: str) -> None:
        status.set_text(PALETTE["good"](f"Updated  ·  {id} = {new_value}"))
        app.tui.request_render()

    def on_cancel() -> None:
        status.set_text(PALETTE["warn"]("Cancelled. No value changed."))
        app.tui.request_render()

    settings = SettingsList(
        items,
        max_visible=4,
        theme=_settings_list_theme(),
        on_change=on_change,
        on_cancel=on_cancel,
        options=SettingsListOptions(enable_search=True),
    )
    app.settings_list = settings

    settings_box = Box(padding_x=2, padding_y=1, bg_fn=PALETTE["panel"])
    settings_box.add_child(settings)
    settings_box.add_child(Spacer(1))
    settings_box.add_child(status)

    app.body.add_child(_heading("Settings that explain themselves"))
    app.body.add_child(_para("Search, cycle small choices, or open a submenu for larger option sets."))
    app.body.add_child(Spacer(1))
    app.body.add_child(settings_box)
    app.tui.set_focus(settings)


def build_page_loader(app: ShowcaseApp) -> None:
    loader = Loader(
        app.tui,
        spinner_style=PALETTE["accent"],
        text_style=PALETTE["muted"],
        text="Top loader running — press Space to pause",
    )
    cancellable = CancellableLoader(
        app.tui,
        spinner_style=PALETTE["warn"],
        text_style=PALETTE["muted"],
        text="Cancellable loader — press Ctrl+G (or Esc) to abort",
    )
    status = Text(PALETTE["muted"]("Both tasks are active."), padding_x=0, padding_y=0)

    def on_cancel() -> None:
        status.set_text(PALETTE["danger"]("Cancellable task aborted."))
        cancellable.set_message("Aborted.")
        cancellable.dispose()
        app.tui.request_render()

    cancellable.on_cancel = on_cancel
    app.loader = loader
    app.cancellable = cancellable

    loader_box = Box(padding_x=2, padding_y=1, bg_fn=PALETTE["panel"])
    loader_box.add_child(Text(PALETTE["brand"](bold("BACKGROUND TASK")), padding_x=0, padding_y=0))
    loader_box.add_child(Spacer(1))
    loader_box.add_child(loader)

    cancellable_box = Box(padding_x=2, padding_y=1, bg_fn=PALETTE["panel_alt"])
    cancellable_box.add_child(Text(PALETTE["accent"](bold("CANCELLABLE TASK")), padding_x=0, padding_y=0))
    cancellable_box.add_child(Spacer(1))
    cancellable_box.add_child(cancellable)
    cancellable_box.add_child(Spacer(1))
    cancellable_box.add_child(status)

    app.body.add_child(_heading("Motion with a clear escape hatch"))
    app.body.add_child(_para("Pause one task or cancel the other. Each loader owns its lifecycle."))
    app.body.add_child(Spacer(1))
    app.body.add_child(loader_box)
    app.body.add_child(Spacer(1))
    app.body.add_child(cancellable_box)

    loader.start()
    cancellable.start()
    app.tui.set_focus(cancellable)


MARKDOWN_DEMO = """# Markdown streams without flicker

Ordinary text supports **bold**, *italic*, ~~strikethrough~~, `inline code`, and [links](https://example.com).

> Blockquotes keep their border and styling when they wrap.

- Nested lists and tasks
  - [x] ANSI-aware wrapping
  - [ ] Ship something delightful

```python
markdown.append_text(chunk)
tui.request_render()
```

| Feature | Status |
| --- | --- |
| Tables | live |
| Code fences | stable |
"""


def _markdown_theme() -> MarkdownTheme:
    return MarkdownTheme(
        heading=lambda text: PALETTE["accent"](bold(text)),
        link=PALETTE["accent"],
        link_url=PALETTE["muted"],
        code=PALETTE["warn"],
        code_block=PALETTE["good"],
        code_block_border=PALETTE["muted"],
        quote=PALETTE["muted"],
        quote_border=PALETTE["accent"],
        hr=PALETTE["muted"],
        list_bullet=PALETTE["accent"],
        bold=bold,
        italic=lambda text: f"\x1b[3m{text}\x1b[23m",
        strikethrough=lambda text: f"\x1b[9m{text}\x1b[29m",
        underline=lambda text: f"\x1b[4m{text}\x1b[24m",
    )


def start_markdown_stream(app: ShowcaseApp) -> None:
    markdown = app.markdown
    if markdown is None:
        return
    if app.markdown_timer is not None:
        app.markdown_timer.cancel()
    markdown.set_text("")
    cursor = 0

    def tick() -> None:
        nonlocal cursor
        if app.markdown is not markdown:
            return
        cursor = min(len(MARKDOWN_DEMO), cursor + 8)
        markdown.set_text(MARKDOWN_DEMO[:cursor])
        app.tui.request_render()
        if cursor < len(MARKDOWN_DEMO):
            timer = threading.Timer(0.035, tick)
            timer.daemon = True
            app.markdown_timer = timer
            timer.start()
        else:
            app.markdown_timer = None

    tick()


def build_page_markdown(app: ShowcaseApp) -> None:
    markdown = Markdown(
        padding_x=0,
        theme=_markdown_theme(),
        default_text_style=DefaultTextStyle(color=PALETTE["text"]),
        options=MarkdownOptions(hyperlinks=False),
    )
    app.markdown = markdown
    markdown_box = Box(padding_x=2, padding_y=0, bg_fn=PALETTE["panel"])
    markdown_box.add_child(markdown)
    app.body.add_child(markdown_box)
    app.tui.set_focus(app.hidden_focus)
    start_markdown_stream(app)


def build_page_overlays(app: ShowcaseApp) -> None:
    modal_card = Box(padding_x=2, padding_y=1, bg_fn=PALETTE["panel"])
    modal_card.add_child(
        Text(
            f"{PALETTE['accent'](bold('M'))}  {PALETTE['text'](bold('Centered modal'))}",
            padding_x=0,
            padding_y=0,
        )
    )
    modal_card.add_child(
        Text(PALETTE["muted"]("Capture focus for a decision, then return it to the page."), padding_x=0, padding_y=0)
    )

    palette_card = Box(padding_x=2, padding_y=1, bg_fn=PALETTE["panel_alt"])
    palette_card.add_child(
        Text(
            f"{PALETTE['accent'](bold('CTRL+P'))}  {PALETTE['text'](bold('Command menu'))}",
            padding_x=0,
            padding_y=0,
        )
    )
    palette_card.add_child(
        Text(
            PALETTE["muted"]("Filter actions and jump anywhere without leaving the keyboard."),
            padding_x=0,
            padding_y=0,
        )
    )

    app.body.add_child(_heading("Add a layer, not a new screen"))
    app.body.add_child(_para("Overlays anchor to the viewport and restore focus when they close."))
    app.body.add_child(Spacer(1))
    app.body.add_child(modal_card)
    app.body.add_child(Spacer(1))
    app.body.add_child(palette_card)
    app.tui.set_focus(app.hidden_focus)


PAGE_BUILDERS: list[Callable[[ShowcaseApp], None]] = [
    build_page_welcome,
    build_page_text,
    build_page_box,
    build_page_input,
    build_page_select,
    build_page_settings,
    build_page_loader,
    build_page_markdown,
    build_page_overlays,
]


# ── Navigation ─────────────────────────────────────────────────────────────


def go_to_page(app: ShowcaseApp, index: int) -> None:
    if app.modal_handle is not None:
        app.modal_handle.hide()
        app.modal_handle = None
    if app.palette_handle is not None:
        app.palette_handle.hide()
        app.palette_handle = None

    app._teardown_page()
    app.body.clear()
    app.body.invalidate()

    app.page_index = max(0, min(index, len(PAGE_BUILDERS) - 1))
    PAGE_BUILDERS[app.page_index](app)
    app.tui.request_render(force=True)


# ── Modal & command palette ────────────────────────────────────────────────


def _make_modal_body() -> Box:
    box = Box(padding_x=3, padding_y=1, bg_fn=PALETTE["panel"])
    box.add_child(
        Text(
            PALETTE["brand"]("◆ ") + PALETTE["text"](bold("Hello from a modal!")),
            padding_x=0,
            padding_y=0,
        )
    )
    box.add_child(Spacer(1))
    box.add_child(
        Text(
            PALETTE["muted"]("This Box is anchored to the center of the terminal and owns focus while it is open."),
            padding_x=0,
            padding_y=0,
        )
    )
    box.add_child(Spacer(1))
    box.add_child(
        Text(
            f"{PALETTE['accent'](bold('ESC'))}  {PALETTE['muted']('Close and return to the gallery')}",
            padding_x=0,
            padding_y=0,
        )
    )
    return box


def show_modal(app: ShowcaseApp) -> None:
    if app.modal_handle is not None:
        return
    body = _make_modal_body()
    handle = app.tui.show_overlay(
        body,
        {
            "anchor": "center",
            "width": "62%",
            "minWidth": 44,
            "maxHeight": 10,
        },
    )
    app.modal_handle = handle


def close_modal(app: ShowcaseApp) -> None:
    if app.modal_handle is not None:
        app.modal_handle.hide()
        app.modal_handle = None
        app.tui.request_render()


def _palette_actions(app: ShowcaseApp) -> list[tuple[SelectItem, Callable[[], None]]]:
    actions: list[tuple[SelectItem, Callable[[], None]]] = []
    for index, title in enumerate(PAGE_TITLES):
        page_idx = index
        actions.append(
            (
                SelectItem(f"goto-{index}", f"Go to: {title}", f"Page {index + 1}"),
                lambda i=page_idx: go_to_page(app, i),
            )
        )
    actions.append(
        (
            SelectItem("modal", "Show modal", "Open the centered modal overlay"),
            lambda: show_modal(app),
        )
    )
    actions.append(
        (
            SelectItem("quit", "Quit", "Stop the TUI and exit"),
            lambda: app.stop(),
        )
    )
    return actions


def open_palette(app: ShowcaseApp) -> None:
    if app.palette_handle is not None:
        return

    actions = _palette_actions(app)
    items = [item for item, _ in actions]
    by_value = {item.value: cb for item, cb in actions}

    palette = _FilterableSelectList(
        items,
        max_visible=8,
        theme=_select_list_theme(),
        layout=SelectListLayoutOptions(min_primary_column_width=32, max_primary_column_width=46),
    )

    box = Box(padding_x=2, padding_y=1, bg_fn=PALETTE["panel"])
    title = Text(
        PALETTE["brand"]("◆ ") + PALETTE["text"](bold("COMMAND MENU")),
        padding_x=0,
        padding_y=0,
    )
    subtitle = Text(PALETTE["muted"]("Jump to a page or run an action."), padding_x=0, padding_y=0)
    hint = Text(PALETTE["muted"]("↑↓ move  ·  Enter run  ·  Esc cancel"), padding_x=0, padding_y=0)
    box.add_child(title)
    box.add_child(subtitle)
    box.add_child(Spacer(1))
    box.add_child(palette)
    box.add_child(Spacer(1))
    box.add_child(hint)

    handle = app.tui.show_overlay(
        box,
        {
            "anchor": "center",
            "width": "72%",
            "minWidth": 56,
            "maxHeight": 18,
        },
    )
    # Overlays receive focus on the *root* component (the Box), but the Box
    # has no handle_input. Refocus onto the SelectList so arrow/Enter/Esc work.
    app.tui.set_focus(palette)
    app.palette_handle = handle

    def close() -> None:
        if app.palette_handle is not None:
            app.palette_handle.hide()
            app.palette_handle = None
            app.tui.request_render()

    def on_select(item: SelectItem) -> None:
        cb = by_value.get(item.value)
        close()
        if cb is not None:
            cb()

    palette.on_select = on_select
    palette.on_cancel = close


# ── Global key listener ────────────────────────────────────────────────────


def _on_input_page(app: ShowcaseApp) -> bool:
    return app.page_index == 3 and app.editor is not None


def _is_cancel_key(data: str) -> bool:
    # Ctrl+G remains a useful terminal-friendly fallback alongside Esc.
    return matches_key(data, "ctrl+g") or matches_key(data, "escape")


def make_global_listener(app: ShowcaseApp) -> Callable[[str], dict[str, Any] | None]:
    def listener(data: str) -> dict[str, Any] | None:
        if matches_key(data, "ctrl+c"):
            app.stop()
            return {"consume": True}

        if app.modal_handle is not None and _is_cancel_key(data):
            close_modal(app)
            return {"consume": True}

        if matches_key(data, "ctrl+p"):
            open_palette(app)
            return {"consume": True}

        if app.palette_handle is not None:
            # Translate Ctrl+G into the Esc the SelectList already understands.
            if matches_key(data, "ctrl+g"):
                return {"data": "\x1b"}
            return None

        if matches_key(data, "shift+tab"):
            go_to_page(app, app.page_index - 1)
            return {"consume": True}
        if matches_key(data, "tab"):
            go_to_page(app, app.page_index + 1)
            return {"consume": True}

        # Page-specific shortcuts that we only want when no Editor is focused.
        if not _on_input_page(app):
            if app.page_index == 6:
                if data == " ":
                    if app.loader is not None:
                        if app.loader._timer_active:
                            app.loader.stop()
                            app.loader.set_message("Top loader paused — press Space to resume")
                        else:
                            app.loader.set_message("Top loader running — press Space to pause")
                            app.loader.start()
                    return {"consume": True}
                if matches_key(data, "ctrl+g"):
                    if app.cancellable is not None and not app.cancellable.aborted:
                        app.cancellable.aborted = True
                        if app.cancellable.on_cancel is not None:
                            app.cancellable.on_cancel()
                    return {"consume": True}
            if app.page_index == 7 and data == "r":
                start_markdown_stream(app)
                return {"consume": True}
            if app.page_index == 8 and data == "m":
                show_modal(app)
                return {"consume": True}
            if data == "q":
                app.stop()
                return {"consume": True}

        return None

    return listener


# ── Build & run ────────────────────────────────────────────────────────────


def build_app(terminal: Terminal | None = None, on_exit: Callable[[], None] | None = None) -> ShowcaseApp:
    term = terminal if terminal is not None else ProcessTerminal()
    tui = TUI(term)
    tui.set_show_hardware_cursor(True)
    # Pages vary substantially in height; clear stale rows when the rendered
    # working area shrinks during page changes.
    tui.set_clear_on_shrink(True)
    body = Container()

    app = ShowcaseApp(tui=tui, body=body, on_exit=on_exit)

    header_live = _LiveText(lambda width: _format_header(app, width))
    footer_live = _LiveText(lambda width: _format_footer(app, width))

    tui.add_child(header_live)
    tui.add_child(Spacer(1))
    tui.add_child(body)
    tui.add_child(Spacer(1))
    tui.add_child(footer_live)

    tui.add_input_listener(make_global_listener(app))
    PAGE_BUILDERS[0](app)
    return app


def run_app(app: ShowcaseApp, stop_event: threading.Event) -> None:
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
