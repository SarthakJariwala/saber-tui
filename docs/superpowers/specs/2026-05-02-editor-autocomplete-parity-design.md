# Editor and Autocomplete Parity Design

Date: 2026-05-02

## Context

`saber_tui` is a faithful low-level Python port of `@mariozechner/pi-tui`.
The first implementation slice intentionally deferred the multiline editor,
autocomplete provider, markdown renderer, settings list, and terminal image
support. The current parity comparison in `missing.md` identifies the editor
and autocomplete stack as the largest user-facing gap.

The upstream source inspected for this design is:

- Clone: `/tmp/pi-mono-tui/packages/tui`
- Commit: `a44622670f8626b84f42885942c9ca340f823b5a`
- Primary upstream files:
  - `src/components/editor.ts`
  - `src/autocomplete.ts`
  - `src/editor-component.ts`
  - `test/editor.test.ts`
  - `test/autocomplete.test.ts`

The user approved a staged parity design: keep the full upstream behavior in
scope for the spec, but implement it in phases so the package can gain a usable
multiline editor before the hardest edge cases are complete.

## Goals

- Add a multiline `Editor` component that follows the existing component model:
  `render(width) -> list[str]`, optional `handle_input(data)`, optional
  `invalidate()`, and `Focusable` cursor marker behavior.
- Add the public autocomplete interfaces and `CombinedAutocompleteProvider`
  needed by the editor.
- Preserve Python naming conventions while keeping upstream concepts obvious.
- Reuse existing local primitives instead of adding a second editor framework:
  `TUI`, `SelectList`, `KillRing`, `UndoStack`, `keybindings`, `keys`, and
  `utils`.
- Make the editor useful before every upstream edge case is complete.
- Preserve a clear path to full parity with upstream tests.

## Non-Goals

- Do not implement Markdown rendering in this editor pass.
- Do not implement `SettingsList`.
- Do not implement terminal image protocols or the `Image` component.
- Do not replace the TUI renderer with prompt_toolkit, curses, Textual, or any
  other retained-mode framework.
- Do not make autocomplete require `fd`. `fd` is optional upstream and should
  remain optional in Python.
- Do not change the existing `Input` public API except for shared helpers that
  reduce duplication and preserve existing tests.

## Approach

Use a staged parity design.

Phase 1 adds the editor core:

- multiline state
- rendering
- cursor movement
- text editing
- submit/change callbacks
- prompt history
- kill/yank
- undo
- public accessors

Phase 2 adds autocomplete:

- data classes and protocols
- `CombinedAutocompleteProvider`
- slash command suggestions
- command argument completion
- file/path completion
- editor menu integration through `SelectList`

Phase 3 closes hard upstream parity gaps:

- large paste markers
- marker-aware segmentation
- sticky visual column through wrapped lines
- async/debounced autocomplete cancellation
- detailed upstream regression test translations

This lets implementation land in useful slices while avoiding a design that
pretends the upstream editor is small.

## Public Modules

### `saber_tui.editor_component`

Add an editor compatibility protocol for applications or extensions that want
to provide an editor-like component without depending on the concrete
`Editor` class.

Expected public names:

- `EditorComponent`

The protocol should require:

- `render(width: int) -> list[str]`
- `handle_input(data: str) -> None`
- `get_text() -> str`
- `set_text(text: str) -> None`
- `on_submit: Callable[[str], None] | None`
- `on_change: Callable[[str], None] | None`

The protocol should optionally allow:

- `add_to_history(text: str) -> None`
- `insert_text_at_cursor(text: str) -> None`
- `get_expanded_text() -> str`
- `set_autocomplete_provider(provider: AutocompleteProvider) -> None`
- `border_color: Callable[[str], str]`
- `set_padding_x(padding: int) -> None`
- `set_autocomplete_max_visible(max_visible: int) -> None`

Python cannot express all optional protocol attributes perfectly at runtime.
The concrete spec requirement is that static typing and import behavior are
useful, not that every optional method is runtime-enforced.

### `saber_tui.autocomplete`

Add reusable autocomplete interfaces and the combined provider.

Expected public names:

- `AutocompleteItem`
- `AbortSignalLike`
- `SlashCommand`
- `AutocompleteSuggestions`
- `AutocompleteProvider`
- `CompletionResult`
- `CombinedAutocompleteProvider`

Suggested Python shapes:

