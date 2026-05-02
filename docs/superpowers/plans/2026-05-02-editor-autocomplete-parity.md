# Editor and Autocomplete Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the staged multiline editor and autocomplete stack described in `docs/superpowers/specs/2026-05-02-editor-autocomplete-parity-design.md`.

**Architecture:** Add focused modules for editor compatibility, autocomplete, and the concrete editor component. Reuse the existing TUI renderer, keybindings, Unicode utilities, `SelectList`, `KillRing`, and `UndoStack`; keep all editor output line-oriented and width-bounded.

**Tech Stack:** Python 3.12, `uv`, `pytest`, `ruff`, existing `regex` and `wcwidth`, optional external `fd` command for recursive attachment completion.

---

## Source References

Read these files before starting the matching tasks:

- Approved spec: `docs/superpowers/specs/2026-05-02-editor-autocomplete-parity-design.md`
- Upstream editor: `/tmp/pi-mono-tui/packages/tui/src/components/editor.ts`
- Upstream autocomplete: `/tmp/pi-mono-tui/packages/tui/src/autocomplete.ts`
- Upstream editor protocol: `/tmp/pi-mono-tui/packages/tui/src/editor-component.ts`
- Upstream editor tests: `/tmp/pi-mono-tui/packages/tui/test/editor.test.ts`
- Upstream autocomplete tests: `/tmp/pi-mono-tui/packages/tui/test/autocomplete.test.ts`
- Local input component: `src/saber_tui/components/input.py`
- Local select list: `src/saber_tui/components/select_list.py`
- Local keybindings: `src/saber_tui/keybindings.py`
- Local fuzzy helpers: `src/saber_tui/fuzzy.py`
- Local utilities: `src/saber_tui/utils.py`

## File Structure

Create:

- `src/saber_tui/autocomplete.py`: autocomplete data classes, provider protocol, path/slash provider.
- `src/saber_tui/editor_component.py`: editor-compatible protocol.
- `src/saber_tui/components/editor.py`: `Editor`, editor dataclasses, wrapping helper, state mutation, rendering, autocomplete UI integration.
- `tests/test_autocomplete.py`: provider tests.
- `tests/test_editor.py`: editor component tests.

Modify:

- `src/saber_tui/__init__.py`: root exports for autocomplete and editor protocol.
- `src/saber_tui/components/__init__.py`: component exports for `Editor`.
- `src/saber_tui/keybindings.py`: add jump and page movement bindings.
- `src/saber_tui/fuzzy.py`: add upstream-compatible generic fuzzy helpers without breaking current API.
- `src/saber_tui/utils.py`: add public text helpers only if needed by `Editor`.
- `tests/test_imports.py`: import coverage for new public names.
- `tests/test_keybindings.py`: coverage for new bindings.
- `tests/test_fuzzy.py`: coverage for new fuzzy helpers.

Do not commit `missing.md`; it is an untracked parity note.

## Phase 1: Foundation APIs

### Task 1: Add Editor Keybindings

**Files:**

- Modify: `src/saber_tui/keybindings.py`
- Modify: `tests/test_keybindings.py`

- [ ] **Step 1: Add failing tests for missing editor bindings**

Append these tests to `tests/test_keybindings.py`:

```python
from saber_tui.keybindings import KeybindingsManager


def test_editor_jump_and_page_bindings_exist() -> None:
    keybindings = KeybindingsManager()

    assert keybindings.get_keys("tui.editor.jumpForward") == ["ctrl+]"]
    assert keybindings.get_keys("tui.editor.jumpBackward") == ["ctrl+alt+]"]
    assert keybindings.get_keys("tui.editor.pageUp") == ["pageUp"]
    assert keybindings.get_keys("tui.editor.pageDown") == ["pageDown"]


def test_editor_jump_binding_can_be_rebound_without_evicting_defaults() -> None:
    keybindings = KeybindingsManager({"tui.editor.jumpForward": "alt+j"})

    assert keybindings.get_keys("tui.editor.jumpForward") == ["alt+j"]
    assert keybindings.get_keys("tui.editor.cursorLeft") == ["left", "ctrl+b"]
```

- [ ] **Step 2: Run keybinding tests and verify the new tests fail**

Run:

```bash
uv run pytest tests/test_keybindings.py -q
```

Expected: FAIL with `KeyError` or an assertion failure for `tui.editor.jumpForward`.

- [ ] **Step 3: Add upstream editor bindings**

In `src/saber_tui/keybindings.py`, add these entries to `TUI_KEYBINDINGS` near the other `tui.editor.*` bindings:

```python
    "tui.editor.jumpForward": {"default_keys": "ctrl+]", "description": "Jump forward to character"},
    "tui.editor.jumpBackward": {"default_keys": "ctrl+alt+]", "description": "Jump backward to character"},
    "tui.editor.pageUp": {"default_keys": "pageUp", "description": "Page up"},
    "tui.editor.pageDown": {"default_keys": "pageDown", "description": "Page down"},
```

- [ ] **Step 4: Run keybinding tests and verify they pass**

Run:

```bash
uv run pytest tests/test_keybindings.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/saber_tui/keybindings.py tests/test_keybindings.py
git commit -m "Add editor jump and page keybindings"
```

Expected: commit succeeds and does not include `missing.md`.

### Task 2: Add Upstream-Compatible Fuzzy Helpers

**Files:**

- Modify: `src/saber_tui/fuzzy.py`
- Modify: `tests/test_fuzzy.py`

- [ ] **Step 1: Add failing tests for generic fuzzy filtering**

Append these tests to `tests/test_fuzzy.py`:

```python
from dataclasses import dataclass

from saber_tui.fuzzy import fuzzy_filter_items, fuzzy_match_score


@dataclass(frozen=True)
class Command:
    name: str
    label: str


def test_fuzzy_match_score_empty_query_matches_with_zero_score() -> None:
    match = fuzzy_match_score("", "anything")

    assert match.matches is True
    assert match.score == 0


def test_fuzzy_filter_items_returns_original_items_for_empty_query() -> None:
    items = [Command("delete", "Delete"), Command("clear", "Clear")]

    assert fuzzy_filter_items(items, "", lambda item: item.name) == items


def test_fuzzy_filter_items_filters_and_sorts_by_match_quality() -> None:
    items = [Command("src/components/editor.py", "Editor"), Command("docs/editor.md", "Docs")]

    result = fuzzy_filter_items(items, "ed", lambda item: item.name)

    assert [item.name for item in result] == ["docs/editor.md", "src/components/editor.py"]


def test_fuzzy_filter_items_requires_all_space_separated_tokens() -> None:
    items = [
        Command("src/components/editor.py", "Editor"),
        Command("src/components/input.py", "Input"),
        Command("tests/test_editor.py", "Editor tests"),
    ]

    result = fuzzy_filter_items(items, "src ed", lambda item: item.name)

    assert [item.name for item in result] == ["src/components/editor.py"]


def test_fuzzy_match_score_matches_swapped_alpha_numeric_tokens() -> None:
    match = fuzzy_match_score("abc123", "123abc")

    assert match.matches is True
```

- [ ] **Step 2: Run fuzzy tests and verify the new tests fail**

Run:

```bash
uv run pytest tests/test_fuzzy.py -q
```

Expected: FAIL with import errors for `fuzzy_filter_items` and `fuzzy_match_score`.

- [ ] **Step 3: Add fuzzy score dataclass and helpers**

In `src/saber_tui/fuzzy.py`, keep the existing `FuzzyMatch`, `fuzzy_match()`, and `fuzzy_filter()` APIs. Add these imports and helpers after the existing code:

```python
from collections.abc import Callable, Sequence
from typing import TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class FuzzyScore:
    matches: bool
    score: float


def fuzzy_match_score(query: str, text: str) -> FuzzyScore:
    query_lower = query.lower()
    text_lower = text.lower()

    def match_query(normalized_query: str) -> FuzzyScore:
        if normalized_query == "":
            return FuzzyScore(True, 0)
        if len(normalized_query) > len(text_lower):
            return FuzzyScore(False, 0)

        query_index = 0
        score = 0.0
        last_match_index = -1
        consecutive_matches = 0

        for index, char in enumerate(text_lower):
            if query_index >= len(normalized_query):
                break
            if char != normalized_query[query_index]:
                continue

            is_word_boundary = index == 0 or text_lower[index - 1] in " \t-_./:"
            if last_match_index == index - 1:
                consecutive_matches += 1
                score -= consecutive_matches * 5
            else:
                consecutive_matches = 0
                if last_match_index >= 0:
                    score += (index - last_match_index - 1) * 2
            if is_word_boundary:
                score -= 10
            score += index * 0.1
            last_match_index = index
            query_index += 1

        if query_index < len(normalized_query):
            return FuzzyScore(False, 0)
        return FuzzyScore(True, score)

    primary_match = match_query(query_lower)
    if primary_match.matches:
        return primary_match

    alpha_numeric = re.fullmatch(r"(?P<letters>[a-z]+)(?P<digits>[0-9]+)", query_lower)
    numeric_alpha = re.fullmatch(r"(?P<digits>[0-9]+)(?P<letters>[a-z]+)", query_lower)
    swapped_query = ""
    if alpha_numeric is not None:
        swapped_query = f"{alpha_numeric.group('digits')}{alpha_numeric.group('letters')}"
    elif numeric_alpha is not None:
        swapped_query = f"{numeric_alpha.group('letters')}{numeric_alpha.group('digits')}"

    if not swapped_query:
        return primary_match

    swapped_match = match_query(swapped_query)
    if not swapped_match.matches:
        return primary_match
    return FuzzyScore(True, swapped_match.score + 5)


def fuzzy_filter_items(items: Sequence[T], query: str, get_text: Callable[[T], str]) -> list[T]:
    if not query.strip():
        return list(items)

    tokens = [token for token in query.strip().split() if token]
    if not tokens:
        return list(items)

    results: list[tuple[T, float]] = []
    for item in items:
        total_score = 0.0
        for token in tokens:
            match = fuzzy_match_score(token, get_text(item))
            if not match.matches:
                break
            total_score += match.score
        else:
            results.append((item, total_score))

    results.sort(key=lambda result: result[1])
    return [item for item, _ in results]
```

Also add `import re` if it is not already present.

- [ ] **Step 4: Run fuzzy tests and fix import ordering**

Run:

```bash
uv run pytest tests/test_fuzzy.py -q
uv run ruff check src/saber_tui/fuzzy.py tests/test_fuzzy.py
```

Expected: both commands PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/saber_tui/fuzzy.py tests/test_fuzzy.py
git commit -m "Add generic fuzzy filtering helpers"
```

Expected: commit succeeds.

### Task 3: Add Autocomplete Public API Shell

**Files:**

- Create: `src/saber_tui/autocomplete.py`
- Modify: `src/saber_tui/__init__.py`
- Modify: `tests/test_imports.py`
- Create: `tests/test_autocomplete.py`

- [ ] **Step 1: Add failing import tests**

Append this test to `tests/test_imports.py`:

```python
def test_editor_autocomplete_exports_import() -> None:
    from saber_tui import (
        AbortSignalLike,
        AutocompleteItem,
        AutocompleteProvider,
        AutocompleteSuggestions,
        CombinedAutocompleteProvider,
        CompletionResult,
        EditorComponent,
        SlashCommand,
    )
    from saber_tui.components import Editor, EditorCursor, EditorOptions, EditorTheme, TextChunk, word_wrap_line

    assert AutocompleteItem
    assert AbortSignalLike
    assert AutocompleteProvider
    assert AutocompleteSuggestions
    assert CombinedAutocompleteProvider
    assert CompletionResult
    assert EditorComponent
    assert SlashCommand
    assert Editor
    assert EditorCursor
    assert EditorOptions
    assert EditorTheme
    assert TextChunk
    assert word_wrap_line
