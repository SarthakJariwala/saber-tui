# Faithful Python TUI Port Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first faithful low-level Python port of `badlogic/pi-mono/packages/tui/src` as a tested `saber_tui` package managed by `uv`.

**Architecture:** Components render ANSI strings to width-bounded line lists. `TUI` owns component composition, overlays, focus, cursor marker extraction, render scheduling, and differential terminal writes. `Terminal` owns raw process I/O, bracketed paste, stdin sequence buffering, resize events, and ANSI terminal operations.

**Tech Stack:** Python 3.12+, `uv`, `wcwidth`, `regex`, `pytest`, `pyte`, `ruff`.

---

## Source References

Keep the upstream clone available at `/tmp/pi-mono`. Read these files before the matching port task:

- `/tmp/pi-mono/packages/tui/src/utils.ts`
- `/tmp/pi-mono/packages/tui/src/stdin-buffer.ts`
- `/tmp/pi-mono/packages/tui/src/keys.ts`
- `/tmp/pi-mono/packages/tui/src/keybindings.ts`
- `/tmp/pi-mono/packages/tui/src/tui.ts`
- `/tmp/pi-mono/packages/tui/src/terminal.ts`
- `/tmp/pi-mono/packages/tui/src/components/text.ts`
- `/tmp/pi-mono/packages/tui/src/components/truncated-text.ts`
- `/tmp/pi-mono/packages/tui/src/components/box.ts`
- `/tmp/pi-mono/packages/tui/src/components/spacer.ts`
- `/tmp/pi-mono/packages/tui/src/components/input.ts`
- `/tmp/pi-mono/packages/tui/src/components/select-list.ts`
- `/tmp/pi-mono/packages/tui/src/components/loader.ts`
- `/tmp/pi-mono/packages/tui/src/components/cancellable-loader.ts`
- `/tmp/pi-mono/packages/tui/src/kill-ring.ts`
- `/tmp/pi-mono/packages/tui/src/undo-stack.ts`
- `/tmp/pi-mono/packages/tui/src/fuzzy.ts`
- `/tmp/pi-mono/packages/tui/test/virtual-terminal.ts`

## File Structure

Create these package files:

- `pyproject.toml`: uv project metadata, dependencies, pytest and ruff config.
- `README.md`: quick usage and supported scope for the first parity slice.
- `src/saber_tui/__init__.py`: public exports.
- `src/saber_tui/utils.py`: ANSI parsing, width, wrapping, truncation, slicing, compositing helpers.
- `src/saber_tui/stdin_buffer.py`: buffered terminal input sequence parser.
- `src/saber_tui/keys.py`: key ids, key matching, parsing, printable decoding, Kitty and modifyOtherKeys support.
- `src/saber_tui/keybindings.py`: default keybinding registry and conflict reporting.
- `src/saber_tui/kill_ring.py`: Emacs-style kill ring used by inputs.
- `src/saber_tui/undo_stack.py`: bounded undo stack helper.
- `src/saber_tui/fuzzy.py`: fuzzy match and filter helpers.
- `src/saber_tui/terminal.py`: `Terminal` protocol and `ProcessTerminal`.
- `src/saber_tui/tui.py`: `Component`, `Focusable`, `Container`, overlays, and `TUI`.
- `src/saber_tui/components/__init__.py`: component exports.
- `src/saber_tui/components/text.py`: `Text`.
- `src/saber_tui/components/truncated_text.py`: `TruncatedText`.
- `src/saber_tui/components/box.py`: `Box`.
- `src/saber_tui/components/spacer.py`: `Spacer`.
- `src/saber_tui/components/input.py`: `Input`.
- `src/saber_tui/components/select_list.py`: `SelectList`.
- `src/saber_tui/components/loader.py`: `Loader`.
- `src/saber_tui/components/cancellable_loader.py`: `CancellableLoader`.
- `tests/virtual_terminal.py`: `pyte`-backed test terminal.
- `tests/test_*.py`: focused pytest suites for each module.
- `examples/chat_simple.py`: minimal interactive example.

## Task 1: Project Scaffold

**Files:**

- Create: `pyproject.toml`
- Create: `README.md`
- Create: `src/saber_tui/__init__.py`
- Create: `src/saber_tui/components/__init__.py`
- Create: `tests/test_imports.py`

- [ ] **Step 1: Initialize the uv package**

Run:

```bash
uv init --package --name saber-tui --python 3.12
```

Expected:

```text
Initialized project `saber-tui`
```

- [ ] **Step 2: Add runtime dependencies**

Run:

```bash
uv add wcwidth regex
```

Expected: `pyproject.toml` includes `wcwidth` and `regex` under dependencies.

- [ ] **Step 3: Add dev dependencies**

Run:

```bash
uv add --dev pytest pyte ruff
```

Expected: `pyproject.toml` includes `pytest`, `pyte`, and `ruff` in the dev dependency group.

- [ ] **Step 4: Replace `pyproject.toml` with project config**

Use this final structure, preserving exact dependency versions selected by `uv` in the lockfile:

```toml
[project]
name = "saber-tui"
version = "0.1.0"
description = "Faithful low-level Python port of pi-tui"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "regex",
    "wcwidth",
]

[dependency-groups]
dev = [
    "pyte",
    "pytest",
    "ruff",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/saber_tui"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]

[tool.ruff]
line-length = 120
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]
```

- [ ] **Step 5: Create public export files**

Create `src/saber_tui/__init__.py`:

```python
"""Faithful low-level Python port of pi-tui."""

from saber_tui.keybindings import KeybindingConflict, KeybindingsManager, get_keybindings, set_keybindings
from saber_tui.keys import decode_printable_key, is_key_release, is_key_repeat, matches_key, parse_key
from saber_tui.terminal import ProcessTerminal, Terminal
from saber_tui.tui import CURSOR_MARKER, Component, Container, Focusable, OverlayHandle, OverlayOptions, TUI

__all__ = [
    "CURSOR_MARKER",
    "Component",
    "Container",
    "Focusable",
    "KeybindingConflict",
    "KeybindingsManager",
    "OverlayHandle",
    "OverlayOptions",
    "ProcessTerminal",
    "TUI",
    "Terminal",
    "decode_printable_key",
    "get_keybindings",
    "is_key_release",
    "is_key_repeat",
    "matches_key",
    "parse_key",
    "set_keybindings",
]
```

Create `src/saber_tui/components/__init__.py`:

```python
from saber_tui.components.box import Box
from saber_tui.components.cancellable_loader import CancellableLoader
from saber_tui.components.input import Input
from saber_tui.components.loader import Loader
from saber_tui.components.select_list import SelectItem, SelectList
from saber_tui.components.spacer import Spacer
from saber_tui.components.text import Text
from saber_tui.components.truncated_text import TruncatedText

__all__ = [
    "Box",
    "CancellableLoader",
    "Input",
    "Loader",
    "SelectItem",
    "SelectList",
    "Spacer",
    "Text",
    "TruncatedText",
]
```

- [ ] **Step 6: Create a smoke import test**

Create `tests/test_imports.py`:

```python
def test_package_imports() -> None:
    import saber_tui

    assert saber_tui.__all__
```

- [ ] **Step 7: Run the smoke test and observe the expected failure**

Run:

```bash
uv run pytest tests/test_imports.py -q
```

Expected: FAIL because exported modules are not created.

- [ ] **Step 8: Add empty module shells with import-safe names**

Create empty files for every package module listed in the file structure. For modules that are imported by `__init__.py`, define minimal names so imports succeed:

```python
# src/saber_tui/terminal.py
from typing import Protocol


class Terminal(Protocol):
    pass


class ProcessTerminal:
    pass
```

```python
# src/saber_tui/tui.py
from typing import Protocol

CURSOR_MARKER = "\x1b_pi:c\x07"


class Component(Protocol):
    pass


class Focusable(Protocol):
    focused: bool


class Container:
    pass


class TUI(Container):
    pass


class OverlayOptions(dict):
    pass


class OverlayHandle(Protocol):
    pass
```

```python
# src/saber_tui/keys.py
def matches_key(data: str, key_id: str) -> bool:
    return False


def parse_key(data: str) -> str | None:
    return None


def is_key_release(data: str) -> bool:
    return False


def is_key_repeat(data: str) -> bool:
    return False


def decode_printable_key(data: str) -> str | None:
    return None
```

```python
# src/saber_tui/keybindings.py
from dataclasses import dataclass


@dataclass(frozen=True)
class KeybindingConflict:
    key: str
    keybindings: list[str]


class KeybindingsManager:
    pass


def get_keybindings() -> KeybindingsManager:
    return KeybindingsManager()


def set_keybindings(keybindings: KeybindingsManager) -> None:
    return None
```

- [ ] **Step 9: Run the smoke test and verify it passes**

Run:

```bash
uv run pytest tests/test_imports.py -q
```

Expected: PASS.

- [ ] **Step 10: Commit the scaffold**

Run:

```bash
git add pyproject.toml uv.lock README.md src tests
git commit -m "chore: scaffold uv python package"
```

Expected: commit succeeds.

## Task 2: Support Primitives

**Files:**

