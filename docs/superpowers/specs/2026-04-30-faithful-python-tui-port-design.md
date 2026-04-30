# Faithful Python TUI Port Design

Date: 2026-04-30

## Context

The upstream source inspected for this design is `badlogic/pi-mono`, specifically
`packages/tui/src` cloned to `/tmp/pi-mono`. The upstream package is a minimal
terminal UI framework built around line-oriented component rendering,
differential terminal updates, raw terminal input handling, overlays, and
Unicode-aware text utilities.

This repository starts as a new Python project. The user wants a faithful
low-level Python port and explicitly wants `uv` for dependency management,
project commands, and tests.

## Goals

- Port the upstream architecture faithfully rather than wrapping an existing
  retained-mode Python TUI framework.
- Keep the public model simple: components render to width-bounded terminal
  lines, the TUI owns composition and differential rendering, and the terminal
  abstraction owns raw input/output.
- Use small focused Python libraries only where they replace low-level
  primitives cleanly.
- Build a testable framework with a virtual terminal so renderer behavior can
  be verified without requiring an interactive terminal.
- Start with a core parity slice before porting higher-risk features such as
  terminal images and the full multiline editor.

## Non-Goals

- Do not use Textual as the foundation. It is a full TUI framework and would
  replace the architecture being ported.
- Do not use prompt_toolkit as the main application loop or renderer. It can be
  reconsidered later for optional integrations, but the core port should own
  rendering and key handling.
- Do not port terminal image protocols, Markdown rendering, autocomplete, or the
  full multiline editor in the first implementation slice.
- Do not add packaging or publishing automation before the core framework and
  tests are in place.

## Upstream Architecture Summary

The upstream framework has four important layers.

1. Terminal layer:
   `Terminal` defines start/stop, write, dimensions, cursor movement, clearing,
   title, and progress operations. `ProcessTerminal` enables raw mode, bracketed
   paste, resize callbacks, Kitty keyboard protocol probing, xterm
   modifyOtherKeys fallback, stdin buffering, and cursor visibility.

2. Component layer:
   `Component.render(width)` returns a list of strings, one per rendered line.
   Each line must fit the supplied terminal width. Components may also implement
   `handleInput(data)` and `invalidate()`. Focusable components expose a
   `focused` flag and emit a zero-width cursor marker at the logical cursor
   position.

3. TUI renderer:
   `TUI` is a `Container` with children, focus, input listeners, overlays,
   render scheduling, cursor marker extraction, synchronized output, and
   differential repainting. Width changes force full redraws because wrapping
   changes. Height changes usually force redraws except in Termux. Shrink
   clearing is configurable.

4. Utilities:
   Unicode and ANSI handling is central. The upstream implementation measures
   display width by grapheme cluster, preserves ANSI state across wrapping,
   truncates by terminal columns, slices by column, and composites overlays into
   base lines without corrupting styles.

## Python Architecture

The Python package should be named `saber_tui`.

### `saber_tui.terminal`

Defines a `Terminal` protocol and a `ProcessTerminal` implementation.

Responsibilities:

- Enter and restore raw terminal mode.
- Enable and disable bracketed paste.
- Read stdin and dispatch complete input sequences.
- Report terminal dimensions.
- Provide ANSI output helpers for cursor movement, clearing, cursor visibility,
  title, and progress.
- Expose whether Kitty keyboard protocol is active.
- Restore terminal state on stop, including cursor visibility and raw mode.

Implementation notes:

- Use Python standard library `termios`, `tty`, `select`, `signal`, `os`,
  `sys`, and `shutil`.
- Keep Windows support out of the first slice unless it can be added without
  widening the design. The upstream Windows VT input behavior can be documented
  as later parity work.
- Support bracketed paste in the first slice.
- Implement Kitty keyboard probing and xterm modifyOtherKeys as first-class
  goals for parity, but keep the implementation isolated so it can be tested.

### `saber_tui.stdin_buffer`

Ports upstream `StdinBuffer`.

Responsibilities:

- Buffer partial escape sequences.
- Emit complete CSI, OSC, DCS, APC, SS3, meta, mouse, and printable sequences.
- Detect bracketed paste start and end markers.
- Emit paste content separately and re-wrap it for component compatibility.
- Avoid duplicate printable emission when terminals send both CSI-u printable
  events and raw printable bytes.

