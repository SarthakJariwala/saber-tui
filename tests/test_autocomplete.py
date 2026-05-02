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