- Create: `src/saber_tui/kill_ring.py`
- Create: `src/saber_tui/undo_stack.py`
- Create: `src/saber_tui/fuzzy.py`
- Test: `tests/test_kill_ring.py`
- Test: `tests/test_undo_stack.py`
- Test: `tests/test_fuzzy.py`

- [ ] **Step 1: Write kill ring tests**

Create `tests/test_kill_ring.py`:

```python
from saber_tui.kill_ring import KillRing


def test_push_and_peek_latest_text() -> None:
    ring = KillRing()
    ring.push("first")
    ring.push("second")

    assert ring.peek() == "second"
    assert len(ring) == 2


def test_rotate_cycles_entries() -> None:
    ring = KillRing()
    ring.push("first")
    ring.push("second")
    ring.push("third")

    ring.rotate()
    assert ring.peek() == "second"
    ring.rotate()
    assert ring.peek() == "first"
    ring.rotate()
    assert ring.peek() == "third"


def test_accumulate_appends_or_prepends_to_latest_entry() -> None:
    ring = KillRing()
    ring.push("world")
    ring.push("hello ", prepend=True, accumulate=True)
    assert ring.peek() == "hello world"

    ring.push("!", prepend=False, accumulate=True)
    assert ring.peek() == "hello world!"
```

- [ ] **Step 2: Run kill ring tests and verify failure**

Run:

```bash
uv run pytest tests/test_kill_ring.py -q
```

Expected: FAIL because `KillRing` is not implemented.

- [ ] **Step 3: Implement `KillRing`**

Replace `src/saber_tui/kill_ring.py`:

```python
from __future__ import annotations


class KillRing:
    def __init__(self, max_size: int = 60) -> None:
        self._max_size = max(1, max_size)
        self._entries: list[str] = []

    def __len__(self) -> int:
        return len(self._entries)

    def push(self, text: str, *, prepend: bool = False, accumulate: bool = False) -> None:
        if text == "":
            return
        if accumulate and self._entries:
            current = self._entries[0]
            self._entries[0] = text + current if prepend else current + text
            return
        self._entries.insert(0, text)
        del self._entries[self._max_size :]

    def peek(self) -> str | None:
        return self._entries[0] if self._entries else None

    def rotate(self) -> None:
        if len(self._entries) <= 1:
            return
        first = self._entries.pop(0)
        self._entries.append(first)
```

- [ ] **Step 4: Run kill ring tests and verify pass**

Run:

```bash
uv run pytest tests/test_kill_ring.py -q
```

Expected: PASS.

- [ ] **Step 5: Write undo stack tests**

Create `tests/test_undo_stack.py`:

```python
from saber_tui.undo_stack import UndoStack


def test_pop_returns_latest_snapshot() -> None:
    stack: UndoStack[dict[str, int]] = UndoStack()
    stack.push({"cursor": 1})
    stack.push({"cursor": 2})

    assert stack.pop() == {"cursor": 2}
    assert stack.pop() == {"cursor": 1}
    assert stack.pop() is None


def test_max_size_discards_oldest_snapshot() -> None:
    stack: UndoStack[int] = UndoStack(max_size=2)
    stack.push(1)
    stack.push(2)
    stack.push(3)

    assert stack.pop() == 3
    assert stack.pop() == 2
    assert stack.pop() is None
```

- [ ] **Step 6: Implement `UndoStack`**

Replace `src/saber_tui/undo_stack.py`:

```python
from __future__ import annotations

from typing import Generic, TypeVar

T = TypeVar("T")


class UndoStack(Generic[T]):
    def __init__(self, max_size: int = 100) -> None:
        self._max_size = max(1, max_size)
        self._items: list[T] = []

    def push(self, item: T) -> None:
        self._items.append(item)
        if len(self._items) > self._max_size:
            del self._items[0 : len(self._items) - self._max_size]

    def pop(self) -> T | None:
        if not self._items:
            return None
        return self._items.pop()

    def clear(self) -> None:
        self._items.clear()
```

- [ ] **Step 7: Write fuzzy tests**

Create `tests/test_fuzzy.py`:

```python
from saber_tui.fuzzy import fuzzy_filter, fuzzy_match


def test_fuzzy_match_scores_ordered_subsequence() -> None:
    match = fuzzy_match("slt", "select-list")

    assert match is not None
    assert match.value == "select-list"
    assert match.indices == [0, 2, 5]
    assert match.score > 0


def test_fuzzy_match_rejects_missing_characters() -> None:
    assert fuzzy_match("xyz", "select-list") is None


def test_fuzzy_filter_orders_better_matches_first() -> None:
    result = fuzzy_filter("sl", ["settings-list", "select-list", "box"])

    assert [item.value for item in result] == ["select-list", "settings-list"]
```

- [ ] **Step 8: Implement fuzzy matching**

Replace `src/saber_tui/fuzzy.py`:

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FuzzyMatch:
    value: str
    score: int
    indices: list[int]


def fuzzy_match(query: str, value: str) -> FuzzyMatch | None:
    if query == "":
        return FuzzyMatch(value=value, score=0, indices=[])

    q = query.lower()
    v = value.lower()
    indices: list[int] = []
    search_from = 0
    for char in q:
        index = v.find(char, search_from)
        if index == -1:
            return None
        indices.append(index)
        search_from = index + 1

    score = 1000
    score -= indices[0] * 10
    score -= (indices[-1] - indices[0] + 1 - len(indices)) * 5
    for previous, current in zip(indices, indices[1:], strict=False):
        if current == previous + 1:
            score += 20
    if value[indices[0]].isupper() or indices[0] == 0:
        score += 10
    return FuzzyMatch(value=value, score=score, indices=indices)


def fuzzy_filter(query: str, values: list[str]) -> list[FuzzyMatch]:
    matches = [match for value in values if (match := fuzzy_match(query, value)) is not None]
    return sorted(matches, key=lambda match: (-match.score, match.value))
```

- [ ] **Step 9: Run primitive tests**

Run:

```bash
uv run pytest tests/test_kill_ring.py tests/test_undo_stack.py tests/test_fuzzy.py -q
```

Expected: PASS.

- [ ] **Step 10: Commit support primitives**

Run:

```bash
git add src/saber_tui/kill_ring.py src/saber_tui/undo_stack.py src/saber_tui/fuzzy.py tests/test_kill_ring.py tests/test_undo_stack.py tests/test_fuzzy.py
git commit -m "feat: add support primitives"
```

Expected: commit succeeds.

## Task 3: ANSI and Width Utilities

**Files:**

- Create: `src/saber_tui/utils.py`
- Test: `tests/test_utils.py`

- [ ] **Step 1: Write utility tests**

Create `tests/test_utils.py`:

```python
from saber_tui.utils import (
    extract_ansi_code,
    extract_segments,
    slice_by_column,
    truncate_to_width,
    visible_width,
    wrap_text_with_ansi,
)


def test_visible_width_handles_ascii_cjk_emoji_and_ansi() -> None:
    assert visible_width("abc") == 3
    assert visible_width("コン") == 4
    assert visible_width("a\x1b[31mb\x1b[0m") == 2
    assert visible_width("👩‍💻") == 2


def test_extract_ansi_code_supports_csi_osc_and_apc() -> None:
    assert extract_ansi_code("\x1b[31mred", 0) == ("\x1b[31m", 5)
    assert extract_ansi_code("\x1b]8;;https://example.com\x07x", 0) == (
        "\x1b]8;;https://example.com\x07",
        25,
    )
    assert extract_ansi_code("\x1b_pi:c\x07x", 0) == ("\x1b_pi:c\x07", 7)


def test_truncate_to_width_preserves_width_and_adds_reset() -> None:
    result = truncate_to_width("\x1b[31mabcdef", 4)

    assert visible_width(result) == 4
    assert result.endswith("\x1b[0m...\x1b[0m")


def test_wrap_text_with_ansi_preserves_active_style() -> None:
    lines = wrap_text_with_ansi("\x1b[31mhello world", 6)

    assert len(lines) == 2
    assert lines[1].startswith("\x1b[31m")
    assert all(visible_width(line) <= 6 for line in lines)


def test_slice_by_column_handles_wide_boundaries() -> None:
    assert slice_by_column("aコンb", 1, 2, strict=True) == "コ"
    assert slice_by_column("aコンb", 1, 1, strict=True) == ""


def test_extract_segments_preserves_before_and_after_text() -> None:
    segments = extract_segments("hello world", before_end=5, after_start=8, after_len=3)

    assert segments.before == "hello"
    assert segments.before_width == 5
    assert segments.after == "rld"
    assert segments.after_width == 3
```

- [ ] **Step 2: Run utility tests and verify failure**

Run:

```bash
uv run pytest tests/test_utils.py -q
```

Expected: FAIL because utility functions are missing.

- [ ] **Step 3: Implement utilities**

Replace `src/saber_tui/utils.py` with a Python port of upstream `utils.ts` using these exact public names:

```python
from __future__ import annotations

from dataclasses import dataclass

import regex
from wcwidth import wcwidth, wcswidth


@dataclass(frozen=True)
class SliceResult:
    text: str
    width: int


@dataclass(frozen=True)
class SegmentResult:
    before: str
    before_width: int
    after: str
    after_width: int