```

Create `tests/test_autocomplete.py` with:

```python
from saber_tui.autocomplete import (
    AutocompleteItem,
    AutocompleteSuggestions,
    CombinedAutocompleteProvider,
    CompletionResult,
    SlashCommand,
)


def test_autocomplete_dataclasses_hold_public_state() -> None:
    item = AutocompleteItem("help", "help", "Show help")
    suggestions = AutocompleteSuggestions([item], "/h")
    result = CompletionResult(["/help "], 0, 6)
    command = SlashCommand("help", "Show help", "topic")

    assert item.value == "help"
    assert suggestions.prefix == "/h"
    assert result.cursor_col == 6
    assert command.argument_hint == "topic"


def test_combined_autocomplete_provider_can_be_constructed() -> None:
    provider = CombinedAutocompleteProvider([SlashCommand("help", "Show help")], "/tmp")

    assert provider is not None
```

- [ ] **Step 2: Run import/autocomplete tests and verify failure**

Run:

```bash
uv run pytest tests/test_imports.py tests/test_autocomplete.py -q
```

Expected: FAIL with import errors for `saber_tui.autocomplete` and editor exports.

- [ ] **Step 3: Create autocomplete API shell**

Create `src/saber_tui/autocomplete.py`:

```python
from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TypeAlias


@dataclass(frozen=True)
class AutocompleteItem:
    value: str
    label: str
    description: str | None = None


@dataclass(frozen=True)
class SlashCommand:
    name: str
    description: str | None = None
    argument_hint: str | None = None
    get_argument_completions: (
        Callable[[str], list[AutocompleteItem] | Awaitable[list[AutocompleteItem] | None] | None] | None
    ) = None


@dataclass(frozen=True)
class AutocompleteSuggestions:
    items: list[AutocompleteItem]
    prefix: str


@dataclass(frozen=True)
class CompletionResult:
    lines: list[str]
    cursor_line: int
    cursor_col: int


class AbortSignalLike(Protocol):
    aborted: bool


SuggestionResult: TypeAlias = AutocompleteSuggestions | None
MaybeAwaitableSuggestionResult: TypeAlias = SuggestionResult | Awaitable[SuggestionResult]


class AutocompleteProvider(Protocol):
    def get_suggestions(
        self,
        lines: list[str],
        cursor_line: int,
        cursor_col: int,
        *,
        force: bool = False,
        signal: AbortSignalLike | None = None,
    ) -> MaybeAwaitableSuggestionResult: ...

    def apply_completion(
        self,
        lines: list[str],
        cursor_line: int,
        cursor_col: int,
        item: AutocompleteItem,
        prefix: str,
    ) -> CompletionResult: ...

    def should_trigger_file_completion(self, lines: list[str], cursor_line: int, cursor_col: int) -> bool: ...


CommandLike: TypeAlias = SlashCommand | AutocompleteItem


def _command_name(command: CommandLike) -> str:
    return command.name if isinstance(command, SlashCommand) else command.value


def _command_item(command: CommandLike) -> AutocompleteItem:
    if isinstance(command, AutocompleteItem):
        return command
    description = command.description or ""
    if command.argument_hint:
        description = f"{command.argument_hint} - {description}" if description else command.argument_hint
    return AutocompleteItem(command.name, command.name, description or None)


async def _maybe_await(
    value: list[AutocompleteItem] | Awaitable[list[AutocompleteItem] | None] | None,
) -> list[AutocompleteItem] | None:
    if inspect.isawaitable(value):
        return await value
    return value


class CombinedAutocompleteProvider:
    def __init__(
        self,
        commands: Sequence[CommandLike] = (),
        base_path: str | Path = Path.cwd(),
        fd_path: str | Path | None = None,
    ) -> None:
        self.commands = list(commands)
        self.base_path = Path(base_path)
        self.fd_path = Path(fd_path) if fd_path is not None else None

    def get_suggestions(
        self,
        lines: list[str],
        cursor_line: int,
        cursor_col: int,
        *,
        force: bool = False,
        signal: AbortSignalLike | None = None,
    ) -> AutocompleteSuggestions | None:
        _ = lines, cursor_line, cursor_col, force, signal
        return None

    def apply_completion(
        self,
        lines: list[str],
        cursor_line: int,
        cursor_col: int,
        item: AutocompleteItem,
        prefix: str,
    ) -> CompletionResult:
        line = lines[cursor_line] if 0 <= cursor_line < len(lines) else ""
        before_prefix = line[: max(0, cursor_col - len(prefix))]
        after_cursor = line[cursor_col:]
        new_lines = list(lines)
        if not new_lines:
            new_lines = [""]
            cursor_line = 0
        new_lines[cursor_line] = before_prefix + item.value + after_cursor
        return CompletionResult(new_lines, cursor_line, len(before_prefix) + len(item.value))

    def should_trigger_file_completion(self, lines: list[str], cursor_line: int, cursor_col: int) -> bool:
        current_line = lines[cursor_line] if 0 <= cursor_line < len(lines) else ""
        text_before_cursor = current_line[:cursor_col]
        return not (text_before_cursor.strip().startswith("/") and " " not in text_before_cursor.strip())
```

- [ ] **Step 4: Add temporary editor API shell for imports**

Create `src/saber_tui/editor_component.py`:

```python
from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from saber_tui.autocomplete import AutocompleteProvider


class EditorComponent(Protocol):
    on_submit: Callable[[str], None] | None
    on_change: Callable[[str], None] | None

    def render(self, width: int) -> list[str]: ...

    def handle_input(self, data: str) -> None: ...

    def get_text(self) -> str: ...

    def set_text(self, text: str) -> None: ...

    def add_to_history(self, text: str) -> None: ...

    def insert_text_at_cursor(self, text: str) -> None: ...

    def get_expanded_text(self) -> str: ...

    def set_autocomplete_provider(self, provider: AutocompleteProvider) -> None: ...

    def set_padding_x(self, padding: int) -> None: ...

    def set_autocomplete_max_visible(self, max_visible: int) -> None: ...
```

Create `src/saber_tui/components/editor.py` with import-safe shells:

```python
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from saber_tui.components.select_list import SelectListTheme


@dataclass(frozen=True)
class TextChunk:
    text: str
    start_index: int
    end_index: int


@dataclass(frozen=True)
class EditorCursor:
    line: int
    col: int


@dataclass(frozen=True)
class EditorTheme:
    border_color: Callable[[str], str] = lambda text: text
    select_list: SelectListTheme = SelectListTheme()


@dataclass(frozen=True)
class EditorOptions:
    padding_x: int = 0
    autocomplete_max_visible: int = 5


def word_wrap_line(line: str, max_width: int, pre_segmented: object | None = None) -> list[TextChunk]:
    _ = pre_segmented
    return [TextChunk(line, 0, len(line))] if line and max_width > 0 else [TextChunk("", 0, 0)]


class Editor:
    def __init__(self, tui: object, theme: EditorTheme | None = None, options: EditorOptions | None = None) -> None:
        self.tui = tui
        self.theme = theme or EditorTheme()
        self.options = options or EditorOptions()
        self.focused = False
        self.border_color = self.theme.border_color
        self.on_submit: Callable[[str], None] | None = None
        self.on_change: Callable[[str], None] | None = None
        self.disable_submit = False

    def render(self, width: int) -> list[str]:
        return [""[:width]]

    def handle_input(self, data: str) -> None:
        _ = data
```

- [ ] **Step 5: Export new names**

Update `src/saber_tui/__init__.py` to import and include these names in `__all__`:

```python
from saber_tui.autocomplete import (
    AbortSignalLike,
    AutocompleteItem,
    AutocompleteProvider,
    AutocompleteSuggestions,
    CombinedAutocompleteProvider,
    CompletionResult,
    SlashCommand,
)
from saber_tui.editor_component import EditorComponent
```

Update `src/saber_tui/components/__init__.py` to import and include these names in `__all__`:

```python
from saber_tui.components.editor import Editor, EditorCursor, EditorOptions, EditorTheme, TextChunk, word_wrap_line
```

- [ ] **Step 6: Run import/autocomplete tests**

Run:

```bash
uv run pytest tests/test_imports.py tests/test_autocomplete.py -q
uv run ruff check \
  src/saber_tui/autocomplete.py \
  src/saber_tui/editor_component.py \
  src/saber_tui/components/editor.py \
  tests/test_autocomplete.py \
  tests/test_imports.py
```

Expected: both commands PASS.

- [ ] **Step 7: Commit**

Run:

```bash
git add \
  src/saber_tui/autocomplete.py \
  src/saber_tui/editor_component.py \
  src/saber_tui/components/editor.py \
  src/saber_tui/__init__.py \
  src/saber_tui/components/__init__.py \
  tests/test_autocomplete.py \
  tests/test_imports.py
git commit -m "Add editor and autocomplete public API shells"
```

Expected: commit succeeds.

## Phase 2: Autocomplete Provider

### Task 4: Implement Slash Command Suggestions and Completion Application

**Files:**

- Modify: `src/saber_tui/autocomplete.py`
- Modify: `tests/test_autocomplete.py`

- [ ] **Step 1: Add failing slash command tests**

Append to `tests/test_autocomplete.py`:

```python
def test_slash_command_suggestions_match_names_and_descriptions() -> None:
    provider = CombinedAutocompleteProvider(
        [
            SlashCommand("help", "Show help"),
            SlashCommand("clear", "Clear chat"),
            SlashCommand("delete", "Delete last message", "message-id"),
        ],
        "/tmp",
    )

    suggestions = provider.get_suggestions(["/he"], 0, 3)

    assert suggestions is not None
    assert suggestions.prefix == "/he"
    assert suggestions.items[0] == AutocompleteItem("help", "help", "Show help")


def test_slash_command_completion_inserts_trailing_space() -> None:
    provider = CombinedAutocompleteProvider([SlashCommand("help", "Show help")], "/tmp")

    result = provider.apply_completion(["/he"], 0, 3, AutocompleteItem("help", "help"), "/he")

    assert result.lines == ["/help "]
    assert result.cursor_line == 0
    assert result.cursor_col == 6


def test_slash_command_argument_completion_replaces_argument_prefix() -> None:
    provider = CombinedAutocompleteProvider([SlashCommand("model", "Pick model")], "/tmp")

    result = provider.apply_completion(["/model gp"], 0, 9, AutocompleteItem("gpt-5", "gpt-5"), "gp")

    assert result.lines == ["/model gpt-5"]
    assert result.cursor_col == len("/model gpt-5")
