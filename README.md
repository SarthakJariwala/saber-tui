# saber-tui

A simple TUI in Python, inspired by pi-tui.

`saber-tui` provides low-level building blocks for terminal UIs: a render tree,
raw terminal integration, focus and overlays, editable text controls, list
selection, animated loaders, and ANSI/Unicode-aware layout helpers.

## Features

- `TUI` and `Container` render trees with differential rendering, resize
  handling, overlays, focus management, and optional hardware cursor placement.
- `ProcessTerminal` for raw terminal lifecycle, bracketed paste, resize
  callbacks, title/progress control, and native scrollback-friendly rendering.
- Key parsing and customizable keybindings, including kitty keyboard protocol,
  modifyOtherKeys sequences, printable key decoding, and key repeat/release
  detection.
- Text layout components: `Text`, `TruncatedText`, `Box`, and `Spacer`.
- Interactive controls: single-line `Input`, multiline `Editor`, `SelectList`,
  `Loader`, and `CancellableLoader`.
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

Run the examples:

```bash
uv run python examples/chat.py
uv run python examples/showcase.py
```

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
- `ProcessTerminal`
- ANSI and Unicode width utilities.
- `StdinBuffer` with bracketed paste handling.
- Key parsing and keybindings.
- `Text`, `TruncatedText`, `Box`, `Spacer`, `Input`, `Editor`, `SelectList`,
  `Loader`, and `CancellableLoader`.
- Slash-command and file/path autocomplete support.

Outside this slice:

- Markdown rendering.
- Terminal image protocols.
- Full Windows-specific VT input support.