def graphemes(text: str) -> list[str]:
    return regex.findall(r"\X", text)


def extract_ansi_code(text: str, pos: int) -> tuple[str, int] | None:
    if pos >= len(text) or text[pos] != "\x1b":
        return None
    if pos + 1 >= len(text):
        return None
    marker = text[pos + 1]
    if marker == "[":
        index = pos + 2
        while index < len(text) and text[index] not in "mGKHJABCDF~u":
            index += 1
        if index < len(text):
            return text[pos : index + 1], index + 1 - pos
        return None
    if marker in ("]", "_", "P"):
        index = pos + 2
        while index < len(text):
            if text[index] == "\x07":
                return text[pos : index + 1], index + 1 - pos
            if text[index] == "\x1b" and index + 1 < len(text) and text[index + 1] == "\\":
                return text[pos : index + 2], index + 2 - pos
            index += 1
        return None
    return None


def strip_ansi(text: str) -> str:
    result: list[str] = []
    index = 0
    while index < len(text):
        ansi = extract_ansi_code(text, index)
        if ansi is not None:
            index += ansi[1]
            continue
        result.append(text[index])
        index += 1
    return "".join(result)


def _grapheme_width(cluster: str) -> int:
    if cluster == "\t":
        return 3
    width = wcswidth(cluster)
    if width >= 0:
        return width
    total = 0
    for char in cluster:
        char_width = wcwidth(char)
        if char_width > 0:
            total += char_width
    return total


def visible_width(text: str) -> int:
    if not text:
        return 0
    clean = strip_ansi(text).replace("\t", "   ")
    return sum(_grapheme_width(cluster) for cluster in graphemes(clean))


class _AnsiTracker:
    def __init__(self) -> None:
        self._codes: list[str] = []

    def process(self, code: str) -> None:
        if not code.startswith("\x1b[") or not code.endswith("m"):
            return
        body = code[2:-1]
        if body in ("", "0"):
            self._codes.clear()
        else:
            self._codes.append(code)

    def active(self) -> str:
        return "".join(self._codes)


def wrap_text_with_ansi(text: str, width: int) -> list[str]:
    if text == "":
        return [""]
    lines: list[str] = []
    tracker = _AnsiTracker()
    for raw_line in text.split("\n"):
        current = tracker.active()
        current_width = visible_width(current)
        for token in regex.findall(r"\s+|\S+", raw_line):
            token_width = visible_width(token)
            if current_width > 0 and current_width + token_width > width:
                lines.append(current.rstrip())
                current = tracker.active()
                current_width = visible_width(current)
                if token.isspace():
                    continue
            while token_width > width:
                chunk = slice_by_column(token, 0, width, strict=True)
                lines.append(tracker.active() + chunk)
                token = token[len(strip_ansi(chunk)) :]
                token_width = visible_width(token)
            current += token
            current_width = visible_width(current)
            index = 0
            while index < len(token):
                ansi = extract_ansi_code(token, index)
                if ansi is not None:
                    tracker.process(ansi[0])
                    index += ansi[1]
                else:
                    index += 1
        lines.append(current.rstrip())
    return lines or [""]


def truncate_to_width(text: str, max_width: int, ellipsis: str = "...", pad: bool = False) -> str:
    if max_width <= 0:
        return ""
    text_width = visible_width(text)
    if text_width <= max_width:
        return text + (" " * (max_width - text_width) if pad else "")
    ellipsis_width = visible_width(ellipsis)
    target = max(0, max_width - ellipsis_width)
    prefix = slice_by_column(text, 0, target, strict=True)
    result = f"{prefix}\x1b[0m{ellipsis}\x1b[0m"
    if pad:
        result += " " * max(0, max_width - visible_width(result))
    return result


def slice_with_width(line: str, start_col: int, length: int, strict: bool = False) -> SliceResult:
    if length <= 0:
        return SliceResult("", 0)
    end_col = start_col + length
    result: list[str] = []
    result_width = 0
    current_col = 0
    pending_ansi = ""
    index = 0
    while index < len(line):
        ansi = extract_ansi_code(line, index)
        if ansi is not None:
            if start_col <= current_col < end_col:
                result.append(ansi[0])
            elif current_col < start_col:
                pending_ansi += ansi[0]
            index += ansi[1]
            continue
        cluster = graphemes(line[index:])[0]
        width = _grapheme_width(cluster)
        in_range = start_col <= current_col < end_col
        fits = not strict or current_col + width <= end_col
        if in_range and fits:
            if pending_ansi:
                result.append(pending_ansi)
                pending_ansi = ""
            result.append(cluster)
            result_width += width
        current_col += width
        index += len(cluster)
        if current_col >= end_col:
            break
    return SliceResult("".join(result), result_width)


def slice_by_column(line: str, start_col: int, length: int, strict: bool = False) -> str:
    return slice_with_width(line, start_col, length, strict).text


def extract_segments(
    line: str,
    before_end: int,
    after_start: int,
    after_len: int,
    strict_after: bool = False,
) -> SegmentResult:
    before = slice_with_width(line, 0, before_end, strict=False)
    after = slice_with_width(line, after_start, after_len, strict_after)
    return SegmentResult(before.text, before.width, after.text, after.width)


def apply_background_to_line(line: str, width: int, bg_fn) -> str:
    padding = " " * max(0, width - visible_width(line))
    return bg_fn(line + padding)


def normalize_terminal_output(text: str) -> str:
    return text.replace("\u0e33", "\u0e4d\u0e32").replace("\u0eb3", "\u0ecd\u0eb2")
```

- [ ] **Step 4: Run utility tests and refine against upstream edge cases**

Run:

```bash
uv run pytest tests/test_utils.py -q
```

Expected: PASS. If a width assertion fails for emoji or CJK, adjust `_grapheme_width` only and rerun the same command.

- [ ] **Step 5: Commit utilities**

Run:

```bash
git add src/saber_tui/utils.py tests/test_utils.py
git commit -m "feat: add ansi width utilities"
```

Expected: commit succeeds.

## Task 4: Stdin Buffer

**Files:**

- Create: `src/saber_tui/stdin_buffer.py`
- Test: `tests/test_stdin_buffer.py`

- [ ] **Step 1: Write stdin buffer tests**

Create `tests/test_stdin_buffer.py`:

```python
from saber_tui.stdin_buffer import StdinBuffer


def test_emits_plain_characters_individually() -> None:
    events: list[str] = []
    buffer = StdinBuffer(on_data=events.append)

    buffer.process("ab")

    assert events == ["a", "b"]


def test_buffers_partial_csi_sequence_until_complete() -> None:
    events: list[str] = []
    buffer = StdinBuffer(on_data=events.append)

    buffer.process("\x1b[")
    assert events == []
    buffer.process("A")

    assert events == ["\x1b[A"]


def test_emits_paste_content_separately() -> None:
    events: list[str] = []
    pastes: list[str] = []
    buffer = StdinBuffer(on_data=events.append, on_paste=pastes.append)

    buffer.process("a\x1b[200~hello\nworld\x1b[201~b")

    assert events == ["a", "b"]
    assert pastes == ["hello\nworld"]


def test_flush_emits_incomplete_sequence() -> None:
    events: list[str] = []
    buffer = StdinBuffer(on_data=events.append)

    buffer.process("\x1b[")
    assert buffer.flush() == ["\x1b["]
```

- [ ] **Step 2: Run stdin buffer tests and verify failure**

Run:

```bash
uv run pytest tests/test_stdin_buffer.py -q
```

Expected: FAIL because `StdinBuffer` is not implemented.

- [ ] **Step 3: Implement stdin buffering**

Replace `src/saber_tui/stdin_buffer.py` with a Python port of upstream `stdin-buffer.ts`. Preserve these public names:

```python
from __future__ import annotations

from collections.abc import Callable

ESC = "\x1b"
BRACKETED_PASTE_START = "\x1b[200~"
BRACKETED_PASTE_END = "\x1b[201~"


def _is_complete_sequence(data: str) -> str:
    if not data.startswith(ESC):
        return "not-escape"
    if len(data) == 1:
        return "incomplete"
    after = data[1:]
    if after.startswith("["):
        if after.startswith("[M"):
            return "complete" if len(data) >= 6 else "incomplete"
        if len(data) < 3:
            return "incomplete"
        final = data[-1]
        if 0x40 <= ord(final) <= 0x7E:
            return "complete"
        return "incomplete"
    if after.startswith(("]", "P", "_")):
        return "complete" if data.endswith("\x07") or data.endswith("\x1b\\") else "incomplete"
    if after.startswith("O"):
        return "complete" if len(after) >= 2 else "incomplete"
    if len(after) == 1:
        return "complete"
    return "complete"


def _extract_complete_sequences(buffer: str) -> tuple[list[str], str]:
    sequences: list[str] = []
    pos = 0
    while pos < len(buffer):
        remaining = buffer[pos:]
        if remaining.startswith(ESC):
            seq_end = 1
            while seq_end <= len(remaining):
                candidate = remaining[:seq_end]
                status = _is_complete_sequence(candidate)
                if status == "complete":
                    sequences.append(candidate)
                    pos += seq_end
                    break
                if status == "incomplete":
                    seq_end += 1
                    continue
                sequences.append(candidate)
                pos += seq_end
                break
            if seq_end > len(remaining):
                return sequences, remaining
        else:
            sequences.append(remaining[0])
            pos += 1
    return sequences, ""