```

- [ ] **Step 2: Run autocomplete tests and verify failure**

Run:

```bash
uv run pytest tests/test_autocomplete.py -q
```

Expected: FAIL because `get_suggestions()` returns `None` and slash completion does not add a space.

- [ ] **Step 3: Implement slash suggestions**

In `src/saber_tui/autocomplete.py`, import fuzzy helper:

```python
from saber_tui.fuzzy import fuzzy_filter_items
```

Replace `CombinedAutocompleteProvider.get_suggestions()` with:

```python
    def get_suggestions(
        self,
        lines: list[str],
        cursor_line: int,
        cursor_col: int,
        *,
        force: bool = False,
        signal: AbortSignalLike | None = None,
    ) -> AutocompleteSuggestions | None:
        if signal is not None and signal.aborted:
            return None
        current_line = lines[cursor_line] if 0 <= cursor_line < len(lines) else ""
        text_before_cursor = current_line[:cursor_col]

        if not force and text_before_cursor.startswith("/"):
            space_index = text_before_cursor.find(" ")
            if space_index == -1:
                prefix = text_before_cursor[1:]
                command_items = [_command_item(command) for command in self.commands]
                filtered = fuzzy_filter_items(command_items, prefix, lambda item: item.value)
                return AutocompleteSuggestions(filtered, text_before_cursor) if filtered else None
        return None
```

- [ ] **Step 4: Implement slash-aware completion application**

Replace `apply_completion()` with:

```python
    def apply_completion(
        self,
        lines: list[str],
        cursor_line: int,
        cursor_col: int,
        item: AutocompleteItem,
        prefix: str,
    ) -> CompletionResult:
        new_lines = list(lines) or [""]
        cursor_line = max(0, min(cursor_line, len(new_lines) - 1))
        current_line = new_lines[cursor_line]
        before_prefix = current_line[: max(0, cursor_col - len(prefix))]
        after_cursor = current_line[cursor_col:]
        adjusted_after = after_cursor

        is_quoted_prefix = prefix.startswith('"') or prefix.startswith('@"')
        if is_quoted_prefix and item.value.endswith('"') and adjusted_after.startswith('"'):
            adjusted_after = adjusted_after[1:]

        is_slash_command = prefix.startswith("/") and before_prefix.strip() == "" and "/" not in prefix[1:]
        if is_slash_command:
            new_line = f"{before_prefix}/{item.value} {adjusted_after}"
            new_lines[cursor_line] = new_line
            return CompletionResult(new_lines, cursor_line, len(before_prefix) + len(item.value) + 2)

        new_line = before_prefix + item.value + adjusted_after
        new_lines[cursor_line] = new_line
        return CompletionResult(new_lines, cursor_line, len(before_prefix) + len(item.value))
```

- [ ] **Step 5: Run autocomplete tests**

Run:

```bash
uv run pytest tests/test_autocomplete.py -q
uv run ruff check src/saber_tui/autocomplete.py tests/test_autocomplete.py
```

Expected: both commands PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add src/saber_tui/autocomplete.py tests/test_autocomplete.py
git commit -m "Implement slash command autocomplete"
```

Expected: commit succeeds.

### Task 5: Implement Direct Path Completion

**Files:**

- Modify: `src/saber_tui/autocomplete.py`
- Modify: `tests/test_autocomplete.py`

- [ ] **Step 1: Add failing path completion tests**

Append to `tests/test_autocomplete.py`:

```python
def test_forced_path_completion_preserves_dot_slash(tmp_path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "README.md").write_text("readme")
    provider = CombinedAutocompleteProvider([], tmp_path)

    suggestions = provider.get_suggestions(["./"], 0, 2, force=True)

    assert suggestions is not None
    assert suggestions.prefix == "./"
    assert AutocompleteItem("./src/", "src/") in suggestions.items
    assert AutocompleteItem("./README.md", "README.md") in suggestions.items


def test_path_completion_quotes_paths_with_spaces(tmp_path) -> None:
    (tmp_path / "two words.txt").write_text("content")
    provider = CombinedAutocompleteProvider([], tmp_path)

    suggestions = provider.get_suggestions(['"two'], 0, 4, force=True)

    assert suggestions is not None
    assert AutocompleteItem('"two words.txt"', "two words.txt") in suggestions.items


def test_should_trigger_file_completion_skips_slash_command() -> None:
    provider = CombinedAutocompleteProvider([], "/tmp")

    assert provider.should_trigger_file_completion(["/model"], 0, 6) is False
    assert provider.should_trigger_file_completion(["/model /"], 0, 8) is True
```

- [ ] **Step 2: Run autocomplete tests and verify failure**

Run:

```bash
uv run pytest tests/test_autocomplete.py -q
```

Expected: FAIL because path suggestions are not implemented.

- [ ] **Step 3: Add path parsing helpers**

Add these helpers to `src/saber_tui/autocomplete.py` before `CombinedAutocompleteProvider`:

```python
PATH_DELIMITERS = {" ", "\t", '"', "'", "="}


def _to_display_path(value: str) -> str:
    return value.replace("\\", "/")


def _find_last_delimiter(text: str) -> int:
    for index in range(len(text) - 1, -1, -1):
        if text[index] in PATH_DELIMITERS:
            return index
    return -1


def _find_unclosed_quote_start(text: str) -> int | None:
    in_quotes = False
    quote_start = -1
    for index, char in enumerate(text):
        if char == '"':
            in_quotes = not in_quotes
            if in_quotes:
                quote_start = index
    return quote_start if in_quotes else None


def _is_token_start(text: str, index: int) -> bool:
    return index == 0 or text[index - 1] in PATH_DELIMITERS


def _extract_quoted_prefix(text: str) -> str | None:
    quote_start = _find_unclosed_quote_start(text)
    if quote_start is None:
        return None
    if quote_start > 0 and text[quote_start - 1] == "@":
        return text[quote_start - 1 :] if _is_token_start(text, quote_start - 1) else None
    return text[quote_start:] if _is_token_start(text, quote_start) else None


@dataclass(frozen=True)
class _PathPrefix:
    raw_prefix: str
    is_at_prefix: bool
    is_quoted_prefix: bool


def _parse_path_prefix(prefix: str) -> _PathPrefix:
    if prefix.startswith('@"'):
        return _PathPrefix(prefix[2:], True, True)
    if prefix.startswith('"'):
        return _PathPrefix(prefix[1:], False, True)
    if prefix.startswith("@"):
        return _PathPrefix(prefix[1:], True, False)
    return _PathPrefix(prefix, False, False)


def _build_completion_value(path_value: str, *, is_at_prefix: bool, is_quoted_prefix: bool) -> str:
    needs_quotes = is_quoted_prefix or " " in path_value
    prefix = "@" if is_at_prefix else ""
    if not needs_quotes:
        return f"{prefix}{path_value}"
    return f'{prefix}"{path_value}"'
```

- [ ] **Step 4: Add direct path suggestion methods**

Add these methods inside `CombinedAutocompleteProvider`:

```python
    def _extract_path_prefix(self, text: str, force: bool = False) -> str | None:
        quoted_prefix = _extract_quoted_prefix(text)
        if quoted_prefix is not None:
            return quoted_prefix
        delimiter_index = _find_last_delimiter(text)
        path_prefix = text if delimiter_index == -1 else text[delimiter_index + 1 :]
        if force:
            return path_prefix
        if "/" in path_prefix or path_prefix.startswith(".") or path_prefix.startswith("~/"):
            return path_prefix
        if path_prefix == "" and text.endswith(" "):
            return path_prefix
        return None

    def _expand_home_path(self, path_value: str) -> Path:
        if path_value == "~":
            return Path.home()
        if path_value.startswith("~/"):
            return Path.home() / path_value[2:]
        return Path(path_value)

    def _get_file_suggestions(self, prefix: str) -> list[AutocompleteItem]:
        parsed = _parse_path_prefix(prefix)
        raw_prefix = parsed.raw_prefix
        expanded_prefix = self._expand_home_path(raw_prefix) if raw_prefix.startswith("~") else Path(raw_prefix)

        root_prefix = raw_prefix in {"", "./", "../", "~", "~/", "/"} or (parsed.is_at_prefix and raw_prefix == "")
        if root_prefix:
            if raw_prefix.startswith("~") or expanded_prefix.is_absolute():
                search_dir = expanded_prefix
            else:
                search_dir = self.base_path / expanded_prefix
            search_prefix = ""
            display_dir = raw_prefix
        elif raw_prefix.endswith("/"):
            if raw_prefix.startswith("~") or expanded_prefix.is_absolute():
                search_dir = expanded_prefix
            else:
                search_dir = self.base_path / expanded_prefix
            search_prefix = ""
            display_dir = raw_prefix
        else:
            display_path = Path(raw_prefix)
            if raw_prefix.startswith("~") or expanded_prefix.is_absolute():
                search_dir = expanded_prefix.parent
            else:
                search_dir = self.base_path / display_path.parent
            search_prefix = display_path.name
            display_dir = "" if str(display_path.parent) == "." else _to_display_path(str(display_path.parent)) + "/"

        try:
            entries = list(search_dir.iterdir())
        except OSError:
            return []

        suggestions: list[AutocompleteItem] = []
        for entry in entries:
            if not entry.name.lower().startswith(search_prefix.lower()):
                continue
            try:
                is_directory = entry.is_dir()
            except OSError:
                is_directory = False
            display_name = f"{entry.name}/" if is_directory else entry.name
            if raw_prefix.startswith("./") and not display_dir.startswith("./"):
                display_path_value = f"./{display_dir}{display_name}"
            elif raw_prefix.startswith("~/"):
                display_path_value = f"~/{display_dir.removeprefix('~/')}{display_name}"
            elif raw_prefix.startswith("/"):
                display_path_value = f"/{display_dir.lstrip('/')}{display_name}"
            else:
                display_path_value = f"{display_dir}{display_name}"
            suggestions.append(
                AutocompleteItem(
                    _build_completion_value(
                        _to_display_path(display_path_value),
                        is_at_prefix=parsed.is_at_prefix,
                        is_quoted_prefix=parsed.is_quoted_prefix,
                    ),
                    display_name,
                )
            )

        suggestions.sort(key=lambda item: (not item.value.endswith("/"), item.label))
        return suggestions
```

- [ ] **Step 5: Wire path suggestions into `get_suggestions()`**

At the end of `get_suggestions()`, before `return None`, add:

```python
        path_prefix = self._extract_path_prefix(text_before_cursor, force)
        if path_prefix is None:
            return None
        suggestions = self._get_file_suggestions(path_prefix)
        return AutocompleteSuggestions(suggestions, path_prefix) if suggestions else None
```

Update `should_trigger_file_completion()` to:

```python
    def should_trigger_file_completion(self, lines: list[str], cursor_line: int, cursor_col: int) -> bool:
        current_line = lines[cursor_line] if 0 <= cursor_line < len(lines) else ""
        text_before_cursor = current_line[:cursor_col]
        stripped = text_before_cursor.strip()
        if stripped.startswith("/") and " " not in stripped:
            return False
        return True
```

- [ ] **Step 6: Run autocomplete tests**

Run:

```bash
uv run pytest tests/test_autocomplete.py -q
uv run ruff check src/saber_tui/autocomplete.py tests/test_autocomplete.py
```

Expected: both commands PASS.

- [ ] **Step 7: Commit**

Run:

