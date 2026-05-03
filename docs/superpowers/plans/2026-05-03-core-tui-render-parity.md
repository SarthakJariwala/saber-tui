# Core TUI Render Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add async/coalesced core TUI rendering and deeper non-image differential redraw parity with upstream `pi-tui`.

**Architecture:** `TUI.request_render()` becomes a scheduling API backed by a pending flag, timer, and `flush_render()` test hook. Rendering tracks logical viewport state and writes the smallest safe terminal update, falling back to full redraw only for unsafe cases. Image protocol and cell-size behavior stay out of scope.

**Tech Stack:** Python 3.12, `threading.Timer`, `time.monotonic`, `pytest`, `pyte` virtual terminal, optional `tmux` smoke testing.

---

## File Structure

- Modify `src/saber_tui/tui.py`: scheduler state, public controls, render state tracking, differential redraw, stop behavior, diagnostics.
- Modify `tests/test_tui_render.py`: deterministic unit tests for scheduler, forced renders, redraw paths, cursor controls, and exit behavior.
- Add `tests/test_tui_tmux_smoke.py`: optional tmux integration smoke test skipped when `tmux` is unavailable.
- Keep `missing.md` untracked and update it after implementation to remove addressed core items.

## Task 1: Async Render Scheduler

**Files:**
- Modify: `src/saber_tui/tui.py`
- Test: `tests/test_tui_render.py`

- [ ] **Step 1: Write failing tests**

Add tests that prove normal render requests are coalesced and forced renders cancel stale timers:

```python
def test_request_render_is_scheduled_until_flush() -> None:
    terminal = VirtualTerminal(columns=20, rows=5)
    component = StaticComponent(["one"])
    tui = TUI(terminal)
    tui.add_child(component)
    tui.start()
    tui.flush_render()
    terminal.clear_writes()

    component.lines = ["two"]
    tui.request_render()

    assert terminal.get_viewport()[0] == "one"
    tui.flush_render()
    assert terminal.get_viewport()[0] == "two"


def test_multiple_request_render_calls_coalesce_to_one_render() -> None:
    terminal = VirtualTerminal(columns=20, rows=5)
    component = CountingComponent(["one"])
    tui = TUI(terminal)
    tui.add_child(component)
    tui.start()
    tui.flush_render()
    component.render_calls = 0

    component.lines = ["two"]
    tui.request_render()
    component.lines = ["three"]
    tui.request_render()
    tui.flush_render()

    assert component.render_calls == 1
    assert terminal.get_viewport()[0] == "three"
```

- [ ] **Step 2: Verify red**

Run: `uv run pytest tests/test_tui_render.py::test_request_render_is_scheduled_until_flush tests/test_tui_render.py::test_multiple_request_render_calls_coalesce_to_one_render -q`

Expected: both tests fail because `request_render()` currently renders synchronously and `flush_render()` does not exist.

- [ ] **Step 3: Implement minimal scheduler**

Add state to `TUI.__init__`:

```python
self._render_requested = False
self._render_timer: threading.Timer | None = None
self._render_lock = threading.RLock()
self._last_render_at = 0.0
self.min_render_interval_ms = 16
```

Change `request_render()` to set `_render_requested`, schedule a timer, and return. Add `flush_render()` that cancels any pending timer and runs `_do_render()` synchronously when pending. Keep `start()` calling `request_render()` followed by `flush_render()` so startup still paints immediately.

- [ ] **Step 4: Verify green**

Run: `uv run pytest tests/test_tui_render.py -q`

