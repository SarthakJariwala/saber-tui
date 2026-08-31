# Gallery: markdown streaming

Page 8 of the gallery streams a fixed markdown document into a `Markdown` component a few characters at a time, proving flicker-free incremental rendering of headings, inline styles, task lists, a fenced python block, a blockquote, and a table. The stream starts automatically when the page opens; `r` replays it from the start.

## Sub-features

- `md-autostream` starts streaming the demo document on page entry.
- `md-complete` finishes with the full document rendered: heading, styled inline text, task list, code fence, and table.
- `md-replay` restarts the stream from an empty component when the user presses `r`.

## How to get to it (user POV)

- From the gallery Welcome page, press Tab 7 times until the header reads `[8/9] Markdown — streaming renderer`.
- Or open the palette (Ctrl+P) and run `Go to: Markdown — streaming renderer`.

## Driving it with tmux

Preconditions:

- A fresh gallery session, then Tab 7 times and `.agents/skills/verify-saber-tui/scripts/pane-wait.sh "$session" "[8/9]"` succeeds.

- **Autostream.** Immediately after arriving, wait for the end of the document. Run `.agents/skills/verify-saber-tui/scripts/pane-wait.sh "$session" "Code fences" 20`. The pane shows the heading `Markdown streams without flicker`, the task list, the python code block, and the table rows (`Tables`, `Code fences`).
- **Complete.** Capture plain and `-e` variants; the `-e` capture proves inline styling (bold/italic codes) survived streaming.
- **Replay.** Run `tmux send-keys -t "$session" r`, then within a second capture the pane and confirm the document is shorter than the completed state (streaming restarted), then run `.agents/skills/verify-saber-tui/scripts/pane-wait.sh "$session" "Code fences" 20` to see it complete again.

## Gotchas

- The whole stream completes in a few seconds; to observe a mid-stream state, capture immediately after `r` rather than after page entry.
- Table cell text renders without the `|` source characters; anchor on cell text like `Code fences`, not on markdown syntax.
- No editor has focus here, so `r` is a page shortcut; if an overlay is open it goes to the overlay instead.
- Leaving the page cancels the stream timer; re-entering restarts the stream from scratch.