class StdinBuffer:
    def __init__(
        self,
        *,
        on_data: Callable[[str], None] | None = None,
        on_paste: Callable[[str], None] | None = None,
    ) -> None:
        self._buffer = ""
        self._paste_mode = False
        self._paste_buffer = ""
        self._on_data = on_data
        self._on_paste = on_paste

    def process(self, data: str | bytes) -> None:
        text = data.decode() if isinstance(data, bytes) else data
        self._buffer += text

        if self._paste_mode:
            self._paste_buffer += self._buffer
            self._buffer = ""
            self._finish_paste_if_complete()
            return

        start_index = self._buffer.find(BRACKETED_PASTE_START)
        if start_index != -1:
            before = self._buffer[:start_index]
            sequences, _ = _extract_complete_sequences(before)
            for sequence in sequences:
                self._emit_data(sequence)
            self._paste_mode = True
            self._paste_buffer = self._buffer[start_index + len(BRACKETED_PASTE_START) :]
            self._buffer = ""
            self._finish_paste_if_complete()
            return

        sequences, remainder = _extract_complete_sequences(self._buffer)
        self._buffer = remainder
        for sequence in sequences:
            self._emit_data(sequence)

    def _finish_paste_if_complete(self) -> None:
        end_index = self._paste_buffer.find(BRACKETED_PASTE_END)
        if end_index == -1:
            return
        content = self._paste_buffer[:end_index]
        remaining = self._paste_buffer[end_index + len(BRACKETED_PASTE_END) :]
        self._paste_buffer = ""
        self._paste_mode = False
        if self._on_paste is not None:
            self._on_paste(content)
        if remaining:
            self.process(remaining)

    def _emit_data(self, sequence: str) -> None:
        if self._on_data is not None:
            self._on_data(sequence)

    def flush(self) -> list[str]:
        if not self._buffer:
            return []
        result = [self._buffer]
        self._buffer = ""
        return result

    def clear(self) -> None:
        self._buffer = ""
        self._paste_mode = False
        self._paste_buffer = ""

    def get_buffer(self) -> str:
        return self._buffer
```

- [ ] **Step 4: Run stdin buffer tests and verify pass**

Run:

```bash
uv run pytest tests/test_stdin_buffer.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit stdin buffer**

Run:

```bash
git add src/saber_tui/stdin_buffer.py tests/test_stdin_buffer.py
git commit -m "feat: add stdin sequence buffer"
```

Expected: commit succeeds.

## Task 5: Keys and Keybindings

**Files:**

- Modify: `src/saber_tui/keys.py`
- Modify: `src/saber_tui/keybindings.py`
- Test: `tests/test_keys.py`
- Test: `tests/test_keybindings.py`

- [ ] **Step 1: Write key tests**

Create `tests/test_keys.py`:

```python
from saber_tui.keys import decode_printable_key, is_key_release, matches_key, parse_key, set_kitty_protocol_active


def test_matches_legacy_control_and_arrows() -> None:
    assert matches_key("\x03", "ctrl+c")
    assert matches_key("\x1b[A", "up")
    assert matches_key("\x1b[Z", "shift+tab")


def test_parse_key_legacy_sequences() -> None:
    assert parse_key("\x03") == "ctrl+c"
    assert parse_key("\x1b[A") == "up"
    assert parse_key("\r") == "enter"


def test_matches_kitty_csi_u_modified_key() -> None:
    set_kitty_protocol_active(True)
    assert matches_key("\x1b[99;5u", "ctrl+c")
    set_kitty_protocol_active(False)


def test_release_detection() -> None:
    assert is_key_release("\x1b[99;5:3u")


def test_decode_printable_key_from_kitty() -> None:
    assert decode_printable_key("\x1b[97u") == "a"
    assert decode_printable_key("\x1b[97;5u") is None
```

- [ ] **Step 2: Port key parsing**

Replace `src/saber_tui/keys.py` with a direct Python port of upstream `keys.ts`. Keep these public functions:

```python
set_kitty_protocol_active(active: bool) -> None
is_kitty_protocol_active() -> bool
is_key_release(data: str) -> bool
is_key_repeat(data: str) -> bool
matches_key(data: str, key_id: str) -> bool
parse_key(data: str) -> str | None
decode_kitty_printable(data: str) -> str | None
decode_printable_key(data: str) -> str | None
```

Implementation requirements:

- Use the same modifier bit values as upstream: shift `1`, alt `2`, ctrl `4`, super `8`.
- Include legacy arrow, home, end, insert, delete, page, function key, alt, and ctrl sequences from upstream.
- Include Kitty CSI-u parsing for printable, arrow, functional, home/end, event type, shifted key, and base layout key forms.
- Include xterm modifyOtherKeys parsing with `CSI 27 ; modifier ; codepoint ~`.
- Preserve upstream behavior for ambiguous backspace and Kitty-mode shift-enter mappings.
- Keep key ids string-based.

- [ ] **Step 3: Run key tests and verify pass**

Run:

```bash
uv run pytest tests/test_keys.py -q
```

Expected: PASS.

- [ ] **Step 4: Write keybinding tests**

Create `tests/test_keybindings.py`:

```python
from saber_tui.keybindings import KeybindingsManager, get_keybindings, set_keybindings


def test_default_keybinding_matches_action() -> None:
    manager = KeybindingsManager()

    assert manager.matches("\x1b[A", "tui.select.up")
    assert manager.matches("\r", "tui.select.confirm")


def test_user_binding_replaces_default_keys() -> None:
    manager = KeybindingsManager({"tui.select.confirm": "ctrl+j"})

    assert manager.matches("\n", "tui.select.confirm")
    assert not manager.matches("\r", "tui.select.confirm")


def test_conflicts_report_user_claims() -> None:
    manager = KeybindingsManager({"tui.select.up": "ctrl+x", "tui.select.down": "ctrl+x"})

    conflicts = manager.get_conflicts()
    assert len(conflicts) == 1
    assert conflicts[0].key == "ctrl+x"
    assert set(conflicts[0].keybindings) == {"tui.select.up", "tui.select.down"}


def test_global_keybindings_can_be_replaced() -> None:
    custom = KeybindingsManager({"tui.select.confirm": "ctrl+j"})
    set_keybindings(custom)

    assert get_keybindings() is custom
```

- [ ] **Step 5: Implement keybindings**

Replace `src/saber_tui/keybindings.py` with the upstream action names and defaults translated to Python. Use this public shape:

```python
from __future__ import annotations

from dataclasses import dataclass

from saber_tui.keys import matches_key

KeyId = str
Keybinding = str
KeybindingsConfig = dict[str, KeyId | list[KeyId] | None]


@dataclass(frozen=True)
class KeybindingConflict:
    key: KeyId
    keybindings: list[Keybinding]


TUI_KEYBINDINGS: dict[str, dict[str, KeyId | list[KeyId] | str]] = {
    "tui.editor.cursorUp": {"default_keys": "up", "description": "Move cursor up"},
    "tui.editor.cursorDown": {"default_keys": "down", "description": "Move cursor down"},
    "tui.editor.cursorLeft": {"default_keys": ["left", "ctrl+b"], "description": "Move cursor left"},
    "tui.editor.cursorRight": {"default_keys": ["right", "ctrl+f"], "description": "Move cursor right"},
    "tui.editor.cursorWordLeft": {
        "default_keys": ["alt+left", "ctrl+left", "alt+b"],
        "description": "Move cursor word left",
    },
    "tui.editor.cursorWordRight": {
        "default_keys": ["alt+right", "ctrl+right", "alt+f"],
        "description": "Move cursor word right",
    },
    "tui.editor.cursorLineStart": {"default_keys": ["home", "ctrl+a"], "description": "Move to line start"},
    "tui.editor.cursorLineEnd": {"default_keys": ["end", "ctrl+e"], "description": "Move to line end"},
    "tui.editor.deleteCharBackward": {"default_keys": "backspace", "description": "Delete character backward"},
    "tui.editor.deleteCharForward": {"default_keys": ["delete", "ctrl+d"], "description": "Delete character forward"},
    "tui.editor.deleteWordBackward": {
        "default_keys": ["ctrl+w", "alt+backspace"],
        "description": "Delete word backward",
    },
    "tui.editor.deleteWordForward": {"default_keys": ["alt+d", "alt+delete"], "description": "Delete word forward"},
    "tui.editor.deleteToLineStart": {"default_keys": "ctrl+u", "description": "Delete to line start"},
    "tui.editor.deleteToLineEnd": {"default_keys": "ctrl+k", "description": "Delete to line end"},
    "tui.editor.yank": {"default_keys": "ctrl+y", "description": "Yank"},
    "tui.editor.yankPop": {"default_keys": "alt+y", "description": "Yank pop"},
    "tui.editor.undo": {"default_keys": "ctrl+-", "description": "Undo"},
    "tui.input.newLine": {"default_keys": "shift+enter", "description": "Insert newline"},
    "tui.input.submit": {"default_keys": "enter", "description": "Submit input"},
    "tui.input.tab": {"default_keys": "tab", "description": "Tab / autocomplete"},
    "tui.input.copy": {"default_keys": "ctrl+c", "description": "Copy selection"},
    "tui.select.up": {"default_keys": "up", "description": "Move selection up"},
    "tui.select.down": {"default_keys": "down", "description": "Move selection down"},
    "tui.select.pageUp": {"default_keys": "pageUp", "description": "Selection page up"},
    "tui.select.pageDown": {"default_keys": "pageDown", "description": "Selection page down"},
    "tui.select.confirm": {"default_keys": "enter", "description": "Confirm selection"},
    "tui.select.cancel": {"default_keys": ["escape", "ctrl+c"], "description": "Cancel selection"},
}
```