```python
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
    get_argument_completions: Callable[[str], Awaitable[list[AutocompleteItem] | None]] | None = None


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
```

The provider protocol should expose:

```python
type SuggestionResult = AutocompleteSuggestions | None
type MaybeAwaitableSuggestionResult = SuggestionResult | Awaitable[SuggestionResult]


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

    def should_trigger_file_completion(
        self,
        lines: list[str],
        cursor_line: int,
        cursor_col: int,
    ) -> bool: ...
```

`AbortSignalLike` is intentionally small. It exists so synchronous providers can
ignore cancellation while async or subprocess-backed providers can return early
when newer editor input supersedes the request.

### `saber_tui.components.editor`

Add the concrete editor component.

Expected public names:

- `Editor`
- `EditorCursor`
- `EditorTheme`
- `EditorOptions`
- `TextChunk`
- `word_wrap_line`

Suggested Python shapes:

```python
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
    border_color: Callable[[str], str]
    select_list: SelectListTheme


@dataclass(frozen=True)
class EditorOptions:
    padding_x: int = 0
    autocomplete_max_visible: int = 5
```

`Editor` should implement `Component` and `Focusable`.

Constructor:

```python
Editor(tui: TUI, theme: EditorTheme, options: EditorOptions | None = None)
```

Public attributes:

- `focused: bool`
- `border_color: Callable[[str], str]`
- `on_submit: Callable[[str], None] | None`
- `on_change: Callable[[str], None] | None`
- `disable_submit: bool`

Public methods:

- `get_padding_x() -> int`
- `set_padding_x(padding: int) -> None`
- `get_autocomplete_max_visible() -> int`
- `set_autocomplete_max_visible(max_visible: int) -> None`
- `set_autocomplete_provider(provider: AutocompleteProvider) -> None`
- `add_to_history(text: str) -> None`
- `get_text() -> str`
- `get_expanded_text() -> str`
- `get_lines() -> list[str]`
- `get_cursor() -> EditorCursor`
- `set_text(text: str) -> None`
- `insert_text_at_cursor(text: str) -> None`
- `is_showing_autocomplete() -> bool`
- `invalidate() -> None`
- `render(width: int) -> list[str]`
- `handle_input(data: str) -> None`

## Editor State Model

The editor stores logical text as:

- `lines: list[str]`
- `cursor_line: int`
- `cursor_col: int`

Cursor positions are string indices into the logical Python string for each
line. Display positions are derived through grapheme segmentation and
`visible_width()`.

Internal state also includes:

- last render width
- vertical scroll offset
- prompt history and history index
- kill ring
- last edit action
- undo stack
- optional autocomplete provider
- optional autocomplete list
- autocomplete state and prefix
- optional pending autocomplete task/cancellation state
- large paste registry and paste counter
- paste buffer state
- jump mode
- preferred visual column
- marker navigation state for paste markers

The editor should expose defensive copies for lists and cursor state. External
callers should not be able to mutate editor internals by changing values
returned from accessors.

## Rendering Design

`Editor.render(width)` returns a list of strings that each fit `width`.

Rendering requirements:

- Render a top border line and a bottom border line.
- Render editor content between the borders.
- Apply `padding_x` to content lines.
- Use `border_color` for border styling.
- Use `CURSOR_MARKER` only when `focused` is true.
- Use inverse-video cursor cell rendering to match existing `Input` behavior.
- Keep the hardware cursor marker zero-width.
- Never exceed the passed width, including ANSI styling.
- Preserve wide-character correctness for CJK, emoji, Thai/Lao AM clusters,
  and regional indicators as far as existing `utils` supports them.
- Use `word_wrap_line()` for wrapping logical lines into visual lines.
- Recompute layout when width changes.
- Render autocomplete suggestions below the editor content when active, using
  `SelectList`.

`word_wrap_line(line, max_width, pre_segmented=None)` should be public because
upstream exports and tests it directly. It should:

- return at least one `TextChunk`
- wrap at word boundaries where possible
- force-break long words where necessary
- preserve multiple spaces where upstream does
- handle wide characters by visible width
- support marker-aware segmentation for large paste markers

## Input Handling

`Editor.handle_input(data)` dispatches through existing keybindings.

Required bindings:

