# Gallery: overlays

The gallery layers overlays on top of page content: a centered modal box on the Overlays page and a command menu available on every page. The menu is a filterable `SelectList` of `Go to:` page actions plus `Show modal` and `Quit`. Esc or Ctrl+G closes either overlay.

## Sub-features

- `overlay-modal` shows a centered modal box on `m` (Overlays page only).
- `overlay-modal-close` dismisses the modal on Esc or Ctrl+G.
- `overlay-palette` opens the command palette on Ctrl+P from any page.
- `overlay-palette-run` runs the highlighted action on Enter (for example jumping to a page).
- `overlay-palette-filter` narrows the action list as the user types.

## How to get to it (user POV)

- Press Ctrl+P on any gallery page for the palette.
- Press Tab from Welcome 8 times to reach `[9/9] Overlays`, then press `m` for the modal.

## Driving it with tmux

Preconditions:

- A fresh gallery session on the Welcome page.

- **Palette.** Run `tmux send-keys -t "$session" C-p` then `.agents/skills/verify-saber-tui/scripts/pane-wait.sh "$session" "COMMAND MENU"`. The overlay lists `Go to:` entries with the hint `↑↓ move · Enter run · Esc cancel`.
- **Filter.** Run `tmux send-keys -t "$session" -l "editor"` and wait for `FILTER  editor`. Capture the pane and assert that it shows `Go to: Editor — multiline editor` but no longer shows `Go to: Welcome`.
- **Run action.** Run `tmux send-keys -t "$session" Enter` then `.agents/skills/verify-saber-tui/scripts/pane-wait.sh "$session" "[4/9]"`. The palette closes and the Editor page is active.
- **Modal.** Go to the Overlays page (palette action `Go to: Overlays — modal & palette` or Tab), run `tmux send-keys -t "$session" m`, then wait for `Hello from a modal!`. A centered box overlays the page text.
- **Close.** Run `tmux send-keys -t "$session" Escape` and confirm a follow-up capture no longer contains `Hello from a modal!` while the page heading remains.

## Gotchas

- `m` opens the modal only on the Overlays page and only while no editor has focus; on other pages it either types or does nothing.
- While the palette is open, arrow keys and typed text go to the palette list, not the page underneath.
- Opening the palette on the Editor page steals focus from the editor; closing it restores the page.
- Capture the closed state as absence of the overlay marker text plus presence of the page heading, never as pixel comparison.
