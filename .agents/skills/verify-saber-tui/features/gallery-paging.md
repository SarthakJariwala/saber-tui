# Gallery: page navigation

The component gallery (`examples/showcase.py`) is a 9-page tour. Tab moves forward, Shift+Tab moves back, and the header always shows `Saber TUI · Component Gallery` with a `[n/9] <title>` indicator. The footer shows per-page key hints. Page order: Welcome, Text & TruncatedText, Box & Spacer, Editor, SelectList, SettingsList, Loader & CancellableLoader, Markdown, Overlays.

## Sub-features

- `paging-next` moves to the next page on Tab and rebuilds the body.
- `paging-prev` moves to the previous page on Shift+Tab.
- `paging-clamp` stays on Welcome when pressing Shift+Tab there and on Overlays when pressing Tab there.
- `paging-frame` keeps the header title, `[n/9]` indicator, and footer hint in sync with the page.
- `paging-quit` exits on Ctrl+C anywhere, or `q` on pages without a focused editor.

## How to get to it (user POV)

- Run `uv run python examples/showcase.py`; navigation keys work on every page.
- Jump directly through the command palette `Go to:` entries (see [gallery-overlays.md](./gallery-overlays.md)).

## Driving it with tmux

Preconditions:

- A fresh session per SKILL.md Launch, running `examples/showcase.py`, ready when the pane shows `Welcome to the Saber TUI Component Gallery`.

- **Next.** Run `tmux send-keys -t "$session" Tab` then `.agents/skills/verify-saber-tui/scripts/pane-wait.sh "$session" "[2/9]"`. The header shows `[2/9] Text & TruncatedText` and the body shows the Text page heading.
- **Prev.** Run `tmux send-keys -t "$session" BTab` then `.agents/skills/verify-saber-tui/scripts/pane-wait.sh "$session" "[1/9]"`. The Welcome heading is back.
- **Clamp low.** On page 1, run `tmux send-keys -t "$session" BTab` and capture after a wait on `[1/9]`. The page does not change.
- **Clamp high.** Press Tab eight times (`tmux send-keys -t "$session" Tab` each), wait for `[9/9]`, press Tab once more, and confirm the pane still shows `[9/9] Overlays`.
- **Frame.** In each capture, assert the footer hint matches the page (for example `Tab next  ·  Ctrl+P palette  ·  Ctrl+C quit` on Welcome).
- **Quit.** Run `tmux send-keys -t "$session" C-c`. The process exits and the session closes.

## Gotchas

- Tab reaches the Editor page (4) and SelectList page (5) where focus captures keys; Tab itself still pages, but `q` does not quit there.
- Page indicators like `[2/9]` are unique, stable wait anchors; page titles contain `—` (em dash) so prefer the indicator or short heading words.
- The Loader page (7) animates continuously, so captures of it differ run to run; anchor on its heading, not spinner frames.
