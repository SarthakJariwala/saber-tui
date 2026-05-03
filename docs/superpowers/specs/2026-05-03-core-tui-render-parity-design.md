# Core TUI Render Parity Design

## Goal

Bring non-image core `TUI` behavior closer to upstream `pi-tui` by making render requests asynchronous, coalesced, and throttle-aware, and by improving differential redraw state so common viewport updates do not fall back to full redraws.

## Scope

Included:

- Async render scheduling for `TUI.request_render()`.
- Forced render scheduling that clears pending timers and renders on the next tick.
- Render throttling at a small minimum interval matching upstream behavior.
- More precise viewport and cursor tracking: logical cursor row, hardware cursor row, maximum rendered lines, and previous viewport top.
- Differential redraw handling for appended lines, deleted lines, visible line changes, offscreen changes, viewport shifts, and bottom-scroll cases.
- Scrollback clearing on explicit full-clear paths.
- `clear_on_shrink` runtime controls.
- Runtime hardware cursor visibility controls.
- Exit cursor placement before stopping the terminal.
- Debug/crash diagnostics for render decisions and over-wide rendered lines.
- A tmux smoke test path for real terminal behavior.

Excluded from this pass:

- Terminal image protocol line handling.
- Image-aware overlay composition.
- Terminal cell-size query and response handling.

## Architecture

`TUI.request_render()` becomes a scheduler front-end instead of rendering immediately. Normal requests set a pending flag and schedule a timer that respects a minimum render interval. Forced requests clear previous render state, cancel any pending timer, and schedule a next-tick render. The public API remains `request_render(force=False)`, with an added `flush_render()` helper for deterministic tests and callers that need to wait for scheduled output.

The renderer keeps enough state to reason in logical buffer coordinates instead of only screen rows. `cursor_row` tracks the logical end of rendered content. `hardware_cursor_row` tracks where the terminal cursor actually ended after the last write. `previous_viewport_top` tracks which logical line was at the top of the terminal viewport. `max_lines_rendered` tracks the largest logical working area so content shrink can clear stale rows when enabled.

Differential rendering compares normalized lines and chooses the narrowest safe write:

- no changed visible lines: only reposition the hardware cursor;
- first change above the previous viewport: full redraw;
- appended lines below the viewport bottom: move to bottom and scroll by writing newlines;
- visible changed lines: move relatively from the tracked hardware cursor and rewrite only the changed range;
- deleted trailing lines: clear stale visible rows without redrawing unchanged lines when possible;
- unsafe viewport shifts, width changes, forced renders, and configured shrink clears: full redraw.

Full clear writes include synchronized output plus `ESC[2J`, `ESC[H`, and `ESC[3J` so the viewport and scrollback are both cleared. Stopping the TUI cancels scheduled work, moves the cursor to the line after the rendered content, shows the hardware cursor, and stops the terminal.

## Testing

Unit tests cover the scheduler, forced render cancellation, throttle coalescing, cursor controls, clear-on-shrink, scrollback clear, exit cursor placement, and differential rendering cases. The virtual terminal remains the primary deterministic assertion surface.

A tmux smoke script exercises a small real terminal session for start, input-driven redraw, resize, and stop. It is not the only safety net; it catches escape/cursor behavior that snapshot-style unit tests can miss.

## Error Handling And Diagnostics

Over-wide rendered lines continue to raise, but now also write a crash log under `/tmp/saber-tui` when possible. Debug render decision logging is gated by `SABER_TUI_DEBUG_REDRAW=1` and detailed buffer logs by `SABER_TUI_DEBUG=1`. Logging failures must not hide the original render behavior unless the render line itself is invalid.

## Compatibility

Existing component APIs do not change. Tests and callers that expect immediate output after `request_render()` should use `flush_render()` in deterministic contexts. `start()` schedules the first render and then flushes it once so existing simple startup behavior remains practical for synchronous examples and tests.
