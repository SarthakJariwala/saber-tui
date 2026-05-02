from __future__ import annotations

import inspect
import os
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


PATH_DELIMITERS = {" ", "\t", '"', "'", "="}


def _to_display_path(value: str) -> str:
    if os.sep == "/":
        return value
    return value.replace(os.sep, "/")


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
    needs_quotes = is_quoted_prefix or any(delimiter in path_value for delimiter in PATH_DELIMITERS)
    prefix = "@" if is_at_prefix else ""
    if not needs_quotes:
        return f"{prefix}{path_value}"
    escaped_path_value = path_value.replace('"', '\\"')
    return f'{prefix}"{escaped_path_value}"'


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
        path_prefix = self._extract_path_prefix(text_before_cursor, force)
        if path_prefix is None:
            return None
        suggestions = self._get_file_suggestions(path_prefix)
        return AutocompleteSuggestions(suggestions, path_prefix) if suggestions else None

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
        if root_prefix or raw_prefix.endswith("/"):
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
        stripped = text_before_cursor.strip()
        return not (stripped.startswith("/") and " " not in stripped)