Expected: render tests pass.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/saber_tui/tui.py tests/test_tui_render.py docs/superpowers/specs/2026-05-03-core-tui-render-parity-design.md docs/superpowers/plans/2026-05-03-core-tui-render-parity.md
git commit -m "feat: schedule tui renders asynchronously"
```

## Task 2: Core Runtime Controls

**Files:**
- Modify: `src/saber_tui/tui.py`
- Test: `tests/test_tui_render.py`

- [ ] **Step 1: Write failing tests**

Add tests for `get_clear_on_shrink()`, `set_clear_on_shrink()`, `get_show_hardware_cursor()`, `set_show_hardware_cursor()`, and scrollback clear:

```python
def test_full_clear_clears_scrollback() -> None:
    terminal = VirtualTerminal(columns=20, rows=5)
    tui = TUI(terminal)
    tui.add_child(StaticComponent(["hello"]))
    tui.start()
    tui.flush_render()
    terminal.clear_writes()

    tui.request_render(force=True)
    tui.flush_render()

    assert any("\x1b[2J\x1b[H\x1b[3J" in write for write in terminal.writes)


def test_hardware_cursor_can_be_toggled_at_runtime() -> None:
    terminal = VirtualTerminal(columns=20, rows=5)
    tui = TUI(terminal)
    tui.add_child(StaticComponent([f"ab{CURSOR_MARKER}cd"]))
    tui.start()
    tui.flush_render()

    assert tui.get_show_hardware_cursor() is False
    tui.set_show_hardware_cursor(True)
    tui.flush_render()

    assert tui.get_show_hardware_cursor() is True
    assert terminal.writes[-1].endswith("\x1b[?25h")