- `tui.editor.cursorUp`
- `tui.editor.cursorDown`
- `tui.editor.cursorLeft`
- `tui.editor.cursorRight`
- `tui.editor.cursorWordLeft`
- `tui.editor.cursorWordRight`
- `tui.editor.cursorLineStart`
- `tui.editor.cursorLineEnd`
- `tui.editor.jumpForward`
- `tui.editor.jumpBackward`
- `tui.editor.pageUp`
- `tui.editor.pageDown`
- `tui.editor.deleteCharBackward`
- `tui.editor.deleteCharForward`
- `tui.editor.deleteWordBackward`
- `tui.editor.deleteWordForward`
- `tui.editor.deleteToLineStart`
- `tui.editor.deleteToLineEnd`
- `tui.editor.yank`
- `tui.editor.yankPop`
- `tui.editor.undo`
- `tui.input.newLine`
- `tui.input.submit`
- `tui.input.tab`
- `tui.select.*` while autocomplete menu is active

`keybindings.py` must add upstream-missing local defaults:

- `tui.editor.jumpForward`: `ctrl+]`
- `tui.editor.jumpBackward`: `ctrl+alt+]`
- `tui.editor.pageUp`: `pageUp`
- `tui.editor.pageDown`: `pageDown`

Printable input should use existing key decoders:

- `decode_printable_key()`
- `decode_kitty_printable()`, where appropriate
- legacy printable data when it contains no control characters

The editor should reject C0, DEL, and C1 controls as literal text outside
recognized terminal key sequences.

## Editing Behavior

Required edit operations:

- Insert printable text at cursor.
- Insert multiline text through `insert_text_at_cursor()`.
- Normalize CRLF and CR line endings to `\n`.
- Backspace deletes one grapheme before the cursor.
- Forward delete deletes one grapheme after the cursor.
- Backspace at line start joins with the previous line.
- Forward delete at line end joins with the next line.
- Delete word backward and forward.
- Delete to line start.
- Delete to line end.
- Delete newline where upstream `Ctrl+K` and `Alt+D` do.
- Move line start/end.
- Move word backward/forward.
- Move up/down across logical and wrapped visual lines.
- Page up/down by visible editor page.
- Submit current value on Enter when submit is enabled.
- Insert newline on configured newline binding.
- Include upstream backslash+Enter workaround:
  a standalone backslash immediately before cursor is converted to newline on
  Enter, while normal typed backslashes remain regular characters.

`on_change` should fire after text-changing operations. It should not fire for
pure cursor movement, failed no-op operations, or render-only changes.

`on_submit` should receive `get_expanded_text()`, not marker-compressed text,
so large pasted content submits literally.

After submit:

- clear undo history
- exit history browsing
- cancel autocomplete
- preserve caller control over whether editor text is cleared

## Prompt History

History behavior mirrors upstream:

- `add_to_history("")` and whitespace-only text do nothing.
- Consecutive duplicate entries are ignored.
- Non-consecutive duplicates are allowed.
- History keeps the newest 100 entries.
- Up arrow on an empty editor enters history browsing at the most recent entry.
- Repeated Up moves toward older entries.
- Down moves toward newer entries.
- Down after the newest entry returns to an empty editor.
- If a non-empty multiline entry is active, Up/Down first move within visual
  lines before changing history entries.
- Typing, `set_text()`, and undo exit history browsing.
- Undo restores the pre-history state after history navigation.

## Kill Ring

The editor uses the existing `KillRing`.

Required behavior:

- `Ctrl+W` saves deleted text and yanks it with `Ctrl+Y`.
- `Ctrl+U` saves deleted text.
- `Ctrl+K` saves deleted text.
- `Alt+D` saves forward-deleted word text.
- Consecutive kill operations accumulate into one kill ring entry.
- Backward deletions prepend during accumulation.
- Forward deletions append during accumulation.
- Non-delete actions break kill accumulation.
- `Alt+Y` only works immediately after yank.
- `Alt+Y` rotates the kill ring and replaces the previously yanked text.
- Multiline yanks work in the middle of text.
- Empty kill ring operations are no-ops.

## Undo

The editor uses `UndoStack[EditorState]`.

Undo requirements:

- Consecutive word characters coalesce into one undo unit.
- Spaces are undone one at a time.
- Newlines are undoable.
- Backspace and forward delete are undoable.
- Word deletion and line deletion are undoable.
- Yank and yank-pop are undoable.
- Paste is undoable atomically.
- `insert_text_at_cursor()` is undoable atomically.
- `set_text("")` is undoable.
- Submit clears undo history.
- Cursor movement starts a new undo unit.
- No-op deletions do not push undo snapshots.
- Autocomplete application is undoable.