```bash
git add src/saber_tui/autocomplete.py tests/test_autocomplete.py
git commit -m "Implement direct path autocomplete"
```

Expected: commit succeeds.

### Task 6: Implement Slash Argument Completion and Optional fd Attachment Search

**Files:**

- Modify: `src/saber_tui/autocomplete.py`
- Modify: `tests/test_autocomplete.py`

- [ ] **Step 1: Add failing slash argument tests**

Append to `tests/test_autocomplete.py`:

```python
async def _model_completions(prefix: str) -> list[AutocompleteItem]:
    return [
        AutocompleteItem("gpt-5", "gpt-5", "frontier"),
        AutocompleteItem("gpt-5-mini", "gpt-5-mini", "small"),
    ]


def test_slash_command_argument_completions_are_used() -> None:
    provider = CombinedAutocompleteProvider(
        [
            SlashCommand(
                "model",
                "Pick model",
                get_argument_completions=lambda prefix: [AutocompleteItem("gpt-5", "gpt-5")],
            )
        ],
        "/tmp",
    )

    suggestions = provider.get_suggestions(["/model gp"], 0, 9)

    assert suggestions is not None
    assert suggestions.prefix == "gp"
    assert suggestions.items == [AutocompleteItem("gpt-5", "gpt-5")]


def test_invalid_slash_command_argument_completions_are_ignored() -> None:
    provider = CombinedAutocompleteProvider(
        [SlashCommand("model", "Pick model", get_argument_completions=lambda prefix: None)],
        "/tmp",
    )

    assert provider.get_suggestions(["/model gp"], 0, 9) is None
```

- [ ] **Step 2: Add optional fd tests**

Append to `tests/test_autocomplete.py`:

```python
import shutil


def test_at_completion_without_fd_returns_none_for_fuzzy_search(tmp_path) -> None:
    (tmp_path / "README.md").write_text("readme")
    provider = CombinedAutocompleteProvider([], tmp_path)

    assert provider.get_suggestions(["@read"], 0, 5) is None


def test_empty_at_completion_with_fd_when_available(tmp_path) -> None:
    fd_path = shutil.which("fd")
    if fd_path is None:
        return
    (tmp_path / "src").mkdir()
    (tmp_path / "README.md").write_text("readme")
    provider = CombinedAutocompleteProvider([], tmp_path, fd_path)

    suggestions = provider.get_suggestions(["@"], 0, 1)

    assert suggestions is not None
    assert suggestions.prefix == "@"
    assert {item.value for item in suggestions.items} >= {"@README.md", "@src/"}
```

- [ ] **Step 3: Run autocomplete tests and verify failure**

Run:

```bash
uv run pytest tests/test_autocomplete.py -q
```

Expected: FAIL because argument completions and `@` handling are absent.

- [ ] **Step 4: Implement synchronous slash argument completion**

Inside `get_suggestions()`, under the existing slash command branch after `space_index != -1`, add:

```python
            command_name = text_before_cursor[1:space_index]
            argument_text = text_before_cursor[space_index + 1 :]
            command = next((command for command in self.commands if _command_name(command) == command_name), None)
            if not isinstance(command, SlashCommand) or command.get_argument_completions is None:
                return None
            completions = command.get_argument_completions(argument_text)
            if inspect.isawaitable(completions):
                raise RuntimeError("async slash argument completion must be awaited through async editor integration")
            if not isinstance(completions, list) or not completions:
                return None
            return AutocompleteSuggestions(completions, argument_text)
```

This keeps the provider usable synchronously. Async editor integration will add an await path in Task 14.

- [ ] **Step 5: Implement `@` prefix extraction and fd search**

Add imports:

```python
import subprocess
```

Add method inside `CombinedAutocompleteProvider`:

```python
    def _extract_at_prefix(self, text: str) -> str | None:
        quoted_prefix = _extract_quoted_prefix(text)
        if quoted_prefix is not None and quoted_prefix.startswith('@"'):
            return quoted_prefix
        delimiter_index = _find_last_delimiter(text)
        token_start = 0 if delimiter_index == -1 else delimiter_index + 1
        return text[token_start:] if token_start < len(text) and text[token_start] == "@" else None

    def _get_fd_suggestions(self, prefix: str) -> list[AutocompleteItem]:
        if self.fd_path is None:
            return []
        parsed = _parse_path_prefix(prefix)
        query = parsed.raw_prefix
        args = [
            str(self.fd_path),
            "--base-directory",
            str(self.base_path),
            "--max-results",
            "100",
            "--type",
            "f",
            "--type",
            "d",
            "--follow",
            "--hidden",
            "--exclude",
            ".git",
            "--exclude",
            ".git/*",
            "--exclude",
            ".git/**",
        ]
        if "/" in query:
            args.append("--full-path")
        if query:
            args.append(query)
        try:
            completed = subprocess.run(args, check=False, capture_output=True, text=True, timeout=1)
        except (OSError, subprocess.TimeoutExpired):
            return []
        if completed.returncode != 0 or not completed.stdout:
            return []
        suggestions: list[AutocompleteItem] = []
        for line in completed.stdout.splitlines():
            display_path = _to_display_path(line.rstrip("/"))
            if display_path == ".git" or display_path.startswith(".git/") or "/.git/" in display_path:
                continue
            is_directory = line.endswith("/")
            completion_path = f"{display_path}/" if is_directory else display_path
            value = _build_completion_value(
                completion_path,
                is_at_prefix=True,
                is_quoted_prefix=parsed.is_quoted_prefix,
            )
            label = Path(display_path).name + ("/" if is_directory else "")
            suggestions.append(AutocompleteItem(value, label, display_path))
        suggestions.sort(key=lambda item: (not item.value.endswith("/"), item.value))
        return suggestions[:20]
```

At the start of `get_suggestions()`, after computing `text_before_cursor`, add:

```python
        at_prefix = self._extract_at_prefix(text_before_cursor)
        if at_prefix is not None:
            suggestions = self._get_fd_suggestions(at_prefix)
            return AutocompleteSuggestions(suggestions, at_prefix) if suggestions else None
```

- [ ] **Step 6: Run autocomplete tests**

Run:

```bash
uv run pytest tests/test_autocomplete.py -q
uv run ruff check src/saber_tui/autocomplete.py tests/test_autocomplete.py
```

Expected: both commands PASS.

- [ ] **Step 7: Commit**

Run:

```bash
git add src/saber_tui/autocomplete.py tests/test_autocomplete.py
git commit -m "Add command arguments and attachment autocomplete"
```

Expected: commit succeeds.

## Phase 3: Editor Core

### Task 7: Implement Editor State Accessors and Text Mutation

**Files:**

- Modify: `src/saber_tui/components/editor.py`
- Modify: `tests/test_editor.py`

- [ ] **Step 1: Create failing editor accessor tests**

Create `tests/test_editor.py`:

```python
from __future__ import annotations

from saber_tui.components.editor import Editor, EditorCursor, EditorTheme
from saber_tui.components.select_list import SelectListTheme
from saber_tui.tui import TUI
from tests.virtual_terminal import VirtualTerminal


def _theme() -> EditorTheme:
    return EditorTheme(border_color=lambda text: text, select_list=SelectListTheme())


def _editor(cols: int = 80, rows: int = 24) -> Editor:
    return Editor(TUI(VirtualTerminal(cols, rows)), _theme())


def test_editor_public_state_accessors_are_defensive() -> None:
    editor = _editor()
    editor.set_text("one\ntwo")

    lines = editor.get_lines()
    lines.append("mutated")

    assert editor.get_text() == "one\ntwo"
    assert editor.get_cursor() == EditorCursor(1, 3)


def test_insert_text_at_cursor_handles_multiline_text() -> None:
    editor = _editor()
    editor.set_text("hello")
    editor.handle_input("\x01")  # Ctrl+A

    editor.insert_text_at_cursor("a\r\nb\r")

    assert editor.get_text() == "a\nb\nhello"
    assert editor.get_cursor() == EditorCursor(2, 0)


def test_on_change_fires_for_text_changes_only() -> None:
    editor = _editor()
    changes: list[str] = []
    editor.on_change = changes.append

    editor.handle_input("a")
    editor.handle_input("\x1b[D")

    assert changes == ["a"]
```

- [ ] **Step 2: Run editor tests and verify failure**

Run:

```bash
uv run pytest tests/test_editor.py -q
```

Expected: FAIL because editor methods are missing.

- [ ] **Step 3: Implement editor state and accessors**

Replace the shell `Editor` class in `src/saber_tui/components/editor.py` with an implementation that starts with this state:

```python
from saber_tui.keybindings import get_keybindings


class Editor:
    def __init__(self, tui: object, theme: EditorTheme | None = None, options: EditorOptions | None = None) -> None:
        self.tui = tui
        self.theme = theme or EditorTheme()
        self.options = options or EditorOptions()
        self.focused = False
        self.border_color = self.theme.border_color
        self.on_submit: Callable[[str], None] | None = None
        self.on_change: Callable[[str], None] | None = None
        self.disable_submit = False
        self.lines = [""]
        self.cursor_line = 0
        self.cursor_col = 0
        self.padding_x = max(0, int(self.options.padding_x))
        self.autocomplete_max_visible = max(3, min(20, int(self.options.autocomplete_max_visible)))

    def get_padding_x(self) -> int:
        return self.padding_x

    def set_padding_x(self, padding: int) -> None:
        self.padding_x = max(0, int(padding))
        self._request_render()

    def get_autocomplete_max_visible(self) -> int:
        return self.autocomplete_max_visible

    def set_autocomplete_max_visible(self, max_visible: int) -> None:
        self.autocomplete_max_visible = max(3, min(20, int(max_visible)))
        self._request_render()

    def get_text(self) -> str:
        return "\n".join(self.lines)

    def get_expanded_text(self) -> str:
        return self.get_text()

    def get_lines(self) -> list[str]:
        return list(self.lines)

    def get_cursor(self) -> EditorCursor:
        self._clamp_cursor()
        return EditorCursor(self.cursor_line, self.cursor_col)

    def set_text(self, text: str) -> None:
        normalized = self._normalize_text(text)
        self.lines = normalized.split("\n") if normalized else [""]
        self.cursor_line = len(self.lines) - 1
        self.cursor_col = len(self.lines[self.cursor_line])
        self._emit_change()
        self._request_render()

    def insert_text_at_cursor(self, text: str) -> None:
        self._insert_text_at_cursor_internal(self._normalize_text(text))
        self._emit_change()
        self._request_render()

    def invalidate(self) -> None:
        pass

    def _normalize_text(self, text: str) -> str:
        return text.replace("\r\n", "\n").replace("\r", "\n")

    def _clamp_cursor(self) -> None:
        if not self.lines:
            self.lines = [""]
        self.cursor_line = max(0, min(self.cursor_line, len(self.lines) - 1))
        self.cursor_col = max(0, min(self.cursor_col, len(self.lines[self.cursor_line])))

    def _insert_text_at_cursor_internal(self, text: str) -> None:
        self._clamp_cursor()
        before = self.lines[self.cursor_line][: self.cursor_col]
        after = self.lines[self.cursor_line][self.cursor_col :]
        parts = text.split("\n")
        if len(parts) == 1:
            self.lines[self.cursor_line] = before + parts[0] + after
            self.cursor_col += len(parts[0])
            return
        replacement = [before + parts[0], *parts[1:-1], parts[-1] + after]
        self.lines[self.cursor_line : self.cursor_line + 1] = replacement
        self.cursor_line += len(parts) - 1
        self.cursor_col = len(parts[-1])

    def _emit_change(self) -> None:
        if self.on_change is not None:
            self.on_change(self.get_text())

    def _request_render(self) -> None:
        request_render = getattr(self.tui, "request_render", None)
        if request_render is not None:
            request_render()
```