```

- [ ] **Step 2: Verify red**

Run: `uv run pytest tests/test_tui_render.py::test_full_clear_clears_scrollback tests/test_tui_render.py::test_hardware_cursor_can_be_toggled_at_runtime -q`

Expected: tests fail because the methods and scrollback clear are absent.

- [ ] **Step 3: Implement controls**

Add:

```python
def get_clear_on_shrink(self) -> bool: ...
def set_clear_on_shrink(self, enabled: bool) -> None: ...
def get_show_hardware_cursor(self) -> bool: ...
def set_show_hardware_cursor(self, enabled: bool) -> None: ...
```

Default `clear_on_shrink` to `False`, matching upstream’s default. Add `\x1b[3J` to full clear buffers.

- [ ] **Step 4: Verify green**

Run: `uv run pytest tests/test_tui_render.py -q`

Expected: render tests pass.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/saber_tui/tui.py tests/test_tui_render.py
git commit -m "feat: add tui core render controls"
```

## Task 3: Viewport State And Differential Redraw

**Files:**
- Modify: `src/saber_tui/tui.py`
- Test: `tests/test_tui_render.py`

- [ ] **Step 1: Write failing tests**

Add tests for appended lines, trailing deletion, changed line above viewport, and clear-on-shrink:

```python
def test_appending_below_viewport_scrolls_without_full_clear() -> None:
    terminal = VirtualTerminal(columns=20, rows=3)
    component = StaticComponent(["one", "two", "three"])
    tui = TUI(terminal)
    tui.add_child(component)
    tui.start()
    tui.flush_render()
    terminal.clear_writes()

    component.lines = ["one", "two", "three", "four"]
    tui.request_render()
    tui.flush_render()

    assert terminal.get_viewport() == ["two", "three", "four"]
    assert not any("\x1b[2J" in write for write in terminal.writes)


def test_deleting_trailing_lines_clears_visible_stale_rows() -> None:
    terminal = VirtualTerminal(columns=20, rows=5)
    component = StaticComponent(["one", "two", "three"])
    tui = TUI(terminal)
    tui.add_child(component)
    tui.start()
    tui.flush_render()
    terminal.clear_writes()

    component.lines = ["one"]
    tui.request_render()
    tui.flush_render()

    assert terminal.get_viewport()[0] == "one"
    assert terminal.get_viewport()[1] == ""
    assert not any("\x1b[2J" in write for write in terminal.writes)
```

- [ ] **Step 2: Verify red**

Run focused tests and confirm failures show full redraw or stale rows.

- [ ] **Step 3: Implement render state**

Add `_cursor_row`, `_max_lines_rendered`, and `_previous_viewport_top`. Rework `_write_changed_lines()` to compute first/last changed line, append starts, previous viewport bottom, relative movement from `_hardware_cursor_row`, stale-row clearing, and full redraw fallbacks when changes are above the previous viewport.

- [ ] **Step 4: Verify green**

Run: `uv run pytest tests/test_tui_render.py tests/test_tui_overlay.py -q`

Expected: render and overlay tests pass.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/saber_tui/tui.py tests/test_tui_render.py
git commit -m "feat: improve tui differential redraw"
```

## Task 4: Stop Behavior And Diagnostics

**Files:**
- Modify: `src/saber_tui/tui.py`
- Test: `tests/test_tui_render.py`

- [ ] **Step 1: Write failing tests**

Add stop and diagnostics tests:

```python
def test_stop_cancels_pending_render_and_places_cursor_after_content() -> None:
    terminal = VirtualTerminal(columns=20, rows=5)
    component = StaticComponent(["one", "two"])
    tui = TUI(terminal)
    tui.add_child(component)
    tui.start()
    tui.flush_render()
    terminal.clear_writes()

    component.lines = ["changed"]
    tui.request_render()
    tui.stop()

    joined = "".join(terminal.writes)
    assert "changed" not in joined
    assert "\r\n" in joined
    assert "\x1b[?25h" in joined
```

- [ ] **Step 2: Verify red**

Run the focused test and confirm pending renders are not cancelled or cursor placement is missing.

- [ ] **Step 3: Implement stop/diagnostics**

Cancel render timers in `stop()`, move to the line after rendered content, show cursor, then stop terminal. Add best-effort debug logging gated by `SABER_TUI_DEBUG_REDRAW=1` and `SABER_TUI_DEBUG=1`; add crash logging for over-wide lines under `/tmp/saber-tui`.

- [ ] **Step 4: Verify green**

Run: `uv run pytest tests/test_tui_render.py -q`

Expected: tests pass.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/saber_tui/tui.py tests/test_tui_render.py
git commit -m "feat: harden tui stop and render diagnostics"
```

## Task 5: tmux Smoke Test

**Files:**
- Add: `tests/test_tui_tmux_smoke.py`

- [ ] **Step 1: Write skipped-when-unavailable test**

Create a pytest test that skips when `tmux` is not found, runs a tiny Saber TUI script in a detached tmux session, captures the pane, resizes it, sends one key, and asserts the pane contains the changed content.

- [ ] **Step 2: Verify red/skip**

Run: `uv run pytest tests/test_tui_tmux_smoke.py -q`

Expected: skip if tmux is unavailable, or fail until the script and render flushing are correct.

- [ ] **Step 3: Implement smoke script inside the test**

Use `subprocess.run()` with timeouts and cleanup in `finally`. Do not require network or external services.

- [ ] **Step 4: Verify green/skip**

Run: `uv run pytest tests/test_tui_tmux_smoke.py -q`

Expected: pass where tmux is installed, skip otherwise.

- [ ] **Step 5: Commit**

Run:

```bash
git add tests/test_tui_tmux_smoke.py
git commit -m "test: add tui tmux smoke coverage"
```

## Task 6: Final Verification And missing.md

**Files:**
- Modify: `missing.md` but do not commit it.

- [ ] **Step 1: Run full verification**

Run:

```bash
uv run pytest -q
uv run ruff check
uvx ty check src/saber_tui tests
```

- [ ] **Step 2: Update `missing.md`**

Remove addressed core TUI bullets only:

- render coalescing and throttling;
- forced render scheduling;
- viewport tracking;
- differential rendering;
- scrollback clearing;
- clear-on-shrink;
- runtime hardware cursor controls;
- exit cursor placement;
- debug logging;
- crash logging.

Keep image-related and cell-size bullets.

- [ ] **Step 3: Check status**

Run: `git status --short --branch`

Expected: branch contains committed implementation changes, with only `missing.md` untracked or modified and intentionally uncommitted.