Add `KeybindingsManager` methods: `matches`, `get_keys`, `get_definition`, `get_conflicts`, `set_user_bindings`, `get_user_bindings`, and `get_resolved_bindings`.

- [ ] **Step 6: Run key and keybinding tests**

Run:

```bash
uv run pytest tests/test_keys.py tests/test_keybindings.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit keys and keybindings**

Run:

```bash
git add src/saber_tui/keys.py src/saber_tui/keybindings.py tests/test_keys.py tests/test_keybindings.py
git commit -m "feat: add key parsing and keybindings"
```

Expected: commit succeeds.

## Task 6: Terminal Abstractions and Virtual Terminal

**Files:**

- Modify: `src/saber_tui/terminal.py`
- Create: `tests/virtual_terminal.py`
- Test: `tests/test_terminal.py`

- [ ] **Step 1: Write terminal protocol tests**

Create `tests/test_terminal.py`:

```python
from tests.virtual_terminal import VirtualTerminal


def test_virtual_terminal_records_writes_and_viewport() -> None:
    terminal = VirtualTerminal(columns=10, rows=3)
    terminal.write("hello")

    assert terminal.get_viewport()[0] == "hello"


def test_virtual_terminal_resize_invokes_handler() -> None:
    terminal = VirtualTerminal(columns=10, rows=3)
    resized = False

    def on_resize() -> None:
        nonlocal resized
        resized = True

    terminal.start(lambda data: None, on_resize)
    terminal.resize(20, 4)

    assert resized
    assert terminal.columns == 20
    assert terminal.rows == 4
```

- [ ] **Step 2: Implement `Terminal` and `VirtualTerminal`**

Replace `src/saber_tui/terminal.py` with:

```python
from __future__ import annotations

from collections.abc import Callable
from typing import Protocol


class Terminal(Protocol):
    def start(self, on_input: Callable[[str], None], on_resize: Callable[[], None]) -> None: ...
    def stop(self) -> None: ...
    def drain_input(self, max_ms: int = 1000, idle_ms: int = 50) -> None: ...
    def write(self, data: str) -> None: ...
    @property
    def columns(self) -> int: ...
    @property
    def rows(self) -> int: ...
    @property
    def kitty_protocol_active(self) -> bool: ...
    def move_by(self, lines: int) -> None: ...
    def hide_cursor(self) -> None: ...
    def show_cursor(self) -> None: ...
    def clear_line(self) -> None: ...
    def clear_from_cursor(self) -> None: ...
    def clear_screen(self) -> None: ...
    def set_title(self, title: str) -> None: ...
    def set_progress(self, active: bool) -> None: ...


class ProcessTerminal:
    def __init__(self) -> None:
        self._columns = 80
        self._rows = 24
        self._kitty_protocol_active = False

    @property
    def columns(self) -> int:
        return self._columns

    @property
    def rows(self) -> int:
        return self._rows

    @property
    def kitty_protocol_active(self) -> bool:
        return self._kitty_protocol_active

    def start(self, on_input: Callable[[str], None], on_resize: Callable[[], None]) -> None:
        import os
        import shutil
        import signal
        import sys
        import termios
        import threading
        import tty

        self._stdin = sys.stdin
        self._stdout = sys.stdout
        self._old_termios = termios.tcgetattr(self._stdin.fileno())
        tty.setraw(self._stdin.fileno())
        self._stdout.write("\x1b[?2004h")
        self._stdout.flush()
        size = shutil.get_terminal_size((80, 24))
        self._columns = size.columns
        self._rows = size.lines
        self._running = True

        def handle_winch(signum, frame) -> None:
            size = shutil.get_terminal_size((80, 24))
            self._columns = size.columns
            self._rows = size.lines
            on_resize()

        self._previous_winch = signal.getsignal(signal.SIGWINCH)
        signal.signal(signal.SIGWINCH, handle_winch)

        def reader() -> None:
            while self._running:
                try:
                    data = os.read(self._stdin.fileno(), 4096)
                except OSError:
                    return
                if data:
                    on_input(data.decode(errors="ignore"))

        self._reader_thread = threading.Thread(target=reader, daemon=True)
        self._reader_thread.start()

    def stop(self) -> None:
        import signal
        import termios

        self._running = False
        if hasattr(self, "_stdout"):
            self._stdout.write("\x1b[?2004l")
            self._stdout.flush()
        if hasattr(self, "_old_termios"):
            termios.tcsetattr(self._stdin.fileno(), termios.TCSADRAIN, self._old_termios)
        if hasattr(self, "_previous_winch"):
            signal.signal(signal.SIGWINCH, self._previous_winch)

    def drain_input(self, max_ms: int = 1000, idle_ms: int = 50) -> None:
        return None

    def write(self, data: str) -> None:
        import sys

        sys.stdout.write(data)
        sys.stdout.flush()

    def move_by(self, lines: int) -> None:
        if lines > 0:
            self.write(f"\x1b[{lines}B")
        elif lines < 0:
            self.write(f"\x1b[{-lines}A")

    def hide_cursor(self) -> None:
        self.write("\x1b[?25l")

    def show_cursor(self) -> None:
        self.write("\x1b[?25h")

    def clear_line(self) -> None:
        self.write("\x1b[K")

    def clear_from_cursor(self) -> None:
        self.write("\x1b[J")

    def clear_screen(self) -> None:
        self.write("\x1b[2J\x1b[H")

    def set_title(self, title: str) -> None:
        self.write(f"\x1b]0;{title}\x07")

    def set_progress(self, active: bool) -> None:
        self.write("\x1b]9;4;3\x07" if active else "\x1b]9;4;0;\x07")
```

Create `tests/virtual_terminal.py`:

```python
from __future__ import annotations

from collections.abc import Callable

import pyte


class VirtualTerminal:
    def __init__(self, columns: int = 80, rows: int = 24) -> None:
        self._columns = columns
        self._rows = rows
        self._screen = pyte.Screen(columns, rows)
        self._stream = pyte.Stream(self._screen)
        self._input_handler: Callable[[str], None] | None = None
        self._resize_handler: Callable[[], None] | None = None
        self.writes: list[str] = []

    def start(self, on_input: Callable[[str], None], on_resize: Callable[[], None]) -> None:
        self._input_handler = on_input
        self._resize_handler = on_resize
        self.write("\x1b[?2004h")

    def stop(self) -> None:
        self.write("\x1b[?2004l")
        self._input_handler = None
        self._resize_handler = None

    def drain_input(self, max_ms: int = 1000, idle_ms: int = 50) -> None:
        return None

    def write(self, data: str) -> None:
        self.writes.append(data)
        self._stream.feed(data)

    @property
    def columns(self) -> int:
        return self._columns

    @property
    def rows(self) -> int:
        return self._rows

    @property
    def kitty_protocol_active(self) -> bool:
        return True

    def send_input(self, data: str) -> None:
        if self._input_handler is not None:
            self._input_handler(data)

    def resize(self, columns: int, rows: int) -> None:
        self._columns = columns
        self._rows = rows
        self._screen.resize(rows, columns)
        if self._resize_handler is not None:
            self._resize_handler()

    def move_by(self, lines: int) -> None:
        if lines > 0:
            self.write(f"\x1b[{lines}B")
        elif lines < 0:
            self.write(f"\x1b[{-lines}A")

    def hide_cursor(self) -> None:
        self.write("\x1b[?25l")

    def show_cursor(self) -> None:
        self.write("\x1b[?25h")

    def clear_line(self) -> None:
        self.write("\x1b[K")

    def clear_from_cursor(self) -> None:
        self.write("\x1b[J")

    def clear_screen(self) -> None:
        self.write("\x1b[2J\x1b[H")

    def set_title(self, title: str) -> None:
        self.write(f"\x1b]0;{title}\x07")

    def set_progress(self, active: bool) -> None:
        return None

    def clear_writes(self) -> None:
        self.writes.clear()

    def get_viewport(self) -> list[str]:
        return [self._screen.display[index].rstrip() for index in range(self._rows)]
```

- [ ] **Step 3: Run terminal tests**

Run:

```bash
uv run pytest tests/test_terminal.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit terminal test support**

Run:

```bash
git add src/saber_tui/terminal.py tests/virtual_terminal.py tests/test_terminal.py
git commit -m "feat: add terminal abstractions"
```

Expected: commit succeeds.

## Task 7: Core TUI Renderer

**Files:**

- Modify: `src/saber_tui/tui.py`
- Test: `tests/test_tui_render.py`
- Test: `tests/test_tui_overlay.py`

