# saber-tui

Faithful low-level Python port of `@mariozechner/pi-tui`.

This first slice provides the core line-rendering framework, process terminal
abstraction, key parsing, keybindings, overlays, text components, single-line
input, select lists, and loaders.

## Usage

```python
from saber_tui import ProcessTerminal, TUI, matches_key
from saber_tui.components import Input, Text

terminal = ProcessTerminal()
tui = TUI(terminal)
tui.add_child(Text("Welcome"))

input_box = Input()
input_box.on_submit = lambda value: tui.add_child(Text(f"You said: {value}"))
tui.add_child(input_box)
tui.set_focus(input_box)

def exit_on_ctrl_c(data: str):
    if matches_key(data, "ctrl+c"):
        tui.stop()
        raise SystemExit(0)
    return None

tui.add_input_listener(exit_on_ctrl_c)
tui.start()
```

Run the example:

```bash
uv run python examples/chat_simple.py
```

## Development

```bash
uv run pytest
uv run ruff check
uv run ruff format --check
uvx ty check
```

## Parity Scope

Included in this slice:

- Core `TUI`, `Container`, overlays, focus, and differential rendering
- `ProcessTerminal`
- ANSI and Unicode width utilities
- `StdinBuffer`
- key parsing and keybindings
- `Text`, `TruncatedText`, `Box`, `Spacer`, `Input`, `SelectList`, `Loader`, and `CancellableLoader`

Outside this slice:

- Multiline `Editor`
- Autocomplete
- Markdown rendering
- Terminal image protocols
- Windows-specific VT input support