## Paste Behavior

The editor should support normal and bracketed paste.

Base paste behavior:

- Buffer bracketed paste from `\x1b[200~` through `\x1b[201~`.
- Insert small pasted text literally.
- Normalize line endings.
- Decode printable CSI-u sequences inside paste where upstream does.
- Do not trigger autocomplete during paste.
- Push one undo snapshot for the entire paste.

Large paste marker behavior belongs to Phase 3 but is part of the final spec:

- Large pastes produce markers such as `[paste #1 +50 lines]` or
  `[paste #2 1234 chars]`.
- The original pasted content is stored in a paste registry.
- `get_text()` returns marker-compressed text.
- `get_expanded_text()` expands markers back to literal pasted content.
- Submit uses expanded text.
- Cursor movement treats valid paste markers as atomic units.
- Backspace and delete treat valid paste markers as atomic units.
- Word movement treats valid paste markers as atomic units.
- Manually typed marker-like text is not atomic unless its ID exists in the
  paste registry.
- Oversized markers must not make rendering exceed terminal width.

## Character Jump

Character jump mirrors upstream:

- `Ctrl+]` enters forward jump mode.
- `Ctrl+Alt+]` enters backward jump mode.
- The next printable key searches for that exact character.
- Forward jump searches after the cursor and across later lines.
- Backward jump searches before the cursor and across earlier lines.
- Search is case-sensitive.
- Pressing the same jump binding again cancels jump mode.
- Escape cancels jump mode and then processes Escape normally.
- Failed searches leave the cursor unchanged.
- Jumping resets edit action state so kill/yank coalescing does not continue
  across a jump.

## Sticky Visual Column

The editor should preserve a preferred visual column through vertical movement.

Requirements:

- Consecutive Up/Down movements retain a target visual column.
- Moving through shorter lines lands at the nearest valid column.
- Horizontal movement clears the preferred column.
- Typing clears it.
- Backspace/delete clears it.
- Line start/end clears it.
- Word movement clears it.
- Undo clears it.
- `set_text()` clears it.
- Width changes should remap the preferred visual column using current layout.
- Wrapped visual lines count as vertical movement targets.
- Paste marker continuation lines must not trap the cursor in an infinite or
  stuck movement state.

## Autocomplete Provider Behavior

`CombinedAutocompleteProvider` supports both slash commands and paths.

Constructor:

```python
CombinedAutocompleteProvider(
    commands: Sequence[SlashCommand | AutocompleteItem] = (),
    base_path: str | Path = Path.cwd(),
    fd_path: str | Path | None = None,
)
```

Slash command behavior:

- If the current text before cursor starts with `/` and has no space, return
  slash command suggestions.
- Match command names fuzzily.
- Include command descriptions.
- Include argument hints in descriptions when provided.
- Applying a command completion inserts `/<command> `.

Slash argument behavior:

- If text is `/command <argument-prefix>`, find the matching slash command.
- If the command has `get_argument_completions`, call it.
- Ignore invalid non-list completion results.
- Support sync or async completers.
- Applying an argument completion replaces only the argument prefix.
- If the typed argument exactly matches a suggestion, Enter should apply the
  exact typed value rather than blindly taking the highlighted first item.

Path completion behavior:

- Forced completion through Tab may extract a path prefix even when natural
  triggers would not.
- Do not treat `/model` at the start of a line as a file path during forced
  completion; that is a slash command.
- Trigger for absolute paths after slash command arguments.
- Natural path completion triggers for path-looking prefixes:
  `/`, `./`, `../`, `~/`, strings containing `/`, and quoted path contexts.
- Preserve `./` prefixes.
- Expand `~` and `~/` for lookup while preserving display values.
- Return directories with trailing `/`.
- Sort directories before files.
- Follow symlinked directories where practical.
- Quote completions when paths contain spaces or when completion occurs inside
  a quoted prefix.
- Applying quoted completions must not duplicate closing quotes.

`@file` behavior:

- `@` starts attachment completion.
- `@"` starts quoted attachment completion.
- Empty `@` query returns available files and folders where supported.
- If `fd_path` is provided, use it for fuzzy recursive search.
- Include hidden paths but exclude `.git`.
- Support scoped fuzzy search such as `@../outside/a`.
- Match nested paths and directories in the middle of paths.
- Limit fuzzy results to a manageable number, matching upstream's intent of
  returning the top results.

Fallback without `fd`:

- Direct path completion must work without `fd`.
- Fuzzy recursive `@` search may return no suggestions when `fd_path` is not
  provided. This is acceptable and should be documented.

## Editor Autocomplete Integration

The editor owns UI state for autocomplete but delegates suggestion logic to the
provider.

Behavior:

- `set_autocomplete_provider(provider)` installs a provider and cancels any
  existing autocomplete state.
- Tab triggers forced file completion if the provider allows it.
- Typing `/` at the start of a message triggers slash command suggestions when
  a provider is installed.
- Typing in slash command context updates suggestions.
- Typing in `@` context triggers attachment suggestions.
- Typing in `#` symbol-completion context asks the installed provider for
  regular suggestions and uses the same debounce path as `@`.
- Backspacing out of a trigger context hides autocomplete.
- Escape hides autocomplete before invoking any broader cancel behavior.
- Up/Down navigate the autocomplete `SelectList`.
- Enter applies the selected suggestion when autocomplete is active.
- If forced file completion has exactly one suggestion, auto-apply it without
  showing a menu.
- If forced file completion has multiple suggestions, show the menu.
- Applying a completion pushes one undo snapshot.
- Autocomplete UI must render width-bounded lines.
- Autocomplete max visible count is clamped to an upstream-compatible range:
  minimum 3, maximum 20, default 5.

Async and debounce behavior:

- Providers may be synchronous or asynchronous.
- Regular slash completion should update promptly.
- Attachment and symbol-style fuzzy completion debounce for 20 ms to match
  upstream's `ATTACHMENT_AUTOCOMPLETE_DEBOUNCE_MS`.
- A newer request cancels or supersedes older in-flight requests.
- Stale results must not overwrite newer editor state.
- Cancellation should be implemented with Python's standard async primitives or
  a small local cancellation token, not by requiring a third-party framework.

## Fuzzy Matching Compatibility

Autocomplete and settings-style filtering depend on upstream fuzzy semantics.
The spec requires either:

1. Add upstream-compatible generic fuzzy helpers while preserving the current
   local `fuzzy_match()` and `fuzzy_filter()` APIs, or
2. Change local fuzzy APIs in a backwards-compatible way using overloads or new
   names.

Recommended API:

- Keep existing `fuzzy_match(query, value) -> FuzzyMatch | None` for current
  callers.
- Add `fuzzy_match_score(query, text) -> FuzzyScore`, where `FuzzyScore` has
  `matches: bool` and `score: float`.
- Add `fuzzy_filter_items(items, query, get_text) -> list[T]`.

`fuzzy_filter_items()` should match upstream behavior:

- empty query returns the original items unchanged
- all space-separated tokens must match
- lower total score sorts first
- match is case-insensitive
- word-boundary and consecutive matches rank better
- swapped alpha/numeric tokens can match with a small penalty

This avoids breaking existing tests while giving autocomplete the API shape it
needs.

## Error Handling

Editor and autocomplete should be defensive but not silent about programming
errors that would corrupt rendering.

Required handling:

- Clamp invalid cursor state before edits and renders.
- Treat out-of-range cursor line/column as recoverable by clamping.
- Treat missing provider suggestions as no autocomplete UI.
- Treat provider exceptions as no suggestions for interactive use.
- Preserve stale request suppression for async completions.
- Never return lines wider than `width`; truncate or adjust before returning.
- Avoid raising for inaccessible directories during completion.
- Avoid following broken symlinks as directories.
- Avoid invoking callbacks when no meaningful state changed.
- Do not let autocomplete provider failures leave the editor in an inconsistent
  menu state.

Testing should still cover the cases that upstream treats as invariants, such
as width-bounded rendering and marker-aware cursor movement.

## Public Exports

Update `src/saber_tui/__init__.py` to export:

- `AutocompleteItem`
- `AutocompleteProvider`
- `AutocompleteSuggestions`
- `CombinedAutocompleteProvider`
- `CompletionResult`
- `EditorComponent`
- `SlashCommand`

Update `src/saber_tui/components/__init__.py` to export:

- `Editor`
- `EditorCursor`
- `EditorOptions`
- `EditorTheme`
- `TextChunk`
- `word_wrap_line`

Root exports for utility functions are useful but not required for this editor
spec. If added, they should be treated as a separate small API cleanup.

## Dependency Decisions

No new required runtime dependency is needed for Phase 1.

Phase 2 and Phase 3 should prefer the standard library:

- `pathlib` and `os.scandir()` for direct path completion
- `asyncio` for async provider support if needed
- `subprocess` for optional `fd` integration
- existing `regex` and `wcwidth` for grapheme/width behavior

Do not add a required dependency for `fd`; accept an optional `fd_path`.

## Test Plan

Add `tests/test_editor.py`.

Coverage groups:

- public state accessors
- text insertion and submission
- line ending normalization
- multiline insertion
- render width bounds
- cursor marker placement
- prompt history navigation
- Unicode and grapheme editing
- word wrapping and `word_wrap_line()`
- kill ring behavior
- undo behavior
- character jump
- sticky visual column
- bracketed paste
- large paste markers
- autocomplete integration

Add `tests/test_autocomplete.py`.

Coverage groups:

- slash command suggestions
- slash command descriptions and argument hints
- slash argument completions
- forced file completion
- natural path completion
- quoted path completion
- `./`, `../`, absolute path, and `~/` behavior
- `@` attachment suggestions
- optional `fd` tests skipped when `fd` is unavailable
- completion application cursor placement
- stale/cancelled async result suppression

Update `tests/test_keybindings.py`.

Coverage:

- new editor bindings exist
- user overrides do not evict unrelated defaults
- direct user conflicts are reported without deleting defaults

Update `tests/test_fuzzy.py`.

Coverage:

- upstream-compatible scoring helper
- generic item filtering
- multi-token filtering
- custom text extraction
- alpha/numeric swapped query matching

Update `tests/test_imports.py`.

Coverage:

- new root exports import
- new component exports import

## Acceptance Criteria

Phase 1 is accepted when:

- `Editor` can be imported from `saber_tui.components`.
- `Editor` renders width-bounded multiline content with cursor markers.
- Basic multiline edit operations work.
- Submit and change callbacks work.
- Prompt history works.
- Kill/yank works.
- Undo works.
- Unicode and grapheme editing behavior is covered by tests.
- Existing tests still pass.

Phase 2 is accepted when:

- `saber_tui.autocomplete` exports the approved public API.
- `CombinedAutocompleteProvider` handles slash commands and direct path
  completion.
- `Editor` can show, navigate, and apply autocomplete suggestions.
- Autocomplete application is undoable.
- Optional `fd` tests skip cleanly when `fd` is unavailable.
- Existing tests still pass.

Phase 3 is accepted when:

- Large paste markers match upstream behavior.
- Sticky visual column tests pass.
- Character jump tests pass.
- Async/debounce/cancellation behavior is tested.
- Upstream `editor.test.ts` and `autocomplete.test.ts` cases have either a
  Python equivalent or a documented Python-specific reason for omission.
- Existing tests still pass.

Full spec acceptance is reached when all three phases are complete.

## Risks

- The upstream editor is large and stateful. A direct one-shot port risks
  regressions in cursor movement, undo, and paste behavior.
- Python string indices and JavaScript string indices differ for some Unicode
  cases. Tests should assert behavior instead of assuming index parity.
- Async autocomplete may be awkward in a synchronous TUI loop. The design keeps
  provider support flexible so implementation can start synchronous and add
  async behavior deliberately.
- `fd` behavior varies by platform and installation. Tests must skip optional
  `fd` cases when unavailable.
- Large paste marker behavior interacts with wrapping and cursor movement. It
  should be isolated behind segmentation helpers and covered heavily.

## Implementation Notes

- Start by porting public dataclasses/protocols and exports so tests can import
  target APIs.
- Add missing keybindings before editor input tests.
- Consider extracting shared grapheme, whitespace, punctuation, and text
  sanitization helpers from `Input` into `utils.py` if it reduces duplication.
- Keep `Input` tests passing when helpers move.
- Build editor state mutation methods first, then rendering, then integration
  with TUI render requests.
- Keep autocomplete provider tests separate from editor integration tests.
- Do not hide width overflow with broad exception handling. Render methods must
  actively bound their output.