Keep the shell `render()` and expand `handle_input()` for basic printable insertion and line start:

```python
    def handle_input(self, data: str) -> None:
        kb = get_keybindings()
        if kb.matches(data, "tui.editor.cursorLineStart"):
            self.cursor_col = 0
            self._request_render()
            return
        if data and all(ord(char) >= 32 and ord(char) != 0x7F for char in data):
            self.insert_text_at_cursor(data)
```

- [ ] **Step 4: Run editor tests**

Run:

```bash
uv run pytest tests/test_editor.py -q
uv run ruff check src/saber_tui/components/editor.py tests/test_editor.py
```

Expected: both commands PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/saber_tui/components/editor.py tests/test_editor.py
git commit -m "Add editor state and text mutation"
```

Expected: commit succeeds.

### Task 8: Implement Word Wrapping and Width-Bounded Rendering

**Files:**

- Modify: `src/saber_tui/components/editor.py`
- Modify: `tests/test_editor.py`

- [ ] **Step 1: Add failing rendering tests**

Append to `tests/test_editor.py`:

```python
from saber_tui.tui import CURSOR_MARKER
from saber_tui.utils import visible_width


def test_word_wrap_line_wraps_at_word_boundaries() -> None:
    from saber_tui.components.editor import word_wrap_line

    chunks = word_wrap_line("hello world", 7)

    assert [chunk.text for chunk in chunks] == ["hello ", "world"]
    assert [(chunk.start_index, chunk.end_index) for chunk in chunks] == [(0, 6), (6, 11)]


def test_editor_render_is_width_bounded_and_marks_focused_cursor() -> None:
    editor = _editor()
    editor.focused = True
    editor.set_text("hello コンピューター")

    lines = editor.render(12)

    assert len(lines) >= 3
    assert CURSOR_MARKER in "".join(lines)
    assert all(visible_width(line) <= 12 for line in lines)


def test_editor_render_handles_narrow_width() -> None:
    editor = _editor()
    editor.focused = True
    editor.set_text("abcdef")

    lines = editor.render(1)

    assert lines
    assert all(visible_width(line) <= 1 for line in lines)
```

- [ ] **Step 2: Run rendering tests and verify failure**

Run:

```bash
uv run pytest \
  tests/test_editor.py::test_word_wrap_line_wraps_at_word_boundaries \
  tests/test_editor.py::test_editor_render_is_width_bounded_and_marks_focused_cursor \
  tests/test_editor.py::test_editor_render_handles_narrow_width \
  -q
```

Expected: FAIL because wrapping and render output are still shell behavior.

- [ ] **Step 3: Implement wrapping helper**

In `src/saber_tui/components/editor.py`, import:

```python
import regex

from saber_tui.tui import CURSOR_MARKER
from saber_tui.utils import slice_by_column, visible_width
```

Replace `word_wrap_line()` with:

```python
def _grapheme_spans(text: str) -> list[tuple[str, int, int]]:
    spans: list[tuple[str, int, int]] = []
    for match in regex.finditer(r"\X", text):
        spans.append((match.group(0), match.start(), match.end()))
    return spans


def word_wrap_line(line: str, max_width: int, pre_segmented: object | None = None) -> list[TextChunk]:
    _ = pre_segmented
    if not line or max_width <= 0:
        return [TextChunk("", 0, 0)]
    if visible_width(line) <= max_width:
        return [TextChunk(line, 0, len(line))]

    spans = _grapheme_spans(line)
    chunks: list[TextChunk] = []
    chunk_start = 0
    current_width = 0
    wrap_index = -1
    wrap_width = 0

    for index, (segment, start, end) in enumerate(spans):
        segment_width = visible_width(segment)
        if current_width + segment_width > max_width:
            if wrap_index >= 0:
                chunks.append(TextChunk(line[chunk_start:wrap_index], chunk_start, wrap_index))
                chunk_start = wrap_index
                current_width -= wrap_width
            elif chunk_start < start:
                chunks.append(TextChunk(line[chunk_start:start], chunk_start, start))
                chunk_start = start
                current_width = 0
            wrap_index = -1

        current_width += segment_width
        next_segment = spans[index + 1][0] if index + 1 < len(spans) else ""
        if segment.isspace() and next_segment and not next_segment.isspace():
            wrap_index = end
            wrap_width = current_width

    chunks.append(TextChunk(line[chunk_start:], chunk_start, len(line)))
    return chunks
```

- [ ] **Step 4: Implement render output**

Add methods inside `Editor`:

```python
    def _content_width(self, width: int) -> int:
        return max(1, width - self.padding_x * 2)

    def _cursor_line_with_marker(self, text: str, cursor_col: int) -> str:
        before = text[:cursor_col]
        after = text[cursor_col:]
        graphemes = _grapheme_spans(after)
        cursor_cell = graphemes[0][0] if graphemes else " "
        rest = after[len(cursor_cell) :]
        marker = CURSOR_MARKER if self.focused else ""
        return f"{before}{marker}\x1b[7m{cursor_cell}\x1b[27m{rest}"

    def render(self, width: int) -> list[str]:
        if width <= 0:
            return [""]
        self._clamp_cursor()
        border = self.border_color("─" * width)
        if width <= 1:
            border = self.border_color("─"[:width])

        content_width = self._content_width(width)
        rendered: list[str] = [border]
        for logical_index, line in enumerate(self.lines):
            line_for_layout = line
            chunks = word_wrap_line(line_for_layout, content_width)
            for chunk in chunks:
                chunk_text = chunk.text
                if logical_index == self.cursor_line and chunk.start_index <= self.cursor_col <= chunk.end_index:
                    chunk_cursor = self.cursor_col - chunk.start_index
                    chunk_text = self._cursor_line_with_marker(chunk_text, chunk_cursor)
                left_padding = " " * min(self.padding_x, max(0, width))
                rendered_line = left_padding + chunk_text
                if visible_width(rendered_line) > width:
                    rendered_line = slice_by_column(rendered_line, 0, width, True)
                rendered.append(rendered_line + " " * max(0, width - visible_width(rendered_line)))
        rendered.append(border)
        return [slice_by_column(line, 0, width, True) if visible_width(line) > width else line for line in rendered]
```

- [ ] **Step 5: Run rendering tests**

Run:

```bash
uv run pytest tests/test_editor.py -q
uv run ruff check src/saber_tui/components/editor.py tests/test_editor.py
```

Expected: both commands PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add src/saber_tui/components/editor.py tests/test_editor.py
git commit -m "Render width bounded multiline editor"
```

Expected: commit succeeds.

### Task 9: Implement Core Cursor Movement and Deletion

**Files:**

- Modify: `src/saber_tui/components/editor.py`
- Modify: `tests/test_editor.py`

- [ ] **Step 1: Add failing movement and deletion tests**

Append to `tests/test_editor.py`:

```python
def test_arrow_keys_move_across_lines_and_insert_at_cursor() -> None:
    editor = _editor()
    editor.set_text("one\ntwo")

    editor.handle_input("\x1b[A")
    editor.handle_input("X")

    assert editor.get_text() == "oneX\ntwo"


def test_backspace_at_line_start_joins_previous_line() -> None:
    editor = _editor()
    editor.set_text("one\ntwo")
    editor.handle_input("\x01")
    editor.handle_input("\x7f")

    assert editor.get_text() == "onetwo"
    assert editor.get_cursor() == EditorCursor(0, 3)


def test_delete_at_line_end_joins_next_line() -> None:
    editor = _editor()
    editor.set_text("one\ntwo")
    editor.handle_input("\x1b[A")
    editor.handle_input("\x05")
    editor.handle_input("\x04")

    assert editor.get_text() == "onetwo"
    assert editor.get_cursor() == EditorCursor(0, 3)
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv run pytest \
  tests/test_editor.py::test_arrow_keys_move_across_lines_and_insert_at_cursor \
  tests/test_editor.py::test_backspace_at_line_start_joins_previous_line \
  tests/test_editor.py::test_delete_at_line_end_joins_next_line \
  -q
```

Expected: FAIL because movement and deletion are absent.

- [ ] **Step 3: Add grapheme helpers and movement methods**

Add methods inside `Editor`:

```python
    def _previous_grapheme_start(self, text: str, col: int) -> int:
        starts = [start for _, start, end in _grapheme_spans(text) if end <= col]
        return starts[-1] if starts else max(0, col - 1)

    def _next_grapheme_end(self, text: str, col: int) -> int:
        for _, start, end in _grapheme_spans(text):
            if start >= col:
                return end
        return min(len(text), col + 1)

    def _move_left(self) -> None:
        self._clamp_cursor()
        if self.cursor_col > 0:
            self.cursor_col = self._previous_grapheme_start(self.lines[self.cursor_line], self.cursor_col)
        elif self.cursor_line > 0:
            self.cursor_line -= 1
            self.cursor_col = len(self.lines[self.cursor_line])

    def _move_right(self) -> None:
        self._clamp_cursor()
        if self.cursor_col < len(self.lines[self.cursor_line]):
            self.cursor_col = self._next_grapheme_end(self.lines[self.cursor_line], self.cursor_col)
        elif self.cursor_line < len(self.lines) - 1:
            self.cursor_line += 1
            self.cursor_col = 0

    def _move_up(self) -> None:
        self._clamp_cursor()
        if self.cursor_line > 0:
            self.cursor_line -= 1
            self.cursor_col = min(self.cursor_col, len(self.lines[self.cursor_line]))

    def _move_down(self) -> None:
        self._clamp_cursor()
        if self.cursor_line < len(self.lines) - 1:
            self.cursor_line += 1
            self.cursor_col = min(self.cursor_col, len(self.lines[self.cursor_line]))
```

- [ ] **Step 4: Add deletion methods**

Add methods inside `Editor`:

```python
    def _delete_backward(self) -> bool:
        self._clamp_cursor()
        if self.cursor_col > 0:
            line = self.lines[self.cursor_line]
            start = self._previous_grapheme_start(line, self.cursor_col)
            self.lines[self.cursor_line] = line[:start] + line[self.cursor_col :]
            self.cursor_col = start
            return True
        if self.cursor_line > 0:
            previous_len = len(self.lines[self.cursor_line - 1])
            self.lines[self.cursor_line - 1] += self.lines[self.cursor_line]
            del self.lines[self.cursor_line]
            self.cursor_line -= 1
            self.cursor_col = previous_len
            return True
        return False

    def _delete_forward(self) -> bool:
        self._clamp_cursor()
        line = self.lines[self.cursor_line]
        if self.cursor_col < len(line):
            end = self._next_grapheme_end(line, self.cursor_col)
            self.lines[self.cursor_line] = line[: self.cursor_col] + line[end:]
            return True
        if self.cursor_line < len(self.lines) - 1:
            self.lines[self.cursor_line] += self.lines[self.cursor_line + 1]
            del self.lines[self.cursor_line + 1]
            return True
        return False
```

