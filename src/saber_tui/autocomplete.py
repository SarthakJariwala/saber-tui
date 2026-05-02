from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

from saber_tui.fuzzy import fuzzy_filter_items


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

    def should_trigger_file_completion(self, lines: list[str], cursor_line: int, cursor_col: int) -> bool: ...


type CommandLike = SlashCommand | AutocompleteItem


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
        awaitable = cast(Awaitable[list[AutocompleteItem] | None], value)
        return await awaitable
    return value


class CombinedAutocompleteProvider:
    def __init__(
        self,
        commands: Sequence[CommandLike] = (),
        base_path: str | Path | None = None,
        fd_path: str | Path | None = None,
    ) -> None:
        self.commands = list(commands)
        self.base_path = Path.cwd() if base_path is None else Path(base_path)
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

        is_slash_command = (
            prefix.startswith("/")
            and before_prefix.strip() == ""
            and "/" not in prefix[1:]
            and not item.value.startswith("/")
        )
        if is_slash_command:
            new_line = f"{before_prefix}/{item.value} {adjusted_after}"
            new_lines[cursor_line] = new_line
            return CompletionResult(new_lines, cursor_line, len(before_prefix) + len(item.value) + 2)

        new_line = before_prefix + item.value + adjusted_after
        new_lines[cursor_line] = new_line
        return CompletionResult(new_lines, cursor_line, len(before_prefix) + len(item.value))

    def should_trigger_file_completion(self, lines: list[str], cursor_line: int, cursor_col: int) -> bool:
        current_line = lines[cursor_line] if 0 <= cursor_line < len(lines) else ""
        text_before_cursor = current_line[:cursor_col]
        return not (text_before_cursor.strip().startswith("/") and " " not in text_before_cursor.strip())
