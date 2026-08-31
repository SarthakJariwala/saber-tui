# saber-tui verification map

This directory is the maintained source for verifying user-facing behavior of the saber-tui examples. Read this index before driving, then use the matching feature file as the recipe. A proof that drives one convenient entry point is incomplete when the feature file lists others.

## Baseline preconditions

- Work from the repo root with dependencies installed (`uv sync`).
- The doctor check in [SKILL.md](../SKILL.md) passes.
- Each drive uses a fresh tmux session named `saber_verify_$run_id` sized 100x30.
- Never drive a tmux session this verification run did not create.

## Driving conventions

- Send keys with `tmux send-keys -t "$session"`; use `-l` for literal text.
- After every action, wait on expected pane text with `.agents/skills/verify-saber-tui/scripts/pane-wait.sh`, never a fixed sleep.
- Anchor on stable strings: page headings, the `[n/9]` header indicator, footer hints, and text you typed.
- Gallery pages are reached from the Welcome page by pressing Tab once per zero-based page index, or through the command palette `Go to:` actions.
- Treat every command as literal. Keep quoted text unchanged.

## Proof and skip reporting

- Capture the pane before the action and after the wait succeeds, plain and `-e` (ANSI) variants.
- For chat history, also capture scrollback with `-S -`.
- Record the feature ID and entry point used with every artifact.
- Report an unreachable path with the attempted command and the unmet precondition.
- Do not report a skipped entry point as verified through a different path.

## Feature entry contract

Each feature file starts with an H1 title and one paragraph describing the user-visible behavior, then exactly four H2 sections in this order:

1. `Sub-features` lists short IDs with one line for each behavior.
2. `How to get to it (user POV)` lists every user entry point.
3. `Driving it with tmux` starts with `Preconditions:` and pairs each user action with an exact command and observable result.
4. `Gotchas` lists traps that can waste or invalidate a run.

## Features

- [Chat: send and stream a message](./chat-streaming.md) covers sending, word-by-word streamed markdown, scrollback history, and quit.
- [Gallery: page navigation](./gallery-paging.md) covers Tab/Shift+Tab paging, clamping at the first and last page, and the header/footer frame.
- [Gallery: editor page](./gallery-editor.md) covers typing, submit, the transcript, input history, and slash-command autocomplete.
- [Gallery: overlays](./gallery-overlays.md) covers the centered modal, the command palette, closing, and palette navigation.
- [Gallery: markdown streaming](./gallery-markdown.md) covers the auto-streaming markdown page and the `r` replay.
