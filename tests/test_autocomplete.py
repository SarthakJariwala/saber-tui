import asyncio
import inspect
import os
import shutil
import subprocess

import pytest

from saber_tui.autocomplete import (
    AutocompleteAbortSignal,
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


def test_combined_autocomplete_provider_default_base_path_uses_current_working_directory(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)

    provider = CombinedAutocompleteProvider()

    assert provider.base_path == tmp_path


def test_apply_completion_clamps_out_of_range_cursor_line() -> None:
    provider = CombinedAutocompleteProvider()

    result = provider.apply_completion(["one", "tw"], 10, 2, AutocompleteItem("two", "two"), "tw")

    assert result.lines == ["one", "two"]
    assert result.cursor_line == 1
    assert result.cursor_col == 3


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

    delete_suggestions = provider.get_suggestions(["/"], 0, 1)

    assert delete_suggestions is not None
    assert AutocompleteItem("delete", "delete", "message-id - Delete last message") in delete_suggestions.items


def test_slash_command_completion_inserts_trailing_space() -> None:
    provider = CombinedAutocompleteProvider([SlashCommand("help", "Show help")], "/tmp")

    result = provider.apply_completion(["/he"], 0, 3, AutocompleteItem("help", "help"), "/he")

    assert result.lines == ["/help "]
    assert result.cursor_line == 0
    assert result.cursor_col == 6


def test_absolute_path_completion_at_line_start_replaces_prefix_without_slash_command_space() -> None:
    provider = CombinedAutocompleteProvider([], "/tmp")

    result = provider.apply_completion(["/t"], 0, 2, AutocompleteItem("/tmp/", "tmp/"), "/t")

    assert result.lines == ["/tmp/"]
    assert result.cursor_col == len("/tmp/")


def test_slash_command_argument_completion_replaces_argument_prefix() -> None:
    provider = CombinedAutocompleteProvider([SlashCommand("model", "Pick model")], "/tmp")

    result = provider.apply_completion(["/model gp"], 0, 9, AutocompleteItem("gpt-5", "gpt-5"), "gp")

    assert result.lines == ["/model gpt-5"]
    assert result.cursor_col == len("/model gpt-5")


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


@pytest.mark.skipif(os.sep != "/", reason="backslash is only a filename character on POSIX")
def test_path_completion_preserves_posix_backslash_filename(tmp_path) -> None:
    (tmp_path / "a\\b.txt").write_text("content")
    provider = CombinedAutocompleteProvider([], tmp_path)

    suggestions = provider.get_suggestions(["a\\"], 0, 2, force=True)

    assert suggestions is not None
    assert AutocompleteItem("a\\b.txt", "a\\b.txt") in suggestions.items
    assert AutocompleteItem("a/b.txt", "a\\b.txt") not in suggestions.items


def test_path_completion_quotes_paths_with_tabs(tmp_path) -> None:
    (tmp_path / "a\tb.txt").write_text("content")
    provider = CombinedAutocompleteProvider([], tmp_path)

    suggestions = provider.get_suggestions(["a"], 0, 1, force=True)

    assert suggestions is not None
    assert AutocompleteItem('"a\tb.txt"', "a\tb.txt") in suggestions.items


def test_path_completion_escapes_embedded_double_quotes(tmp_path) -> None:
    (tmp_path / 'a"b.txt').write_text("content")
    provider = CombinedAutocompleteProvider([], tmp_path)

    suggestions = provider.get_suggestions(["a"], 0, 1, force=True)

    assert suggestions is not None
    assert AutocompleteItem('"a\\"b.txt"', 'a"b.txt') in suggestions.items


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


def test_async_slash_command_argument_completions_are_returned_as_awaitable() -> None:
    provider = CombinedAutocompleteProvider(
        [
            SlashCommand(
                "model",
                "Pick model",
                get_argument_completions=_model_completions,
            )
        ],
        "/tmp",
    )

    result = provider.get_suggestions(["/model gp"], 0, 9)

    assert inspect.isawaitable(result)
    suggestions = asyncio.run(result)
    assert suggestions == AutocompleteSuggestions(
        [
            AutocompleteItem("gpt-5", "gpt-5", "frontier"),
            AutocompleteItem("gpt-5-mini", "gpt-5-mini", "small"),
        ],
        "gp",
    )


def test_async_slash_command_argument_completions_stop_after_signal_abort() -> None:
    signal = AutocompleteAbortSignal()
    provider = CombinedAutocompleteProvider(
        [
            SlashCommand(
                "model",
                "Pick model",
                get_argument_completions=_model_completions,
            )
        ],
        "/tmp",
    )

    result = provider.get_suggestions(["/model gp"], 0, 9, signal=signal)

    assert inspect.isawaitable(result)
    signal.abort()
    assert asyncio.run(result) is None


def test_invalid_slash_command_argument_completions_are_ignored() -> None:
    provider = CombinedAutocompleteProvider(
        [SlashCommand("model", "Pick model", get_argument_completions=lambda prefix: None)],
        "/tmp",
    )

    assert provider.get_suggestions(["/model gp"], 0, 9) is None


def test_at_completion_without_fd_returns_none_for_fuzzy_search(tmp_path) -> None:
    (tmp_path / "README.md").write_text("readme")
    provider = CombinedAutocompleteProvider([], tmp_path)

    assert provider.get_suggestions(["@read"], 0, 5) is None


def test_at_completion_with_fd_filters_git_paths_and_builds_items(tmp_path, monkeypatch) -> None:
    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(
            args,
            0,
            stdout="src/\nREADME.md\n.git/config\nnested/.git/config\n",
            stderr="",
        )

    monkeypatch.setattr("saber_tui.autocomplete.subprocess.run", fake_run)
    provider = CombinedAutocompleteProvider([], tmp_path, "/usr/bin/fd")

    suggestions = provider.get_suggestions(["@"], 0, 1)

    assert suggestions == AutocompleteSuggestions(
        [
            AutocompleteItem("@src/", "src/", "src"),
            AutocompleteItem("@README.md", "README.md", "README.md"),
        ],
        "@",
    )


def test_at_completion_with_fd_uses_query_separator_for_option_like_queries(tmp_path, monkeypatch) -> None:
    captured_args = []

    def fake_run(args, **kwargs):
        captured_args.append(args)
        return subprocess.CompletedProcess(args, 0, stdout="--flag.txt\n", stderr="")

    monkeypatch.setattr("saber_tui.autocomplete.subprocess.run", fake_run)
    provider = CombinedAutocompleteProvider([], tmp_path, "/usr/bin/fd")

    suggestions = provider.get_suggestions(["@--flag"], 0, 7)

    assert captured_args[-1][-2:] == ["--", "--flag"]
    assert suggestions is not None
    assert suggestions.items == [AutocompleteItem("@--flag.txt", "--flag.txt", "--flag.txt")]


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