- [ ] **Step 1: Write renderer tests**

Create `tests/test_tui_render.py`:

```python
from saber_tui.tui import CURSOR_MARKER, Component, TUI
from tests.virtual_terminal import VirtualTerminal


class StaticComponent:
    def __init__(self, lines: list[str]) -> None:
        self.lines = lines

    def render(self, width: int) -> list[str]:
        return self.lines

    def invalidate(self) -> None:
        return None


def test_start_renders_children() -> None:
    terminal = VirtualTerminal(columns=20, rows=5)
    tui = TUI(terminal)
    tui.add_child(StaticComponent(["hello", "world"]))

    tui.start()

    assert terminal.get_viewport()[0] == "hello"
    assert terminal.get_viewport()[1] == "world"


def test_request_render_updates_changed_line() -> None:
    terminal = VirtualTerminal(columns=20, rows=5)
    component = StaticComponent(["one"])
    tui = TUI(terminal)
    tui.add_child(component)
    tui.start()
    terminal.clear_writes()

    component.lines = ["two"]
    tui.request_render(force=True)

    assert terminal.get_viewport()[0] == "two"
    assert any("two" in write for write in terminal.writes)


def test_cursor_marker_is_stripped_from_output() -> None:
    terminal = VirtualTerminal(columns=20, rows=5)
    tui = TUI(terminal, show_hardware_cursor=True)
    tui.add_child(StaticComponent([f"ab{CURSOR_MARKER}cd"]))

    tui.start()

    assert CURSOR_MARKER not in "\n".join(terminal.get_viewport())
```

- [ ] **Step 2: Write overlay tests**

Create `tests/test_tui_overlay.py`:

```python
from saber_tui.tui import TUI
from tests.virtual_terminal import VirtualTerminal


class StaticComponent:
    def __init__(self, lines: list[str]) -> None:
        self.lines = lines

    def render(self, width: int) -> list[str]:
        return self.lines

    def invalidate(self) -> None:
        return None


def test_overlay_composites_over_base_content() -> None:
    terminal = VirtualTerminal(columns=20, rows=5)
    tui = TUI(terminal)
    tui.add_child(StaticComponent(["base content"]))

    tui.show_overlay(StaticComponent(["MENU"]), {"width": 6, "row": 0, "col": 2})
    tui.start()

    assert terminal.get_viewport()[0].startswith("baMENU")


def test_overlay_handle_can_hide_overlay() -> None:
    terminal = VirtualTerminal(columns=20, rows=5)
    tui = TUI(terminal)
    tui.add_child(StaticComponent(["base content"]))
    handle = tui.show_overlay(StaticComponent(["MENU"]), {"width": 6, "row": 0, "col": 2})
    tui.start()

    handle.hide()

    assert terminal.get_viewport()[0].startswith("base content")
```

- [ ] **Step 3: Implement `Component`, `Container`, overlays, and `TUI`**

Replace `src/saber_tui/tui.py` with a direct Python port of upstream `tui.ts`, adapted to synchronous tests:

```python
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from saber_tui.keys import is_key_release, matches_key
from saber_tui.terminal import Terminal
from saber_tui.utils import (
    extract_segments,
    normalize_terminal_output,
    slice_by_column,
    slice_with_width,
    visible_width,
)

CURSOR_MARKER = "\x1b_pi:c\x07"
SEGMENT_RESET = "\x1b[0m\x1b]8;;\x07"


class Component(Protocol):
    wants_key_release: bool

    def render(self, width: int) -> list[str]:
        pass

    def handle_input(self, data: str) -> None:
        pass

    def invalidate(self) -> None:
        pass


@runtime_checkable
class Focusable(Protocol):
    focused: bool


InputListener = Callable[[str], dict[str, Any] | None]
OverlayOptions = dict[str, Any]


class OverlayHandle(Protocol):
    def hide(self) -> None: ...
    def set_hidden(self, hidden: bool) -> None: ...
    def is_hidden(self) -> bool: ...
    def focus(self) -> None: ...
    def unfocus(self) -> None: ...
    def is_focused(self) -> bool: ...


class Container:
    def __init__(self) -> None:
        self.children: list[Component] = []

    def add_child(self, component: Component) -> None:
        self.children.append(component)

    def remove_child(self, component: Component) -> None:
        if component in self.children:
            self.children.remove(component)

    def clear(self) -> None:
        self.children.clear()

    def invalidate(self) -> None:
        for child in self.children:
            invalidate = getattr(child, "invalidate", None)
            if invalidate is not None:
                invalidate()

    def render(self, width: int) -> list[str]:
        lines: list[str] = []
        for child in self.children:
            lines.extend(child.render(width))
        return lines


@dataclass
class _OverlayEntry:
    component: Component
    options: OverlayOptions | None
    pre_focus: Component | None
    hidden: bool
    focus_order: int


class _OverlayHandle:
    def __init__(self, tui: TUI, entry: _OverlayEntry) -> None:
        self._tui = tui
        self._entry = entry

    def hide(self) -> None:
        self._tui._hide_overlay_entry(self._entry)

    def set_hidden(self, hidden: bool) -> None:
        self._tui._set_overlay_hidden(self._entry, hidden)

    def is_hidden(self) -> bool:
        return self._entry.hidden

    def focus(self) -> None:
        self._tui._focus_overlay(self._entry)

    def unfocus(self) -> None:
        self._tui._unfocus_overlay(self._entry)

    def is_focused(self) -> bool:
        return self._tui.focused_component is self._entry.component


class TUI(Container):
    def __init__(self, terminal: Terminal, show_hardware_cursor: bool = False) -> None:
        super().__init__()
        self.terminal = terminal
        self.focused_component: Component | None = None
        self.previous_lines: list[str] = []
        self.previous_width = 0
        self.previous_height = 0
        self.input_listeners: list[InputListener] = []
        self.overlay_stack: list[_OverlayEntry] = []
        self.focus_order_counter = 0
        self.show_hardware_cursor = show_hardware_cursor
        self.stopped = True
        self.full_redraws = 0

    def set_focus(self, component: Component | None) -> None:
        if isinstance(self.focused_component, Focusable):
            self.focused_component.focused = False
        self.focused_component = component
        if isinstance(component, Focusable):
            component.focused = True

    def add_input_listener(self, listener: InputListener) -> Callable[[], None]:
        self.input_listeners.append(listener)

        def remove() -> None:
            self.remove_input_listener(listener)

        return remove

    def remove_input_listener(self, listener: InputListener) -> None:
        if listener in self.input_listeners:
            self.input_listeners.remove(listener)

    def start(self) -> None:
        self.stopped = False
        self.terminal.start(self._handle_input, lambda: self.request_render(force=True))
        self.terminal.hide_cursor()
        self.request_render(force=True)

    def stop(self) -> None:
        self.stopped = True
        self.terminal.show_cursor()
        self.terminal.stop()

    def request_render(self, force: bool = False) -> None:
        if self.stopped:
            return
        if force:
            self.previous_lines = []
        self._do_render()

    def show_overlay(self, component: Component, options: OverlayOptions | None = None) -> OverlayHandle:
        entry = _OverlayEntry(component, options, self.focused_component, False, self.focus_order_counter + 1)
        self.focus_order_counter += 1
        self.overlay_stack.append(entry)
        if not (options or {}).get("nonCapturing"):
            self.set_focus(component)
        if not self.stopped:
            self.request_render()
        return _OverlayHandle(self, entry)

    def hide_overlay(self) -> None:
        if self.overlay_stack:
            self._hide_overlay_entry(self.overlay_stack[-1])

    def has_overlay(self) -> bool:
        return any(self._is_overlay_visible(entry) for entry in self.overlay_stack)

    def _handle_input(self, data: str) -> None:
        current = data
        for listener in list(self.input_listeners):
            result = listener(current)
            if result and result.get("consume"):
                return
            if result and "data" in result:
                current = result["data"]
        if matches_key(current, "shift+ctrl+d") and hasattr(self, "on_debug"):
            self.on_debug()
            return
        if self.focused_component is not None and hasattr(self.focused_component, "handle_input"):
            if is_key_release(current) and not getattr(self.focused_component, "wants_key_release", False):
                return
            self.focused_component.handle_input(current)
            self.request_render()

    def _is_overlay_visible(self, entry: _OverlayEntry) -> bool:
        if entry.hidden:
            return False
        visible = (entry.options or {}).get("visible")
        if visible is None:
            return True
        return bool(visible(self.terminal.columns, self.terminal.rows))

    def _hide_overlay_entry(self, entry: _OverlayEntry) -> None:
        if entry in self.overlay_stack:
            self.overlay_stack.remove(entry)
            if self.focused_component is entry.component:
                self.set_focus(entry.pre_focus)
            if not self.stopped:
                self.request_render(force=True)

    def _set_overlay_hidden(self, entry: _OverlayEntry, hidden: bool) -> None:
        entry.hidden = hidden
        if hidden and self.focused_component is entry.component:
            self.set_focus(entry.pre_focus)
        if not self.stopped:
            self.request_render(force=True)

    def _focus_overlay(self, entry: _OverlayEntry) -> None:
        if entry in self.overlay_stack and self._is_overlay_visible(entry):
            self.focus_order_counter += 1
            entry.focus_order = self.focus_order_counter
            self.set_focus(entry.component)
            self.request_render()

    def _unfocus_overlay(self, entry: _OverlayEntry) -> None:
        if self.focused_component is entry.component:
            self.set_focus(entry.pre_focus)
            self.request_render()

    def _resolve_overlay_layout(self, options: OverlayOptions | None, overlay_height: int) -> tuple[int, int, int]:
        opt = options or {}
        term_width = self.terminal.columns
        term_height = self.terminal.rows
        width = int(opt.get("width", min(80, term_width)))
        row = int(opt.get("row", max(0, (term_height - overlay_height) // 2)))
        col = int(opt.get("col", max(0, (term_width - width) // 2)))
        width = max(1, min(width, term_width))
        row = max(0, min(row, max(0, term_height - overlay_height)))
        col = max(0, min(col, max(0, term_width - width)))
        return width, row, col

    def _composite_overlays(self, lines: list[str]) -> list[str]:
        result = list(lines)
        visible = [entry for entry in self.overlay_stack if self._is_overlay_visible(entry)]
        visible.sort(key=lambda entry: entry.focus_order)
        for entry in visible:
            width, _, _ = self._resolve_overlay_layout(entry.options, 0)
            overlay_lines = entry.component.render(width)
            width, row, col = self._resolve_overlay_layout(entry.options, len(overlay_lines))
            while len(result) < row + len(overlay_lines):
                result.append("")
            for offset, overlay_line in enumerate(overlay_lines):
                result[row + offset] = self._composite_line_at(
                    result[row + offset], overlay_line, col, width, self.terminal.columns
                )
        return result

    def _composite_line_at(self, base_line: str, overlay_line: str, start_col: int, overlay_width: int, total_width: int) -> str:
        base = extract_segments(base_line, start_col, start_col + overlay_width, total_width - start_col - overlay_width, True)
        overlay = slice_with_width(overlay_line, 0, overlay_width, True)
        before_pad = " " * max(0, start_col - base.before_width)
        overlay_pad = " " * max(0, overlay_width - overlay.width)
        result = base.before + before_pad + overlay.text + overlay_pad + base.after
        if visible_width(result) > total_width:
            return slice_by_column(result, 0, total_width, True)
        return result

    def _extract_cursor_position(self, lines: list[str]) -> tuple[int, int] | None:
        for row in range(len(lines) - 1, -1, -1):
            index = lines[row].find(CURSOR_MARKER)
            if index != -1:
                col = visible_width(lines[row][:index])
                lines[row] = lines[row][:index] + lines[row][index + len(CURSOR_MARKER) :]
                return row, col
        return None

    def _apply_line_resets(self, lines: list[str]) -> list[str]:
        return [normalize_terminal_output(line) + SEGMENT_RESET for line in lines]

    def _do_render(self) -> None:
        width = self.terminal.columns
        lines = self.render(width)
        if self.overlay_stack:
            lines = self._composite_overlays(lines)
        cursor = self._extract_cursor_position(lines)
        lines = self._apply_line_resets(lines)
        for index, line in enumerate(lines):
            if visible_width(line) > width:
                raise ValueError(f"Rendered line {index} exceeds terminal width ({visible_width(line)} > {width})")
        buffer = "\x1b[?2026h"
        if not self.previous_lines or self.previous_width != width or self.previous_height != self.terminal.rows:
            self.full_redraws += 1
            buffer += "\x1b[2J\x1b[H"
            buffer += "\r\n".join(lines)
        else:
            first_changed = next(
                (index for index in range(max(len(lines), len(self.previous_lines))) if
                 (lines[index] if index < len(lines) else "") !=
                 (self.previous_lines[index] if index < len(self.previous_lines) else "")),
                -1,
            )
            if first_changed == -1:
                buffer += ""
            else:
                buffer += f"\x1b[{first_changed + 1};1H"
                buffer += "\r\n".join(lines[first_changed:])
        buffer += "\x1b[?2026l"
        self.terminal.write(buffer)
        if cursor is not None:
            row, col = cursor
            self.terminal.write(f"\x1b[{row + 1};{col + 1}H")
            if self.show_hardware_cursor:
                self.terminal.show_cursor()
            else:
                self.terminal.hide_cursor()
        self.previous_lines = lines
        self.previous_width = width
        self.previous_height = self.terminal.rows
```

