def test_package_imports() -> None:
    import saber_tui

    assert saber_tui.__all__


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
