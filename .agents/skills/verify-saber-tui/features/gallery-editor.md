# Gallery: editor page

Page 4 of the gallery hosts a focused multiline `Editor` with a border, history, undo, kill/yank, and slash-command autocomplete. Submitting non-empty text appends it to the `RECENT SUBMISSIONS` card below the editor and clears the input.

## Sub-features

- `editor-type` echoes typed printable text inside the bordered editor.
- `editor-submit` on Enter appends the text as a `● <text>` transcript line and clears the editor.
- `editor-history` recalls the previous submission with the Up arrow when the editor is empty.
- `editor-autocomplete` shows a suggestion list (`/help`, `/clear`, `/quit`) after typing `/`.

## How to get to it (user POV)

- From the gallery Welcome page, press Tab 3 times until the header reads `[4/9] Editor — multiline editor`.
- Or open the palette (Ctrl+P) and run `Go to: Editor — multiline editor`.

## Driving it with tmux

Preconditions:

- A fresh gallery session, then Tab 3 times and `.agents/skills/verify-saber-tui/scripts/pane-wait.sh "$session" "[4/9]"` succeeds.

- **Type.** Run `tmux send-keys -t "$session" -l "hello from tmux"` then `.agents/skills/verify-saber-tui/scripts/pane-wait.sh "$session" "hello from tmux"`. The text appears inside the editor border, and the transcript still shows `No submissions yet. Press Enter to add one.`.
- **Submit.** Run `tmux send-keys -t "$session" Enter` then `.agents/skills/verify-saber-tui/scripts/pane-wait.sh "$session" "●  hello from tmux"`. The transcript lists `●  hello from tmux` and the editor is empty.
- **History.** Run `tmux send-keys -t "$session" Up` and wait for `hello from tmux` to reappear in the editor; press Escape or delete the text to leave history recall.
- **Autocomplete.** With an empty editor, run `tmux send-keys -t "$session" -l "/"` then `.agents/skills/verify-saber-tui/scripts/pane-wait.sh "$session" "/help"`. A suggestion list shows `/help`, `/clear`, `/quit`; press Escape to dismiss, then clear the `/` with BSpace.

## Gotchas

- The editor owns focus, so `q` types a letter instead of quitting; leave the page with Tab/Shift+Tab or quit with Ctrl+C.
- Enter on an empty editor submits an empty string, which the page ignores; the transcript only changes for non-empty text.
- History recall on Up works only while the editor is empty; leftover text turns Up into cursor movement.
- The transcript keeps the last 5 submissions; older lines drop off, so assert on recent ones.