- [ ] **Step 4: Run TUI renderer tests**

Run:

```bash
uv run pytest tests/test_tui_render.py tests/test_tui_overlay.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit core renderer**

Run:

```bash
git add src/saber_tui/tui.py tests/test_tui_render.py tests/test_tui_overlay.py
git commit -m "feat: add core tui renderer"
```

Expected: commit succeeds.

## Task 8: Text Layout Components

**Files:**

- Create: `src/saber_tui/components/text.py`
- Create: `src/saber_tui/components/truncated_text.py`
- Create: `src/saber_tui/components/box.py`
- Create: `src/saber_tui/components/spacer.py`
- Test: `tests/test_text_components.py`

- [ ] **Step 1: Write component tests**

Create `tests/test_text_components.py`:

```python
from saber_tui.components import Box, Spacer, Text, TruncatedText
from saber_tui.utils import visible_width


def test_text_wraps_and_pads_to_width() -> None:
    text = Text("hello world", padding_x=1, padding_y=1)

    lines = text.render(8)

    assert lines[0] == " " * 8
    assert all(visible_width(line) == 8 for line in lines)


def test_truncated_text_is_single_line() -> None:
    text = TruncatedText("abcdef", padding_x=1)

    assert text.render(6) == [" ab..."]


def test_box_wraps_child_lines_with_padding() -> None:
    box = Box(padding_x=1, padding_y=1)
    box.add_child(Text("hi", padding_x=0, padding_y=0))

    lines = box.render(6)

    assert lines == ["      ", " hi   ", "      "]


def test_spacer_returns_empty_width_lines() -> None:
    spacer = Spacer(2)

    assert spacer.render(4) == ["    ", "    "]
```

- [ ] **Step 2: Implement text components**

Create the component modules by translating upstream `text.ts`, `truncated-text.ts`, `box.ts`, and `spacer.ts`. Public constructors:

```python
Text(text: str = "", padding_x: int = 1, padding_y: int = 1, custom_bg_fn: Callable[[str], str] | None = None)
TruncatedText(text: str = "", padding_x: int = 0, padding_y: int = 0)
Box(padding_x: int = 1, padding_y: int = 1, bg_fn: Callable[[str], str] | None = None)
Spacer(height: int = 1)
```

Implementation requirements:

- Every rendered line must have `visible_width(line) <= width`.
- `Text.set_text` and `Text.set_custom_bg_fn` invalidate cached output.
- `Box.add_child`, `Box.remove_child`, and `Box.clear` invalidate cached output.
- `TruncatedText.set_text` invalidates cached output.
- Background functions receive already-padded text.

- [ ] **Step 3: Run component tests**

Run:

```bash
uv run pytest tests/test_text_components.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit text components**

Run:

```bash
git add src/saber_tui/components tests/test_text_components.py
git commit -m "feat: add text layout components"
```

Expected: commit succeeds.

## Task 9: Input Component

**Files:**

- Create: `src/saber_tui/components/input.py`
- Test: `tests/test_input.py`

- [ ] **Step 1: Write input tests**

Create `tests/test_input.py`:

```python
from saber_tui.components import Input
from saber_tui.tui import CURSOR_MARKER
from saber_tui.utils import visible_width


def test_input_inserts_printable_text_and_submits() -> None:
    input_box = Input()
    submitted: list[str] = []
    input_box.on_submit = submitted.append

    for char in "hello":
        input_box.handle_input(char)
    input_box.handle_input("\r")

    assert input_box.get_value() == "hello"
    assert submitted == ["hello"]


def test_input_backspace_deletes_grapheme() -> None:
    input_box = Input()
    input_box.set_value("aコン")
    input_box.handle_input("\x05")
    input_box.handle_input("\x7f")

    assert input_box.get_value() == "aコ"


def test_input_kill_ring_and_yank() -> None:
    input_box = Input()
    input_box.set_value("foo bar")
    input_box.handle_input("\x05")
    input_box.handle_input("\x17")
    assert input_box.get_value() == "foo "
    input_box.handle_input("\x19")
    assert input_box.get_value() == "foo bar"


def test_input_render_never_exceeds_width_and_marks_cursor_when_focused() -> None:
    input_box = Input()
    input_box.set_value("コンピューター")
    input_box.focused = True

    line = input_box.render(10)[0]

    assert visible_width(line) <= 10
    assert CURSOR_MARKER in line
```

- [ ] **Step 2: Implement `Input`**

Translate upstream `components/input.ts` into `src/saber_tui/components/input.py`.

Implementation requirements:

