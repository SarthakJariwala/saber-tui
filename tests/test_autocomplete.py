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