- [ ] **Step 5: Wire movement and deletion in `handle_input()`**

Add branches before printable insertion:

```python
        if kb.matches(data, "tui.editor.cursorUp"):
            self._move_up()
            self._request_render()
            return
        if kb.matches(data, "tui.editor.cursorDown"):
            self._move_down()
            self._request_render()
            return
        if kb.matches(data, "tui.editor.cursorLeft"):
            self._move_left()
            self._request_render()
            return
        if kb.matches(data, "tui.editor.cursorRight"):
            self._move_right()
            self._request_render()
            return
        if kb.matches(data, "tui.editor.cursorLineEnd"):
            self.cursor_col = len(self.lines[self.cursor_line])
            self._request_render()
            return
        if kb.matches(data, "tui.editor.deleteCharBackward"):
            if self._delete_backward():
                self._emit_change()
            self._request_render()
            return
        if kb.matches(data, "tui.editor.deleteCharForward"):
            if self._delete_forward():
                self._emit_change()
            self._request_render()
            return
```

- [ ] **Step 6: Run editor tests**

Run:

```bash
uv run pytest tests/test_editor.py -q
uv run ruff check src/saber_tui/components/editor.py tests/test_editor.py
```

Expected: both commands PASS.

- [ ] **Step 7: Commit**

Run:

```bash
git add src/saber_tui/components/editor.py tests/test_editor.py
git commit -m "Add editor cursor movement and deletion"
```

Expected: commit succeeds.

### Task 10: Implement Submit, Newline, History, and Backslash Enter

**Files:**

- Modify: `src/saber_tui/components/editor.py`
- Modify: `tests/test_editor.py`

- [ ] **Step 1: Add failing submit and history tests**

Append to `tests/test_editor.py`:

```python
def test_enter_submits_and_shift_enter_inserts_newline() -> None:
    editor = _editor()
    submitted: list[str] = []
    editor.on_submit = submitted.append
    editor.handle_input("h")
    editor.handle_input("\x1b[13;2u")  # shift+enter Kitty CSI-u
    editor.handle_input("i")
    editor.handle_input("\r")

    assert editor.get_text() == "h\ni"
    assert submitted == ["h\ni"]


def test_backslash_enter_converts_standalone_backslash_to_newline() -> None:
    editor = _editor()
    editor.handle_input("\\")
    editor.handle_input("\r")

    assert editor.get_text() == "\n"


def test_prompt_history_navigation() -> None:
    editor = _editor()
    editor.add_to_history("first")
    editor.add_to_history("second")

    editor.handle_input("\x1b[A")
    assert editor.get_text() == "second"

    editor.handle_input("\x1b[A")
    assert editor.get_text() == "first"

    editor.handle_input("\x1b[B")
    assert editor.get_text() == "second"

    editor.handle_input("\x1b[B")
    assert editor.get_text() == ""
```

- [ ] **Step 2: Run targeted tests and verify failure**

Run:

```bash
uv run pytest \
  tests/test_editor.py::test_enter_submits_and_shift_enter_inserts_newline \
  tests/test_editor.py::test_backslash_enter_converts_standalone_backslash_to_newline \
  tests/test_editor.py::test_prompt_history_navigation \
  -q
```

Expected: FAIL because submit/newline/history are incomplete.

- [ ] **Step 3: Add history state and methods**

In `Editor.__init__`, add:

```python
        self.history: list[str] = []
        self.history_index = -1
        self.history_browse_original: str | None = None
```

Add methods:

```python
    def add_to_history(self, text: str) -> None:
        if not text.strip():
            return
        if self.history and self.history[-1] == text:
            return
        self.history.append(text)
        if len(self.history) > 100:
            self.history = self.history[-100:]

    def _set_text_internal(self, text: str, *, emit_change: bool) -> None:
        normalized = self._normalize_text(text)
        self.lines = normalized.split("\n") if normalized else [""]
        self.cursor_line = len(self.lines) - 1
        self.cursor_col = len(self.lines[self.cursor_line])
        if emit_change:
            self._emit_change()
        self._request_render()

    def _exit_history_mode(self) -> None:
        self.history_index = -1
        self.history_browse_original = None

    def _is_editor_empty(self) -> bool:
        return len(self.lines) == 1 and self.lines[0] == ""

    def _navigate_history(self, direction: int) -> bool:
        if not self.history:
            return False
        if direction < 0 and not self._is_editor_empty() and self.history_index == -1:
            return False
        if self.history_index == -1:
            self.history_browse_original = self.get_text()
            self.history_index = 0
        else:
            self.history_index += -direction
        if self.history_index < 0:
            self.history_index = -1
            self._set_text_internal(self.history_browse_original or "", emit_change=False)
            self.history_browse_original = None
            return True
        self.history_index = min(self.history_index, len(self.history) - 1)
        self._set_text_internal(self.history[-1 - self.history_index], emit_change=False)
        return True
```

Update `set_text()` to call `_exit_history_mode()` before setting text.

- [ ] **Step 4: Add newline and submit methods**

Add methods:

```python
    def _add_newline(self) -> None:
        self._insert_text_at_cursor_internal("\n")
        self._exit_history_mode()
        self._emit_change()
        self._request_render()

    def _submit_value(self) -> None:
        if self.disable_submit:
            return
        self._exit_history_mode()
        if self.on_submit is not None:
            self.on_submit(self.get_expanded_text())

    def _should_submit_on_backslash_enter(self, data: str) -> bool:
        _ = data
        self._clamp_cursor()
        return self.cursor_col > 0 and self.lines[self.cursor_line][self.cursor_col - 1 : self.cursor_col] == "\\"
```

- [ ] **Step 5: Wire history, newline, and submit in `handle_input()`**

Add these branches before cursor movement:

```python
        if kb.matches(data, "tui.input.newLine"):
            self._add_newline()
            return
        if kb.matches(data, "tui.input.submit") or data == "\n":
            if self._should_submit_on_backslash_enter(data):
                self._delete_backward()
                self._add_newline()
                return
            self._submit_value()
            return
```

Change Up/Down branches to history-aware behavior:

```python
        if kb.matches(data, "tui.editor.cursorUp"):
            if not self._navigate_history(-1):
                self._move_up()
                self._request_render()
            return
        if kb.matches(data, "tui.editor.cursorDown"):
            if self.history_index != -1:
                self._navigate_history(1)
            else:
                self._move_down()
                self._request_render()
            return
```

Before printable insertion, add:

```python
            self._exit_history_mode()
```

- [ ] **Step 6: Run editor tests**

Run:

```bash
uv run pytest tests/test_editor.py -q
uv run ruff check src/saber_tui/components/editor.py tests/test_editor.py
```

Expected: both commands PASS.

- [ ] **Step 7: Commit**

Run:

```bash
git add src/saber_tui/components/editor.py tests/test_editor.py
git commit -m "Add editor submit newline and history"
```

Expected: commit succeeds.

### Task 11: Implement Kill Ring and Undo

**Files:**

- Modify: `src/saber_tui/components/editor.py`
- Modify: `tests/test_editor.py`

- [ ] **Step 1: Add failing kill ring and undo tests**

Append to `tests/test_editor.py`:

```python
def test_editor_kill_ring_and_yank() -> None:
    editor = _editor()
    editor.set_text("foo bar")

    editor.handle_input("\x17")
    assert editor.get_text() == "foo "

    editor.handle_input("\x19")
    assert editor.get_text() == "foo bar"


def test_editor_undo_restores_previous_text_and_cursor() -> None:
    editor = _editor()
    editor.handle_input("a")
    editor.handle_input("b")
    editor.handle_input(" ")
    editor.handle_input("c")

    editor.handle_input("\x1f")

    assert editor.get_text() == "ab "
    assert editor.get_cursor() == EditorCursor(0, 3)
```

- [ ] **Step 2: Run targeted tests and verify failure**

Run:

```bash
uv run pytest \
  tests/test_editor.py::test_editor_kill_ring_and_yank \
  tests/test_editor.py::test_editor_undo_restores_previous_text_and_cursor \
  -q
```

Expected: FAIL because kill ring and undo are absent.

- [ ] **Step 3: Add state and imports**

Add imports:

```python
from saber_tui.kill_ring import KillRing
from saber_tui.undo_stack import UndoStack
```

Add dataclass:

```python
@dataclass(frozen=True)
class _EditorState:
    lines: list[str]
    cursor_line: int
    cursor_col: int
```

In `Editor.__init__`, add:

```python
        self.kill_ring = KillRing()
        self.last_action: str | None = None
        self.undo_stack: UndoStack[_EditorState] = UndoStack()
```

- [ ] **Step 4: Add undo snapshot helpers**

Add methods:

```python
    def _snapshot(self) -> _EditorState:
        return _EditorState(list(self.lines), self.cursor_line, self.cursor_col)

    def _push_undo(self) -> None:
        self.undo_stack.push(self._snapshot())

    def _undo(self) -> None:
        snapshot = self.undo_stack.pop()
        if snapshot is None:
            return
        self.lines = list(snapshot.lines)
        self.cursor_line = snapshot.cursor_line
        self.cursor_col = snapshot.cursor_col
        self.last_action = None
        self._exit_history_mode()
        self._emit_change()
        self._request_render()
```

Call `_push_undo()` before text-changing methods:

- before printable insertion when starting a new undo unit
- before deletion when deletion will change text
- before `insert_text_at_cursor()`
- before `set_text()`

Use this minimal rule for the first pass:

```python
    def _before_text_change(self) -> None:
        if self.last_action != "type-word":
            self._push_undo()
        self.last_action = "type-word"
```

- [ ] **Step 5: Add kill/yank methods**

Add methods:

```python
    def _delete_word_backward(self) -> bool:
        self._clamp_cursor()
        if self.cursor_col == 0 and self.cursor_line == 0:
            return False
        original_line = self.cursor_line
        original_col = self.cursor_col
        while self.cursor_col > 0 and self.lines[self.cursor_line][self.cursor_col - 1].isspace():
            self.cursor_col -= 1
        while self.cursor_col > 0 and not self.lines[self.cursor_line][self.cursor_col - 1].isspace():
            self.cursor_col -= 1
        deleted = self.lines[original_line][self.cursor_col:original_col]
        self.lines[original_line] = (
            self.lines[original_line][: self.cursor_col] + self.lines[original_line][original_col:]
        )
        if deleted:
            self.kill_ring.push(deleted, prepend=True, accumulate=self.last_action == "kill")
            self.last_action = "kill"
            return True
        return False

    def _yank(self) -> None:
        text = self.kill_ring.peek()
        if not text:
            return
        self._push_undo()
        self._insert_text_at_cursor_internal(text)
        self.last_action = "yank"
        self._emit_change()
        self._request_render()

    def _yank_pop(self) -> None:
        if self.last_action != "yank" or len(self.kill_ring) <= 1:
            return
        previous = self.kill_ring.peek() or ""
        for _ in previous:
            self._delete_backward()
        self.kill_ring.rotate()
        self._insert_text_at_cursor_internal(self.kill_ring.peek() or "")
        self.last_action = "yank"
        self._emit_change()
        self._request_render()
```

