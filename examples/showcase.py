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
    Editor,
    EditorTheme,
    Loader,
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
from saber_tui.components.select_list import SelectListTheme

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
    "accent": fg(125, 211, 252),  # sky
    "muted": fg(148, 163, 184),  # slate
    "good": fg(134, 239, 172),  # mint
    "warn": fg(251, 191, 36),  # amber
    "danger": fg(248, 113, 113),  # rose
    "panel": bg(17, 24, 39),  # near-black panel
    "panel_alt": bg(30, 41, 59),  # slate panel
    "header_bg": bg(30, 58, 138),  # indigo
    "footer_bg": bg(15, 23, 42),  # slate-950
}


# ── Pages ──────────────────────────────────────────────────────────────────

PAGE_TITLES = [
    "Welcome",
    "Text & TruncatedText",
    "Box & Spacer",
    "Editor — multiline editor",
    "SelectList — filter & pick",
    "SettingsList - toggles & search",
    "Loader & CancellableLoader",
    "Overlays — modal & palette",
]

PAGE_HINTS = [
    "Tab next  ·  Ctrl+P palette  ·  Ctrl+C quit",
    "Tab next  ·  Shift+Tab back  ·  Ctrl+P palette",
    "Tab next  ·  Shift+Tab back  ·  Ctrl+P palette",
    "Enter submit  ·  ↑↓ history  ·  Ctrl+Z undo  ·  type / for autocomplete",
    "↑↓ move  ·  type to filter  ·  Enter pick",
    "↑↓ move  ·  type search  ·  Enter/Space change  ·  Esc cancel",
    "Space toggle top loader  ·  Ctrl+G or Esc cancel lower loader",
    "m show modal  ·  Ctrl+G or Esc close  ·  Ctrl+P palette",
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
        self.editor = None
        self.select_list = None
        self.settings_list = None
        self.loader = None
        self.cancellable = None


# ── Frame builders (header/footer) ─────────────────────────────────────────


def _format_header(app: ShowcaseApp, width: int) -> str:
    title = "Saber TUI · Component Gallery"
    page = f"[{app.page_index + 1}/{len(PAGE_TITLES)}] {PAGE_TITLES[app.page_index]}"
    gap = max(1, width - len(title) - len(page) - 4)
    raw = f"  {title}{' ' * gap}{page}  "
    return PALETTE["header_bg"](PALETTE["accent"](bold(raw[:width].ljust(width))))


def _format_footer(app: ShowcaseApp, width: int) -> str:
    hint = PAGE_HINTS[app.page_index]
    raw = f"  {hint}  "
    if len(raw) < width:
        raw += " " * (width - len(raw))
    else:
        raw = raw[:width]
    return PALETTE["footer_bg"](PALETTE["muted"](raw))


# ── Page builders ──────────────────────────────────────────────────────────


def _heading(text: str) -> Text:
    return Text(PALETTE["accent"](bold(text)), padding_x=1, padding_y=0)


def _para(text: str) -> Text:
    return Text(PALETTE["muted"](text), padding_x=1, padding_y=0)


def _select_list_theme() -> SelectListTheme:
    return SelectListTheme(
        selected_prefix=PALETTE["accent"],
        selected_text=lambda t: PALETTE["accent"](bold(t)),
        description=PALETTE["muted"],
        scroll_info=PALETTE["muted"],
        no_match=PALETTE["danger"],
    )


def _settings_list_theme() -> SettingsListTheme:
    return SettingsListTheme(
        label=lambda text, selected: PALETTE["accent"](bold(text)) if selected else text,
        value=lambda text, selected: PALETTE["accent"](text) if selected else PALETTE["muted"](text),
        description=PALETTE["muted"],
        cursor=PALETTE["accent"]("-> "),
        hint=PALETTE["muted"],
    )


def build_page_welcome(app: ShowcaseApp) -> None:
    app.body.add_child(_heading("Welcome to the Saber TUI Component Gallery"))
    app.body.add_child(Spacer(1))
    app.body.add_child(
        _para(
            "Saber TUI is a low-level Python TUI framework — eight composable "
            "components, an overlay system, focus management, ANSI styling, and "
            "coalesced async rendering. "
            "This gallery walks you through every component on its own page."
        )
    )
    app.body.add_child(Spacer(1))
    app.body.add_child(_para("• Tab / Shift+Tab — move between pages"))
    app.body.add_child(_para("• Ctrl+P — open the command palette overlay"))
    app.body.add_child(_para("• Ctrl+C — quit"))
    app.body.add_child(Spacer(1))
    app.body.add_child(
        Text(
            PALETTE["good"]("Tip: ")
            + PALETTE["muted"]("every component is in saber_tui.components and accepts ANSI-styled strings."),
            padding_x=1,
            padding_y=0,
        )
    )
    app.tui.set_focus(app.hidden_focus)


def build_page_text(app: ShowcaseApp) -> None:
    long_para = (
        "The quick brown fox jumps over the lazy dog. Pack my box with five "
        "dozen liquor jugs. Sphinx of black quartz, judge my vow. "
    ) * 2

    wrap_box = Box(padding_x=2, padding_y=1, bg_fn=PALETTE["panel"])
    wrap_box.add_child(Text(PALETTE["good"](bold("Text — wraps to width:")), padding_x=0, padding_y=0))
    wrap_box.add_child(Text(long_para, padding_x=0, padding_y=0))

    trunc_box = Box(padding_x=2, padding_y=1, bg_fn=PALETTE["panel_alt"])
    trunc_box.add_child(Text(PALETTE["warn"](bold("TruncatedText — single line, clipped:")), padding_x=0, padding_y=0))
    trunc_box.add_child(TruncatedText(long_para, padding_x=0, padding_y=0))

    app.body.add_child(wrap_box)
    app.body.add_child(Spacer(1))
    app.body.add_child(trunc_box)
    app.tui.set_focus(app.hidden_focus)


def build_page_box(app: ShowcaseApp) -> None:
    inner = Box(padding_x=2, padding_y=1, bg_fn=PALETTE["panel_alt"])
    inner.add_child(Text(PALETTE["accent"](bold("Inner Box")), padding_x=0, padding_y=0))
    inner.add_child(Text(PALETTE["muted"]("Boxes nest. Each has its own padding and bg."), padding_x=0, padding_y=0))

    outer = Box(padding_x=2, padding_y=1, bg_fn=PALETTE["panel"])
    outer.add_child(Text(PALETTE["good"](bold("Outer Box")), padding_x=0, padding_y=0))
    outer.add_child(Spacer(1))
    outer.add_child(inner)
    outer.add_child(Spacer(2))
    outer.add_child(Text(PALETTE["muted"]("↑ that gap is a Spacer(2)."), padding_x=0, padding_y=0))

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
    transcript_text = Text("", padding_x=1, padding_y=0)

    def update_transcript() -> None:
        if not app.transcript:
            transcript_text.set_text(PALETTE["muted"]("(no submissions yet — press Enter)"))
        else:
            recent = app.transcript[-5:]
            lines = "\n".join(f"  • {line}" for line in recent)
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

    app.body.add_child(_heading("Editor — multiline with history & autocomplete"))
    app.body.add_child(Spacer(1))
    app.body.add_child(editor)
    app.body.add_child(Spacer(1))
    app.body.add_child(
        _para(
            "Multiline edit · ↑↓ history (when empty) · Ctrl+Z undo · type / for slash-command "
            "autocomplete · Ctrl+A/E start/end · Alt+←/→ word · Ctrl+W delete word · "
            "Ctrl+K kill to end · Ctrl+Y yank · large pastes are folded into [paste #N] markers"
        )
    )
    app.body.add_child(Spacer(1))
    app.body.add_child(_heading("Submitted (last 5):"))
    app.body.add_child(transcript_text)
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
    select = SelectList(items, max_visible=6, theme=_select_list_theme())
    result_text = Text(PALETTE["muted"]("(use ↑↓ then Enter)"), padding_x=1, padding_y=0)

    def on_select(item: SelectItem) -> None:
        result_text.set_text(PALETTE["good"](f"  Picked: {item.label} — {item.description or ''}"))
        app.tui.request_render()

    def on_change(item: SelectItem) -> None:
        result_text.set_text(PALETTE["muted"](f"  Hovering: {item.label}"))
        app.tui.request_render()

    select.on_select = on_select
    select.on_selection_change = on_change
    app.select_list = select

    app.body.add_child(_heading("SelectList — themed, scrollable, filterable"))
    app.body.add_child(Spacer(1))
    app.body.add_child(select)
    app.body.add_child(Spacer(1))
    app.body.add_child(result_text)
    app.tui.set_focus(select)


def build_page_settings(app: ShowcaseApp) -> None:
    status = Text(PALETTE["muted"]("  Change a value or search by typing."), padding_x=1, padding_y=0)
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
        status.set_text(PALETTE["good"](f"  {id} = {new_value}"))
        app.tui.request_render()

    def on_cancel() -> None:
        status.set_text(PALETTE["warn"]("  Settings cancel callback fired."))
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

    app.body.add_child(_heading("SettingsList — toggles, search, submenus"))
    app.body.add_child(Spacer(1))
    app.body.add_child(_para("Type to fuzzy-filter by label. Space still activates the selected setting."))
    app.body.add_child(Spacer(1))
    app.body.add_child(settings)
    app.body.add_child(Spacer(1))
    app.body.add_child(status)
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
    status = Text(PALETTE["muted"]("(loaders ticking…)"), padding_x=1, padding_y=0)

    def on_cancel() -> None:
        status.set_text(PALETTE["danger"]("  Cancellable loader aborted."))
        cancellable.set_message("Aborted.")
        cancellable.dispose()
        app.tui.request_render()

    cancellable.on_cancel = on_cancel
    app.loader = loader
    app.cancellable = cancellable

    app.body.add_child(_heading("Loader — animated braille spinner"))
    app.body.add_child(loader)
    app.body.add_child(Spacer(1))
    app.body.add_child(_heading("CancellableLoader — handles Esc / Ctrl+C"))
    app.body.add_child(cancellable)
    app.body.add_child(Spacer(1))
    app.body.add_child(status)

    loader.start()
    cancellable.start()
    app.tui.set_focus(cancellable)


def build_page_overlays(app: ShowcaseApp) -> None:
    app.body.add_child(_heading("Overlays — modal dialogs and the command palette"))
    app.body.add_child(Spacer(1))
    app.body.add_child(_para("Press " + PALETTE["accent"]("m") + " to show a centered modal."))
    app.body.add_child(_para("Press " + PALETTE["accent"]("Ctrl+P") + " to open the command palette."))
    app.body.add_child(_para("Both close on " + PALETTE["accent"]("Ctrl+G") + " or " + PALETTE["accent"]("Esc") + "."))
    app.body.add_child(Spacer(1))
    app.body.add_child(
        _para(
            "Overlays are layered on top of the main content with anchored positioning "
            "(center, top-right, percentages, ...) and can capture or pass through focus."
        )
    )
    app.tui.set_focus(app.hidden_focus)


PAGE_BUILDERS: list[Callable[[ShowcaseApp], None]] = [
    build_page_welcome,
    build_page_text,
    build_page_box,
    build_page_input,
    build_page_select,
    build_page_settings,
    build_page_loader,
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
    box = Box(padding_x=3, padding_y=1, bg_fn=PALETTE["panel_alt"])
    box.add_child(Text(PALETTE["accent"](bold("Hello from a modal!")), padding_x=0, padding_y=0))
    box.add_child(Spacer(1))
    box.add_child(
        Text(
            PALETTE["muted"](
                "This Box is rendered inside an overlay anchored to the center of the "
                "terminal. Press Ctrl+G or Esc to dismiss."
            ),
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
            "width": "60%",
            "minWidth": 40,
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

    palette = SelectList(items, max_visible=8, theme=_select_list_theme())

    box = Box(padding_x=1, padding_y=0, bg_fn=PALETTE["panel"])
    title = Text(PALETTE["accent"](bold("  Command Palette  ")), padding_x=0, padding_y=0)
    hint = Text(PALETTE["muted"]("  ↑↓ move · Enter run · Esc cancel"), padding_x=0, padding_y=0)
    box.add_child(title)
    box.add_child(palette)
    box.add_child(hint)

    handle = app.tui.show_overlay(
        box,
        {
            "anchor": "center",
            "width": "70%",
            "minWidth": 50,
            "maxHeight": 14,
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
    # Ctrl+G is a single-byte BEL (0x07) that StdinBuffer flushes immediately;
    # Esc alone is buffered by StdinBuffer until a follow-up byte unless the
    # terminal has Kitty-protocol disambiguate enabled, so accepting both gives
    # users a key that always works.
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
            if app.page_index == 7 and data == "m":
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
