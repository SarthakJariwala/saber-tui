---
name: verify-saber-tui
description: Drives the saber-tui examples (streaming chat demo and 9-page component gallery) in isolated tmux sessions to prove TUI behavior end to end. Use when verifying rendering, key handling, focus, overlays, the editor, or markdown streaming in this repo the way a user sees them.
---

# Verify saber-tui

saber-tui is a library, so verification drives its runnable examples: `examples/chat.py` (streaming chat) and `examples/showcase.py` (component gallery). Each drive runs one example in its own tmux session, sends real keystrokes, and proves state from pane captures. The maintained list of user-facing behavior lives in [features/](features/README.md); read it before driving.

The pyte harness in `tests/virtual_terminal.py` is for unit tests. It bypasses `ProcessTerminal` and real key delivery, so it is not proof of user-visible behavior. Prove with tmux.

## Launch

There is no server. Install dependencies once, then start each drive in its own session. Run everything from the repo root.

```sh
uv sync                       # once per checkout
run_id=$(date +%s)
session="saber_verify_$run_id"
tmux new-session -d -x 100 -y 30 -c "$PWD" -s "$session" "$(command -v uv) run python examples/showcase.py"
.agents/skills/verify-saber-tui/scripts/pane-wait.sh "$session" "Welcome to the Saber TUI Component Gallery" 20
```

For the chat demo, launch `examples/chat.py` instead and wait for `Type a message`. Ready means the wait prints a pane containing that text. Embed `$(command -v uv)` as shown; the tmux server may not share your PATH. Teardown is in Cleanup.

## Doctor

Run this read-only check first whenever anything looks off:

```sh
uv --version && tmux -V \
  && uv run python -c "import saber_tui; print('saber_tui import ok')" \
  && { tmux ls 2>/dev/null | grep saber_verify_ || echo "no stale verify sessions"; }
```

All four lines must succeed. Stale `saber_verify_*` sessions belong to a crashed earlier run; kill them by name before driving. If `uv` is missing, install it (`pip install --user uv`) rather than substituting pip.

## Drive

Send keys to the session; the examples bind them as follows.

```sh
tmux send-keys -t "$session" Tab          # next gallery page
tmux send-keys -t "$session" BTab         # previous gallery page (Shift+Tab)
tmux send-keys -t "$session" C-p          # command palette overlay
tmux send-keys -t "$session" Escape       # close overlay (C-g also works)
tmux send-keys -t "$session" -l "hello"   # literal text; -l stops tmux interpreting it
tmux send-keys -t "$session" Enter        # submit editor / run palette action
tmux send-keys -t "$session" C-c          # quit either example
```

After every action, wait on the expected text instead of sleeping:

```sh
.agents/skills/verify-saber-tui/scripts/pane-wait.sh "$session" "expected text" 10
```

Anchor waits on stable strings: page headings from `PAGE_TITLES` in `examples/showcase.py`, the header page indicator like `[4/9]`, footer hints, or message text you sent. Never anchor on colors or column positions.

## Evidence

Proof standards:

- Exercise the real user path: keystrokes through tmux into the running example. Never call app functions, use the pyte harness, or pre-seed state and call it a user proof.
- Capture the action and the resulting state: a pane capture before the action, the keys sent, and a capture after the wait succeeds, not just the final screen.
- The examples write nothing to disk, so screen state is the observable side effect. For chat history, capture scrollback too (`-S -`), because completed turns leave the live pane by design.
- No mocks; the examples have no external boundaries.

Save captures under an evidence directory that outlives the run, default `/tmp/saber-verify/$run_id` (in an Amp orb prefer `.amp/in/artifacts/saber-verify/$run_id` so the user can review):

```sh
ev="/tmp/saber-verify/$run_id"; mkdir -p "$ev"
tmux capture-pane -pt "$session"        > "$ev/03-editor-after-submit.txt"
tmux capture-pane -pet "$session"       > "$ev/03-editor-after-submit.ansi.txt"   # with colors
tmux capture-pane -pt "$session" -S -   > "$ev/04-chat-scrollback.txt"            # include history
```

Name files `<step>-<feature-id>-<what>.txt` and record in your report which feature file and entry point each capture proves.

## Cleanup

Kill only the sessions this run created, by exact name:

```sh
tmux kill-session -t "$session"
```

If the example already exited (Ctrl+C ends the process and tmux closes the session), kill-session failing with "session not found" is fine. Never `pkill python` and never kill sessions you did not start; other agents and the Amp terminal share this machine. Evidence under `/tmp/saber-verify/` (or the artifacts dir) is not scratch state; leave it in place.

Isolation: any number of drives can run side by side. Each gets its own `$run_id`, session, and evidence dir; the examples share no files or ports.

## Helpers

`scripts/pane-wait.sh SESSION TEXT [TIMEOUT_SECONDS]` polls `tmux capture-pane` until TEXT appears, prints the pane, and exits 0; on timeout it prints the last pane to stdout, a diagnostic to stderr, and exits 1. Default timeout 10s. Streaming pages need up to 20s.