- [ ] **Step 6: Wire key handling**

Add branches:

```python
        if kb.matches(data, "tui.editor.undo"):
            self._undo()
            return
        if kb.matches(data, "tui.editor.deleteWordBackward"):
            self._push_undo()
            if self._delete_word_backward():
                self._emit_change()
            self._request_render()
            return
        if kb.matches(data, "tui.editor.yank"):
            self._yank()
            return
        if kb.matches(data, "tui.editor.yankPop"):
            self._yank_pop()
            return
```

- [ ] **Step 7: Run editor tests**

Run:

```bash
uv run pytest tests/test_editor.py -q
uv run ruff check src/saber_tui/components/editor.py tests/test_editor.py
```

Expected: both commands PASS.

- [ ] **Step 8: Commit**

Run:

```bash
git add src/saber_tui/components/editor.py tests/test_editor.py
git commit -m "Add editor kill ring and undo"
```

Expected: commit succeeds.

## Phase 4: Editor Autocomplete Integration

### Task 12: Show and Apply Autocomplete Suggestions

**Files:**

- Modify: `src/saber_tui/components/editor.py`
- Modify: `tests/test_editor.py`

- [ ] **Step 1: Add failing editor autocomplete tests**

Append to `tests/test_editor.py`:

```python
from saber_tui.autocomplete import AutocompleteItem, AutocompleteSuggestions


class StaticProvider:
    def get_suggestions(self, lines, cursor_line, cursor_col, *, force=False, signal=None):
        return AutocompleteSuggestions([AutocompleteItem("help", "help", "Show help")], "/h")

    def apply_completion(self, lines, cursor_line, cursor_col, item, prefix):
        from saber_tui.autocomplete import CompletionResult

        line = lines[cursor_line]
        before = line[: cursor_col - len(prefix)]
        after = line[cursor_col:]
        new_line = before + "/" + item.value + " " + after
        return CompletionResult([new_line], cursor_line, len(before) + len(item.value) + 2)

    def should_trigger_file_completion(self, lines, cursor_line, cursor_col):
        return True


def test_editor_shows_and_applies_autocomplete() -> None:
    editor = _editor()
    editor.set_autocomplete_provider(StaticProvider())
    editor.handle_input("/")
    editor.handle_input("h")

    assert editor.is_showing_autocomplete() is True

    editor.handle_input("\r")

    assert editor.get_text() == "/help "
    assert editor.is_showing_autocomplete() is False
```

- [ ] **Step 2: Run targeted test and verify failure**

Run:

```bash
uv run pytest tests/test_editor.py::test_editor_shows_and_applies_autocomplete -q
```

Expected: FAIL because autocomplete state is not implemented.

- [ ] **Step 3: Add autocomplete state**

Add imports:

```python
from saber_tui.autocomplete import AutocompleteProvider, AutocompleteSuggestions
from saber_tui.components.select_list import SelectItem, SelectList
```

In `Editor.__init__`, add:

```python
        self.autocomplete_provider: AutocompleteProvider | None = None
        self.autocomplete_suggestions: AutocompleteSuggestions | None = None
        self.autocomplete_list: SelectList | None = None
```

Add methods:

```python
    def set_autocomplete_provider(self, provider: AutocompleteProvider) -> None:
        self.autocomplete_provider = provider
        self._clear_autocomplete()

    def is_showing_autocomplete(self) -> bool:
        return self.autocomplete_list is not None

    def _clear_autocomplete(self) -> None:
        self.autocomplete_suggestions = None
        self.autocomplete_list = None

    def _update_autocomplete(self, *, force: bool = False) -> None:
        if self.autocomplete_provider is None:
            return
        suggestions = self.autocomplete_provider.get_suggestions(
            self.get_lines(),
            self.cursor_line,
            self.cursor_col,
            force=force,
        )
        if inspect.isawaitable(suggestions):
            return
        if suggestions is None or not suggestions.items:
            self._clear_autocomplete()
            return
        self.autocomplete_suggestions = suggestions
        items = [SelectItem(item.value, item.label, item.description) for item in suggestions.items]
        self.autocomplete_list = SelectList(items, self.autocomplete_max_visible, self.theme.select_list)

    def _apply_autocomplete(self) -> bool:
        if (
            self.autocomplete_provider is None
            or self.autocomplete_suggestions is None
            or self.autocomplete_list is None
        ):
            return False
        selected = self.autocomplete_list.get_selected_item()
        if selected is None:
            return False
        item = next(item for item in self.autocomplete_suggestions.items if item.value == selected.value)
        self._push_undo()
        result = self.autocomplete_provider.apply_completion(
            self.get_lines(),
            self.cursor_line,
            self.cursor_col,
            item,
            self.autocomplete_suggestions.prefix,
        )
        self.lines = result.lines
        self.cursor_line = result.cursor_line
        self.cursor_col = result.cursor_col
        self._clear_autocomplete()
        self._emit_change()
        self._request_render()
        return True
```

Add `import inspect`.

- [ ] **Step 4: Wire autocomplete input and render**

In `handle_input()`:

- Before submit branch:

```python
        if self.autocomplete_list is not None:
            if kb.matches(data, "tui.select.up") or kb.matches(data, "tui.select.down"):
                self.autocomplete_list.handle_input(data)
                self._request_render()
                return
            if kb.matches(data, "tui.select.confirm"):
                if self._apply_autocomplete():
                    return
            if kb.matches(data, "tui.select.cancel"):
                self._clear_autocomplete()
                self._request_render()
                return
```

- After printable insertion:

```python
            self._update_autocomplete()
```

- For Tab:

```python
        if kb.matches(data, "tui.input.tab"):
            self._update_autocomplete(force=True)
            if self.autocomplete_suggestions is not None and len(self.autocomplete_suggestions.items) == 1:
                self._apply_autocomplete()
            return
```

In `render()`, before appending the bottom border, add:

```python
        if self.autocomplete_list is not None:
            rendered.extend(self.autocomplete_list.render(width))
```

- [ ] **Step 5: Run editor tests**

Run:

```bash
uv run pytest tests/test_editor.py -q
uv run ruff check src/saber_tui/components/editor.py tests/test_editor.py
```

Expected: both commands PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add src/saber_tui/components/editor.py tests/test_editor.py
git commit -m "Integrate autocomplete with editor"
```

Expected: commit succeeds.

## Phase 5: Advanced Parity

### Task 13: Add Character Jump and Page Movement

**Files:**

- Modify: `src/saber_tui/components/editor.py`
- Modify: `tests/test_editor.py`

- [ ] **Step 1: Add failing jump tests**

Append to `tests/test_editor.py`:

```python
def test_character_jump_forward_and_backward() -> None:
    editor = _editor()
    editor.set_text("abc\ndef")
    editor.handle_input("\x01")

    editor.handle_input("\x1d")  # ctrl+]
    editor.handle_input("e")

    assert editor.get_cursor() == EditorCursor(1, 1)

    editor.handle_input("\x1b[93;7u")  # ctrl+alt+] in Kitty CSI-u form
    editor.handle_input("b")

    assert editor.get_cursor() == EditorCursor(0, 1)
```

- [ ] **Step 2: Run jump test and verify failure**

Run:

```bash
uv run pytest tests/test_editor.py::test_character_jump_forward_and_backward -q
```

Expected: FAIL because jump mode is absent.

- [ ] **Step 3: Add jump state and methods**

In `Editor.__init__`, add:

```python
        self.jump_mode: str | None = None
```

Add methods:

```python
    def _jump_to_char(self, char: str, direction: str) -> None:
        if direction == "forward":
            for line_index in range(self.cursor_line, len(self.lines)):
                start = self.cursor_col + 1 if line_index == self.cursor_line else 0
                found = self.lines[line_index].find(char, start)
                if found != -1:
                    self.cursor_line = line_index
                    self.cursor_col = found
                    return
        else:
            for line_index in range(self.cursor_line, -1, -1):
                end = self.cursor_col if line_index == self.cursor_line else len(self.lines[line_index])
                found = self.lines[line_index].rfind(char, 0, end)
                if found != -1:
                    self.cursor_line = line_index
                    self.cursor_col = found
                    return
```

- [ ] **Step 4: Wire jump mode**

At the start of `handle_input()` after `kb = get_keybindings()`:

```python
        if self.jump_mode is not None:
            mode = self.jump_mode
            self.jump_mode = None
            if kb.matches(data, "tui.select.cancel"):
                self._request_render()
                return
            if data and all(ord(char) >= 32 and ord(char) != 0x7F for char in data):
                self._jump_to_char(data[0], mode)
                self.last_action = None
                self._request_render()
                return
```

Add branches before movement:

```python
        if kb.matches(data, "tui.editor.jumpForward"):
            self.jump_mode = None if self.jump_mode == "forward" else "forward"
            self._request_render()
            return
        if kb.matches(data, "tui.editor.jumpBackward"):
            self.jump_mode = None if self.jump_mode == "backward" else "backward"
            self._request_render()
            return
        if kb.matches(data, "tui.editor.pageUp"):
            self.cursor_line = max(0, self.cursor_line - 10)
            self.cursor_col = min(self.cursor_col, len(self.lines[self.cursor_line]))
            self._request_render()
            return
        if kb.matches(data, "tui.editor.pageDown"):
            self.cursor_line = min(len(self.lines) - 1, self.cursor_line + 10)
            self.cursor_col = min(self.cursor_col, len(self.lines[self.cursor_line]))
            self._request_render()
            return
```

- [ ] **Step 5: Run editor tests**

Run:

```bash
uv run pytest tests/test_editor.py -q
uv run ruff check src/saber_tui/components/editor.py tests/test_editor.py
```

Expected: both commands PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add src/saber_tui/components/editor.py tests/test_editor.py
git commit -m "Add editor character jump and page movement"
```

Expected: commit succeeds.

### Task 14: Add Sticky Visual Column and Wrapped Vertical Movement

**Files:**

- Modify: `src/saber_tui/components/editor.py`
- Modify: `tests/test_editor.py`

- [ ] **Step 1: Add failing sticky column tests**

Append to `tests/test_editor.py`:

```python
def test_sticky_column_preserves_target_through_shorter_line() -> None:
    editor = _editor()
    editor.set_text("abcdef\nxy\nabcdef")

    editor.handle_input("\x1b[A")
    assert editor.get_cursor() == EditorCursor(1, 2)

    editor.handle_input("\x1b[A")
    assert editor.get_cursor() == EditorCursor(0, 6)


def test_horizontal_movement_resets_sticky_column() -> None:
    editor = _editor()
    editor.set_text("abcdef\nxy\nabcdef")

    editor.handle_input("\x1b[A")
    editor.handle_input("\x1b[D")
    editor.handle_input("\x1b[A")

    assert editor.get_cursor() == EditorCursor(0, 1)
```

- [ ] **Step 2: Run targeted sticky tests and verify failure**

Run:

```bash
uv run pytest \
  tests/test_editor.py::test_sticky_column_preserves_target_through_shorter_line \
  tests/test_editor.py::test_horizontal_movement_resets_sticky_column \
  -q
```

Expected: FAIL because `_move_up()` and `_move_down()` do not preserve a target column.

