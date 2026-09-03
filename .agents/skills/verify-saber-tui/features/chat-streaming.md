# Chat: send and stream a message

The chat demo (`examples/chat.py`) lets a user type a message into a bordered editor card, submit it with Enter, and watch an assistant echo stream in word by word as live-rendered markdown. Completed turns flow into native terminal scrollback; the live pane keeps the branded header, recent turns, editor, and key hints.

## Sub-features

- `chat-welcome` shows a system welcome message on launch.
- `chat-send` submits the editor text as a `You` message and clears the editor.
- `chat-stream` streams the assistant echo word by word with markdown (bold, inline code) rendered live.
- `chat-scrollback` moves completed turns into terminal scrollback instead of a scrolling widget.
- `chat-quit` exits cleanly on Ctrl+C.

## How to get to it (user POV)

- Run `uv run python examples/chat.py` in a terminal and type into the always-focused editor.

## Driving it with tmux

Preconditions:

- A fresh session per SKILL.md Launch, running `examples/chat.py`, ready when the pane shows `Type a message`.

- **Welcome.** Launch and wait. Run `.agents/skills/verify-saber-tui/scripts/pane-wait.sh "$session" "Type a message" 20`. The pane shows a `◆ SYSTEM` message and an empty `MESSAGE` editor card.
- **Send.** Type a message and submit. Run `tmux send-keys -t "$session" -l "hello saber"` then `tmux send-keys -t "$session" Enter`. A `◆ YOU` turn containing `hello saber` appears and the editor is empty again.
- **Stream.** Wait for the echo to finish. Run `.agents/skills/verify-saber-tui/scripts/pane-wait.sh "$session" "Your message was: hello saber" 20`. An `Assistant` turn ends with `Your message was: hello saber`; mid-stream captures show it growing.
- **Scrollback.** Send several more messages, then capture history. Run `tmux capture-pane -pt "$session" -S -`. Earlier turns appear above the live viewport in the scrollback output.
- **Quit.** Run `tmux send-keys -t "$session" C-c`. The process exits and the tmux session closes on its own.

## Gotchas

- Streaming takes roughly 40ms per word; wait on the final phrase `Your message was: <text>`, not on partial output.
- The editor always has focus. Every printable key is typed into it, so there are no page-style shortcut keys here.
- Proving `chat-scrollback` needs enough turns to overflow the 30-row pane; a single short exchange stays fully visible.
- After Ctrl+C the session is gone; capture all evidence before quitting.