- Keep `value`, `cursor`, `focused`, `on_submit`, and `on_escape`.
- Use `regex.findall(r"\X", text)` for grapheme movement and deletion.
- Use `get_keybindings().matches(data, action)` for all navigation and editing commands.
- Support bracketed paste markers `\x1b[200~` and `\x1b[201~`.
- Support undo with `UndoStack`.
- Support kill ring actions: delete to start, delete to end, delete word backward, delete word forward, yank, and yank pop.
- Decode printable Kitty input with `decode_kitty_printable`.
- Reject C0, DEL, and C1 control characters as printable text.
- Render with prompt `"> "`, horizontal scrolling, inverse-video fake cursor, and `CURSOR_MARKER` before the fake cursor when focused.

- [ ] **Step 3: Run input tests**

Run:

```bash
uv run pytest tests/test_input.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit input component**

Run:

```bash
git add src/saber_tui/components/input.py tests/test_input.py
git commit -m "feat: add input component"
```

Expected: commit succeeds.

## Task 10: Select List and Loaders

**Files:**

- Create: `src/saber_tui/components/select_list.py`
- Create: `src/saber_tui/components/loader.py`
- Create: `src/saber_tui/components/cancellable_loader.py`
- Test: `tests/test_select_list.py`
- Test: `tests/test_loader.py`

- [ ] **Step 1: Write select list tests**

Create `tests/test_select_list.py`:

```python
from saber_tui.components import SelectItem, SelectList


def test_select_list_filters_and_selects_item() -> None:
    selected: list[SelectItem] = []
    items = [SelectItem("delete", "delete", "Delete last"), SelectItem("clear", "clear", "Clear all")]
    select = SelectList(items, max_visible=5)
    select.on_select = selected.append

    select.set_filter("cl")
    select.handle_input("\r")

    assert selected == [items[1]]


def test_select_list_wraps_selection() -> None:
    items = [SelectItem("one", "one"), SelectItem("two", "two")]
    select = SelectList(items, max_visible=5)

    select.handle_input("\x1b[A")

    assert select.get_selected_item() == items[1]
```

- [ ] **Step 2: Implement `SelectList`**

Translate upstream `components/select-list.ts` into `src/saber_tui/components/select_list.py`.

Implementation requirements:

- Create `SelectItem` as `@dataclass(frozen=True)` with `value`, `label`, and optional `description`.
- Keep `set_filter`, `set_selected_index`, `render`, `handle_input`, and `get_selected_item`.
- Use simple default theme functions when no theme is provided.
- Use `truncate_to_width` and `visible_width` for all line width management.
- Support `on_select`, `on_cancel`, and `on_selection_change`.

- [ ] **Step 3: Write loader tests**

Create `tests/test_loader.py`:

```python
from saber_tui.components.loader import Loader


class DummyTUI:
    def __init__(self) -> None:
        self.render_count = 0

    def request_render(self, force: bool = False) -> None:
        self.render_count += 1


def test_loader_renders_label_and_spinner() -> None:
    tui = DummyTUI()
    loader = Loader(tui, text="Thinking...")

    line = loader.render(20)[0]

    assert "Thinking..." in line


def test_loader_tick_requests_render() -> None:
    tui = DummyTUI()
    loader = Loader(tui, text="Thinking...")

    loader.tick()

    assert tui.render_count == 1
```

- [ ] **Step 4: Implement loaders**

Translate upstream `components/loader.ts` and `components/cancellable-loader.ts` into Python.

Implementation requirements:

- `Loader` constructor accepts `tui`, optional style functions, text, and spinner frames.
- `Loader.render(width)` returns one width-bounded line.
- `Loader.tick()` advances the frame and calls `tui.request_render()`.
- `CancellableLoader` wraps `Loader`, exposes `on_cancel`, and handles cancel keybindings.

- [ ] **Step 5: Run select list and loader tests**

Run:

```bash
uv run pytest tests/test_select_list.py tests/test_loader.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit selection and loader components**

Run:

```bash
git add src/saber_tui/components/select_list.py src/saber_tui/components/loader.py src/saber_tui/components/cancellable_loader.py tests/test_select_list.py tests/test_loader.py
git commit -m "feat: add select list and loaders"
```

Expected: commit succeeds.

## Task 11: Example and Documentation

**Files:**

- Modify: `README.md`
- Create: `examples/chat_simple.py`
- Test: `tests/test_examples.py`

- [ ] **Step 1: Write example import test**

Create `tests/test_examples.py`:

```python
import importlib.util
from pathlib import Path


def test_chat_simple_example_imports() -> None:
    path = Path("examples/chat_simple.py")
    spec = importlib.util.spec_from_file_location("chat_simple", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert hasattr(module, "build_app")
```

- [ ] **Step 2: Create non-running example module**

Create `examples/chat_simple.py`:

```python
from __future__ import annotations

from saber_tui import ProcessTerminal, TUI, matches_key
from saber_tui.components import Input, Text


def build_app() -> tuple[TUI, Input]:
    terminal = ProcessTerminal()
    tui = TUI(terminal)
    tui.add_child(Text("Welcome to Simple Chat!\nType a message below. Press Ctrl+C to exit."))

    input_box = Input()

    def submit(value: str) -> None:
        if value.strip():
            tui.add_child(Text(f"You said: {value}", padding_x=1, padding_y=0))
            tui.request_render()

    input_box.on_submit = submit
    tui.add_child(input_box)
    tui.set_focus(input_box)

    def exit_on_ctrl_c(data: str):
        if matches_key(data, "ctrl+c"):
            tui.stop()
            raise SystemExit(0)
        return None

    tui.add_input_listener(exit_on_ctrl_c)
    return tui, input_box


def main() -> None:
    tui, _input_box = build_app()
    tui.start()


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Write README**

Replace `README.md`:

```markdown
# saber-tui

Faithful low-level Python port of `@mariozechner/pi-tui`.

This first slice provides the core line-rendering framework, process terminal
abstraction, key parsing, keybindings, overlays, text components, single-line
input, select lists, and loaders.

## Usage

```python
from saber_tui import ProcessTerminal, TUI, matches_key
from saber_tui.components import Input, Text

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
    return None

tui.add_input_listener(exit_on_ctrl_c)
tui.start()
```

Run the example:

```bash
uv run python examples/chat_simple.py
```

## Development

```bash
uv run pytest
uv run ruff check
uv run ruff format --check
uvx ty check
```

## Parity Scope

Included in this slice:

- Core `TUI`, `Container`, overlays, focus, and differential rendering
- `ProcessTerminal`
- ANSI and Unicode width utilities
- `StdinBuffer`
- key parsing and keybindings
- `Text`, `TruncatedText`, `Box`, `Spacer`, `Input`, `SelectList`, `Loader`, and `CancellableLoader`

Outside this slice:

- Multiline `Editor`
- Autocomplete
- Markdown rendering
- Terminal image protocols
- Windows-specific VT input support
```

- [ ] **Step 4: Run example test**

Run:

```bash
uv run pytest tests/test_examples.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit docs and example**

Run:

```bash
git add README.md examples/chat_simple.py tests/test_examples.py
git commit -m "docs: add usage example"
```

Expected: commit succeeds.

## Task 12: Final Verification

**Files:**

- Modify only files required by failing verification output.

- [ ] **Step 1: Run full test suite**

Run:

```bash
uv run pytest -q
```

Expected: PASS.

- [ ] **Step 2: Run lint**

Run:

```bash
uv run ruff check
```

Expected: PASS.

- [ ] **Step 3: Run format check**

Run:

```bash
uv run ruff format --check
```

Expected: PASS.

- [ ] **Step 4: Run type check**

Run:

```bash
uvx ty check
```

Expected: PASS or report only unsupported third-party type metadata. Fix project code errors before continuing.

- [ ] **Step 5: Run import smoke manually**

Run:

```bash
uv run python -c "from saber_tui import TUI, ProcessTerminal; from saber_tui.components import Input, Text; print(TUI.__name__, ProcessTerminal.__name__, Input.__name__, Text.__name__)"
```

Expected:

```text
TUI ProcessTerminal Input Text
```

- [ ] **Step 6: Commit verification fixes**

If any verification step required fixes, run:

```bash
git add src tests README.md examples pyproject.toml uv.lock
git commit -m "fix: address verification findings"
```

Expected: commit succeeds when fixes exist. If no fixes exist, leave the working tree unchanged.

- [ ] **Step 7: Report final status**

Run:

```bash
git status --short
```

Expected: no output.

Report the test commands and results in the final implementation response.

## Plan Self-Review

Spec coverage:

- `uv` project management is covered by Task 1 and Task 12.
- Runtime dependencies `wcwidth` and `regex` are covered by Task 1 and Task 3.
- `pyte` virtual terminal testing is covered by Task 6 and Task 7.
- Terminal abstraction is covered by Task 6.
- Core renderer, focus, overlays, cursor marker, and differential rendering are covered by Task 7.
- Utilities are covered by Task 3.
- Stdin buffering is covered by Task 4.
- Keys and keybindings are covered by Task 5.
- Support primitives are covered by Task 2.
- First component slice is covered by Tasks 8, 9, and 10.
- Example and README are covered by Task 11.
- Final verification is covered by Task 12.

Known gaps against the approved design:

- Terminal image protocols, Markdown, autocomplete, and multiline `Editor` are outside this first implementation plan by design.
- Windows-specific VT input support is outside this first implementation plan by design.
- The renderer task starts with correctness-focused differential rendering. Further parity refinements should be driven by tests after this slice passes.