- [ ] **Step 3: Add sticky column state**

In `Editor.__init__`, add:

```python
        self.preferred_visual_col: int | None = None
```

Add helpers:

```python
    def _current_visual_col(self) -> int:
        return visible_width(self.lines[self.cursor_line][: self.cursor_col])

    def _column_for_visual_col(self, line: str, target: int) -> int:
        current_width = 0
        for segment, start, end in _grapheme_spans(line):
            next_width = current_width + visible_width(segment)
            if next_width > target:
                return start
            current_width = next_width
            if current_width == target:
                return end
        return len(line)

    def _reset_sticky_column(self) -> None:
        self.preferred_visual_col = None
```

- [ ] **Step 4: Update vertical movement**

Replace `_move_up()` and `_move_down()` with:

```python
    def _move_up(self) -> None:
        self._clamp_cursor()
        if self.preferred_visual_col is None:
            self.preferred_visual_col = self._current_visual_col()
        if self.cursor_line > 0:
            self.cursor_line -= 1
            self.cursor_col = self._column_for_visual_col(self.lines[self.cursor_line], self.preferred_visual_col)

    def _move_down(self) -> None:
        self._clamp_cursor()
        if self.preferred_visual_col is None:
            self.preferred_visual_col = self._current_visual_col()
        if self.cursor_line < len(self.lines) - 1:
            self.cursor_line += 1
            self.cursor_col = self._column_for_visual_col(self.lines[self.cursor_line], self.preferred_visual_col)
```

Call `_reset_sticky_column()` inside horizontal movement, typing, deletion, undo, `set_text()`, and `insert_text_at_cursor()`.

- [ ] **Step 5: Run editor tests**

Run:

```bash
uv run pytest tests/test_editor.py -q
uv run ruff check src/saber_tui/components/editor.py tests/test_editor.py
```

Expected: both commands PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add src/saber_tui/components/editor.py tests/test_editor.py
git commit -m "Add editor sticky visual column"
```

Expected: commit succeeds.

### Task 15: Add Bracketed Paste and Large Paste Markers

**Files:**

- Modify: `src/saber_tui/components/editor.py`
- Modify: `tests/test_editor.py`

- [ ] **Step 1: Add failing paste tests**

Append to `tests/test_editor.py`:

```python
def test_bracketed_paste_inserts_small_paste_atomically() -> None:
    editor = _editor()

    editor.handle_input("\x1b[200~a\nb\x1b[201~")

    assert editor.get_text() == "a\nb"
    editor.handle_input("\x1f")
    assert editor.get_text() == ""


def test_large_paste_marker_expands_in_get_expanded_text() -> None:
    editor = _editor()
    pasted = "\n".join(f"line {index}" for index in range(12))

    editor.handle_input(f"\x1b[200~{pasted}\x1b[201~")

    assert "[paste #1" in editor.get_text()
    assert editor.get_expanded_text() == pasted
```

- [ ] **Step 2: Run targeted paste tests and verify failure**

Run:

```bash
uv run pytest \
  tests/test_editor.py::test_bracketed_paste_inserts_small_paste_atomically \
  tests/test_editor.py::test_large_paste_marker_expands_in_get_expanded_text \
  -q
```

Expected: FAIL because paste buffering and markers are absent.

- [ ] **Step 3: Add paste state**

In `Editor.__init__`, add:

```python
        self.is_in_paste = False
        self.paste_buffer = ""
        self.pastes: dict[int, str] = {}
        self.paste_counter = 0
```

Add methods:

```python
    def _paste_marker(self, content: str) -> str:
        self.paste_counter += 1
        paste_id = self.paste_counter
        self.pastes[paste_id] = content
        lines = content.split("\n")
        if len(lines) > 10:
            suffix = f"+{len(lines)} lines"
        else:
            suffix = f"{len(content)} chars"
        return f"[paste #{paste_id} {suffix}]"

    def _handle_paste(self, pasted_text: str) -> None:
        self._push_undo()
        normalized = self._normalize_text(pasted_text)
        text_to_insert = self._paste_marker(normalized) if len(normalized.split("\n")) > 10 else normalized
        self._insert_text_at_cursor_internal(text_to_insert)
        self.last_action = None
        self._emit_change()
        self._request_render()

    def get_expanded_text(self) -> str:
        text = self.get_text()
        for paste_id, content in self.pastes.items():
            text = re.sub(rf"\[paste #{paste_id}( \+\d+ lines| \d+ chars)?\]", content, text)
        return text
```

Add `import re`.

- [ ] **Step 4: Wire bracketed paste at the start of `handle_input()`**

Add this before keybinding dispatch:

```python
        if "\x1b[200~" in data:
            self.is_in_paste = True
            self.paste_buffer = ""
            data = data.replace("\x1b[200~", "")
        if self.is_in_paste:
            self.paste_buffer += data
            end_index = self.paste_buffer.find("\x1b[201~")
            if end_index != -1:
                paste_content = self.paste_buffer[:end_index]
                remaining = self.paste_buffer[end_index + len("\x1b[201~") :]
                self.is_in_paste = False
                self.paste_buffer = ""
                self._handle_paste(paste_content)
                if remaining:
                    self.handle_input(remaining)
            return
```

- [ ] **Step 5: Run editor tests**

Run:

```bash
uv run pytest tests/test_editor.py -q
uv run ruff check src/saber_tui/components/editor.py tests/test_editor.py
```

Expected: both commands PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add src/saber_tui/components/editor.py tests/test_editor.py
git commit -m "Add editor paste markers"
```

Expected: commit succeeds.

### Task 16: Add Async Autocomplete Cancellation and Debounce

**Files:**

- Modify: `src/saber_tui/components/editor.py`
- Modify: `src/saber_tui/autocomplete.py`
- Modify: `tests/test_editor.py`

- [ ] **Step 1: Add failing stale result test**

Append to `tests/test_editor.py`:

```python
class RecordingSignalProvider:
    def __init__(self) -> None:
        self.signals = []

    def get_suggestions(self, lines, cursor_line, cursor_col, *, force=False, signal=None):
        self.signals.append(signal)
        return AutocompleteSuggestions([AutocompleteItem("first", "first")], lines[cursor_line][:cursor_col])

    def apply_completion(self, lines, cursor_line, cursor_col, item, prefix):
        from saber_tui.autocomplete import CompletionResult

        return CompletionResult([item.value], 0, len(item.value))

    def should_trigger_file_completion(self, lines, cursor_line, cursor_col):
        return True


def test_new_autocomplete_request_aborts_previous_signal() -> None:
    provider = RecordingSignalProvider()
    editor = _editor()
    editor.set_autocomplete_provider(provider)

    editor.handle_input("@")
    editor.handle_input("a")

    assert len(provider.signals) >= 2
    assert provider.signals[0].aborted is True
    assert provider.signals[-1].aborted is False
```

- [ ] **Step 2: Run targeted test and verify failure**

Run:

```bash
uv run pytest tests/test_editor.py::test_new_autocomplete_request_aborts_previous_signal -q
```

Expected: FAIL because editor does not create cancellation tokens.

- [ ] **Step 3: Add cancellation token**

In `src/saber_tui/autocomplete.py`, add:

```python
class AutocompleteAbortSignal:
    def __init__(self) -> None:
        self.aborted = False

    def abort(self) -> None:
        self.aborted = True
```

Export it from `__all__` if an `__all__` list is added in that file. Add it to root exports only if tests need direct import.

- [ ] **Step 4: Use token in editor autocomplete requests**

In `src/saber_tui/components/editor.py`, import:

```python
from saber_tui.autocomplete import AutocompleteAbortSignal
```

In `Editor.__init__`, add:

```python
        self.autocomplete_signal: AutocompleteAbortSignal | None = None
```

At the start of `_update_autocomplete()`, add:

```python
        if self.autocomplete_signal is not None:
            self.autocomplete_signal.abort()
        self.autocomplete_signal = AutocompleteAbortSignal()
```

Pass `signal=self.autocomplete_signal` into provider `get_suggestions()`.

In `_clear_autocomplete()`, abort and clear the signal:

```python
        if self.autocomplete_signal is not None:
            self.autocomplete_signal.abort()
        self.autocomplete_signal = None
```

- [ ] **Step 5: Run tests**

Run:

```bash
uv run pytest tests/test_editor.py tests/test_autocomplete.py -q
uv run ruff check src/saber_tui/components/editor.py src/saber_tui/autocomplete.py tests/test_editor.py
```

Expected: both commands PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add src/saber_tui/components/editor.py src/saber_tui/autocomplete.py tests/test_editor.py
git commit -m "Add autocomplete cancellation token"
```

Expected: commit succeeds.

## Final Verification

### Task 17: Run Full Test and Static Checks

**Files:**

- Verify: all changed files

- [ ] **Step 1: Run full test suite**

Run:

```bash
uv run pytest -q
```

Expected: PASS.

- [ ] **Step 2: Run Ruff**

Run:

```bash
uv run ruff check
uv run ruff format --check
```

Expected: both commands PASS.

- [ ] **Step 3: Run type checker**

Run:

```bash
uvx ty check
```

Expected: PASS.

- [ ] **Step 4: Inspect public API manually**

Run:

```bash
uv run python - <<'PY'
from saber_tui import AutocompleteItem, CombinedAutocompleteProvider, EditorComponent
from saber_tui.components import Editor, EditorOptions, EditorTheme

print(AutocompleteItem("x", "x"))
print(CombinedAutocompleteProvider)
print(EditorComponent)
print(Editor, EditorOptions, EditorTheme)
PY
```

Expected output includes `AutocompleteItem(value='x', label='x', description=None)` and class/protocol objects for the other names.

- [ ] **Step 5: Check git status**

Run:

```bash
git status --short --branch
```

Expected: only intended source/test changes are present. `missing.md` may still appear as untracked if it was not committed separately.

- [ ] **Step 6: Commit final verification cleanup if any**

If formatting or small import fixes were required by the verification commands, commit only those changed files:

```bash
git add src/saber_tui tests
git commit -m "Polish editor autocomplete parity"
```

Expected: commit succeeds when cleanup changes exist. If there are no cleanup changes, skip this step.

## Coverage Checklist

Before marking the implementation complete, verify each spec section maps to passing tests or an explicit tracked follow-up:

- Public modules and exports: `tests/test_imports.py`
- Keybindings: `tests/test_keybindings.py`
- Generic fuzzy helpers: `tests/test_fuzzy.py`
- Autocomplete dataclasses/protocol/provider: `tests/test_autocomplete.py`
- Slash command suggestions: `tests/test_autocomplete.py`
- Path and quoted path completion: `tests/test_autocomplete.py`
- Optional `fd` attachment search: `tests/test_autocomplete.py`
- Editor accessors and state: `tests/test_editor.py`
- Rendering and wrapping: `tests/test_editor.py`
- Core editing: `tests/test_editor.py`
- Submit/newline/history: `tests/test_editor.py`
- Kill ring and undo: `tests/test_editor.py`
- Autocomplete UI integration: `tests/test_editor.py`
- Character jump: `tests/test_editor.py`
- Sticky visual column: `tests/test_editor.py`
- Paste markers: `tests/test_editor.py`
- Cancellation token behavior: `tests/test_editor.py`