### `saber_tui.keys`

Ports upstream key identification.

Responsibilities:

- Match raw input strings against key ids such as `ctrl+c`, `shift+enter`,
  `alt+left`, `pageUp`, and printable keys.
- Parse Kitty CSI-u sequences, event types, alternate/base layout keys, and
  key release/repeat events.
- Parse xterm modifyOtherKeys sequences.
- Decode printable key input from Kitty CSI-u and modifyOtherKeys.
- Keep key identifiers string-based for API parity and simple downstream use.

### `saber_tui.keybindings`

Ports upstream keybinding registry.

Responsibilities:

- Provide default TUI keybindings for editor/input/select actions.
- Allow user overrides.
- Detect conflicts among user overrides.
- Provide `matches(data, keybinding)` using `keys.matches_key`.

### `saber_tui.utils`

Ports width, wrapping, truncation, and ANSI helpers.

Responsibilities:

- Strip and extract ANSI/OSC/APC sequences.
- Compute visible terminal width.
- Segment text by grapheme cluster.
- Wrap ANSI-styled text while preserving active styles across line breaks.
- Truncate styled text to a maximum column width with optional padding.
- Slice text by terminal columns, with strict wide-character boundary handling.
- Extract before/after segments for overlay compositing while preserving style.
- Normalize terminal output for known rendering edge cases where practical.

Dependencies:

- Use `wcwidth` for display cell width.
- Use `regex` for grapheme cluster segmentation with `\X`.

### `saber_tui.tui`

Ports the core framework.

Public types:

- `Component`
- `Focusable`
- `Container`
- `TUI`
- `OverlayOptions`
- `OverlayHandle`
- `CURSOR_MARKER`

Responsibilities:

- Manage children and focus.
- Manage global input listeners that can consume or rewrite input.
- Manage a stack of overlays with focus capture, temporary hiding, permanent
  hiding, visibility predicates, anchors, percentage sizing, margins, and
  focus order.
- Render child components into flat lines.
- Composite visible overlays by terminal column.
- Extract cursor markers before line resets.
- Append a full style and OSC 8 reset to non-image lines.
- Validate that rendered non-image lines do not exceed terminal width.
- Schedule renders with a minimum interval near 16 ms.
- Perform full redraws when width changes, height changes, or shrink clearing
  requires it.
- Perform differential redraws by finding first and last changed lines and
  writing only the changed span.
- Position the hardware cursor for focused components when requested.

### `saber_tui.components`

First implementation slice:

- `Text`: multi-line ANSI-aware wrapping with padding and optional background
  function.
- `TruncatedText`: single-line truncation with padding.
- `Box`: child container with padding and optional background function.
- `Spacer`: fixed empty vertical space.
- `Input`: single-line editor with cursor movement, horizontal scrolling,
  bracketed paste, kill ring, undo stack, and submit/escape callbacks.
- `SelectList`: filtered selectable list with scrolling, descriptions, and
  callbacks.
- `Loader` and `CancellableLoader`: spinner components driven by TUI render
  requests.

Supporting modules:

- `kill_ring.py`
- `undo_stack.py`
- `fuzzy.py`

Deferred components:

- `Editor`
- `Autocomplete`
- `Markdown`
- `Image`
- terminal image capability detection and protocols

## Public API Shape

The first user-facing API should feel close to upstream while using Python
naming conventions.

```python
from saber_tui import Input, ProcessTerminal, Text, TUI, matches_key

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

tui.add_input_listener(exit_on_ctrl_c)
tui.start()
```

Component contract:

```python
class Component(Protocol):
    wants_key_release: bool

    def render(self, width: int) -> list[str]:
        ...

    def handle_input(self, data: str) -> None:
        ...

    def invalidate(self) -> None:
        ...
```

The actual protocol should make `handle_input`, `invalidate`, and
`wants_key_release` optional through runtime checks, matching the upstream
behavior.

## Dependency Plan

Use `uv` for project initialization, dependency management, and commands.

Runtime dependencies:

- `wcwidth`: terminal display width.
- `regex`: grapheme cluster segmentation.

Development dependencies:

- `pytest`: test runner.
- `pyte`: virtual terminal emulator for renderer tests.
- `ruff`: formatting and linting.
- `ty`: optional type checking through `uvx ty check`.

Rich can be added later when the Markdown component is ported. It is not needed
for the initial renderer and component slice.

## Testing Strategy

Use `pytest` with focused unit tests and virtual terminal integration tests.

Unit tests:

- ANSI extraction and stripping.
- Visible width for ASCII, emoji, CJK, combining marks, tabs, and ANSI-styled
  strings.
- Grapheme-safe wrapping, truncation, and column slicing.
- Key matching for legacy sequences, Kitty CSI-u, modifyOtherKeys, modifiers,
  printable decoding, key release, and key repeat.
- Stdin buffering for partial escape sequences, bracketed paste, OSC/DCS/APC,
  mouse sequences, and plain printable data.
- Keybinding defaults, overrides, and conflicts.
- Input editing behavior: insertion, cursor movement, word movement, deletion,
  kill ring, yank, undo, paste, submit, escape, and width-bounded rendering.
- SelectList rendering, filtering, selection movement, callbacks, and width
  bounds.

Virtual terminal tests:

- First render writes all lines.
- Width change causes full redraw.
- Height change causes full redraw outside Termux behavior.
- Diff rendering updates only changed lines where possible.
- Content shrink clearing works when enabled.
- Overlay positioning, visibility, focus behavior, z-order, and compositing.
- Cursor marker extraction positions the hardware cursor and strips the marker
  from visible output.
- Rendered lines never exceed terminal width unless explicitly allowed for a
  deferred image-line path.

Use `pyte` to implement a test `VirtualTerminal` analogous to upstream
`test/virtual-terminal.ts`.

## Implementation Phases

Phase 1: Project and utility foundation.

- Initialize `uv` Python package.
- Add runtime and dev dependencies.
- Implement package exports.
- Port `utils.py`, `stdin_buffer.py`, `keys.py`, `keybindings.py`,
  `kill_ring.py`, `undo_stack.py`, and `fuzzy.py`.
- Add unit tests for those modules.

Phase 2: Terminal and renderer.

- Implement `Terminal`, `ProcessTerminal`, `VirtualTerminal`, `Component`,
  `Focusable`, `Container`, overlay types, and `TUI`.
- Add renderer and overlay tests through `pyte`.

Phase 3: Core components.

- Implement `Text`, `TruncatedText`, `Box`, `Spacer`, `Input`, `SelectList`,
  `Loader`, and `CancellableLoader`.
- Port matching upstream tests for these components.
- Add a small runnable example.

Phase 4: Stabilization.

- Run pytest, ruff, and type checks.
- Review parity gaps against the upstream package.
- Document supported terminals, known limitations, and the deferred parity list.

Later phases can port `Editor`, autocomplete, Markdown, and image rendering once
the core renderer and input stack are stable.

## Acceptance Criteria

- The project is managed by `uv`.
- The package imports as `saber_tui`.
- A small interactive example can create a `TUI`, add text and input components,
  focus the input, render updates, and exit on `ctrl+c`.
- Core unit tests and virtual terminal tests pass with `uv run pytest`.
- Formatting and linting pass with `uv run ruff check` and
  `uv run ruff format --check`.
- The first implementation slice avoids Textual and prompt_toolkit as core
  dependencies.
- Rendered component lines are validated against terminal width.
- The implementation keeps clear parity notes for behavior intentionally
  deferred from upstream.

## Risks and Decisions

- Unicode width behavior differs across terminals. The port will use `wcwidth`
  and grapheme segmentation, then add regression tests for cases discovered
  during upstream comparison.
- Python raw terminal handling differs from Node streams. The terminal layer
  should stay isolated and covered by unit tests where possible.
- Exact differential rendering behavior is subtle. The first renderer should
  prioritize correctness and parity tests; micro-optimizations can follow after
  behavior is pinned down.
- Windows terminal support is deferred unless it falls out naturally from the
  standard-library implementation. The first supported target is Unix-like
  terminals.
