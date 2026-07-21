# saber-tui

A simple TUI in Python, inspired by pi-tui.

`saber-tui` provides low-level building blocks for terminal UIs: a render tree,
raw terminal integration, focus and overlays, editable text controls, list
selection, animated loaders, and ANSI/Unicode-aware layout helpers.

## Features

- `TUI` and `Container` render trees with differential rendering, resize
  handling, overlays, focus management, and optional hardware cursor placement.
- `ProcessTerminal` for raw terminal lifecycle, bracketed paste, resize
  callbacks, title/progress control, native scrollback-friendly rendering, and
  automatic POSIX/native Windows backend selection.
- Key parsing and customizable keybindings, including kitty keyboard protocol,
  modifyOtherKeys sequences, printable key decoding, and key repeat/release
  detection.
- Text layout components: `Text`, `TruncatedText`, `Box`, and `Spacer`.
- Streaming-safe Markdown with headings, inline styles, fenced/highlighted code,
  nested and task lists, blockquotes, tables, links, HTML text, and ANSI-aware wrapping.
- Interactive controls: single-line `Input`, multiline `Editor`, `SelectList`,
  `SettingsList`, `Loader`, and `CancellableLoader`.
- Editor behavior for command-style input: history, undo, kill/yank, word
  movement, paste markers, submit/change callbacks, and configurable padding.
- Autocomplete primitives and providers: `AutocompleteItem`, `SlashCommand`,
  `AutocompleteSuggestions`, `CompletionResult`, and
  `CombinedAutocompleteProvider` with command and path suggestions.
- ANSI-aware wrapping, slicing, truncation, background application, grapheme
  handling, fuzzy matching, and terminal-output normalization utilities.

## Usage

```python
from saber_tui import ProcessTerminal, TUI, matches_key
from saber_tui.components import Editor, Text

terminal = ProcessTerminal()
tui = TUI(terminal)
tui.add_child(Text("Welcome"))

editor = Editor(tui)
editor.on_submit = lambda value: tui.add_child(Text(f"You said: {value}"))
tui.add_child(editor)
tui.set_focus(editor)

def exit_on_ctrl_c(data: str):
    if matches_key(data, "ctrl+c"):
        tui.stop()
        raise SystemExit(0)
    return None

tui.add_input_listener(exit_on_ctrl_c)
tui.start()
```

Markdown can be updated as assistant output streams in. Incomplete closing code
fences are stabilized so the block does not flicker when the last backtick arrives:

```python
from saber_tui.components import Markdown, MarkdownTheme

markdown = Markdown("", padding_x=1, theme=MarkdownTheme())
tui.add_child(markdown)

# For each streamed chunk:
markdown.append_text(chunk)
tui.request_render()
```

Use `MarkdownTheme` to supply ANSI style functions, `DefaultTextStyle` for a
message-wide foreground/background and decorations, and `MarkdownOptions` for
source marker/escape preservation or explicit OSC 8 hyperlink behavior.

### Terminal images

```python
from saber_tui.components import Image

tui.add_child(Image(tui, png_bytes, "image/png"))
```

Images are detected conservatively per `TUI`: Kitty, Ghostty, WezTerm, and Warp
use the Kitty graphics protocol; iTerm2 uses OSC 1337. Kitty accepts PNG data
only, while iTerm2 recognizes PNG, JPEG, GIF, and WebP containers.
Unknown terminals, Windows Terminal, VS Code, Alacritty, JetBrains JediTerm,
tmux, and screen receive a width-safe text fallback. Sixel is not supported.
Terminal image rows are opaque to overlays, and overlays may not contain image
commands. Components cache their base64/rendered representation, so retaining
many image components also retains their encoded image data in memory; call
`invalidate()` after terminal metrics or image presentation options change.

For settings-style UIs, use `SettingsList` with value cycling, fuzzy search, and
optional submenus:

```python
from saber_tui.components import SettingItem, SettingsList, SettingsListOptions

settings = SettingsList(
    [
        SettingItem("theme", "Theme", "dark", values=["dark", "light", "system"]),
        SettingItem("streaming", "Streaming", "on", values=["on", "off"]),
    ],
    max_visible=8,
    on_change=lambda setting_id, value: print(f"{setting_id} = {value}"),
    options=SettingsListOptions(enable_search=True),
)
```

Run the examples:

```bash
uv run python examples/chat.py
uv run python examples/showcase.py
```

The chat demo renders its streamed assistant response through `Markdown`. The
component gallery includes a dedicated Markdown page; press `r` there to replay
the stream and watch inline styles, lists, code fences, blockquotes, and tables
appear incrementally.

`ProcessTerminal` supports POSIX terminals and native Windows consoles with
virtual terminal processing, including Windows Terminal and recent PowerShell or
cmd sessions. WSL uses the POSIX backend.

## Development

```bash
uv run pytest
uv run ruff check
uv run ruff format --check
uvx ty check
```

## Current Scope

Available in this slice:

- Core `TUI`, `Container`, overlays, focus, and differential rendering.
- `ProcessTerminal` on POSIX and native Windows VT-capable consoles.
- ANSI and Unicode width utilities.
- `StdinBuffer` with bracketed paste handling.
- Key parsing and keybindings.
- `Text`, `TruncatedText`, `Box`, `Spacer`, `Markdown`, `Input`, `Editor`,
  `SelectList`, `SettingsList`, `Loader`, and `CancellableLoader`.
- Slash-command and file/path autocomplete support.

Outside this slice:

- Sixel and terminal image protocols other than Kitty and iTerm2.
- Legacy Windows consoles without virtual terminal processing.
