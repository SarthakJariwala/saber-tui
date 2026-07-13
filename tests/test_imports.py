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


def test_markdown_exports_import() -> None:
    import saber_tui
    import saber_tui.components as components

    assert saber_tui.Markdown is components.Markdown
    assert saber_tui.MarkdownTheme is components.MarkdownTheme
    assert saber_tui.MarkdownOptions is components.MarkdownOptions
    assert saber_tui.DefaultTextStyle is components.DefaultTextStyle


def test_settings_list_exports_import() -> None:
    import saber_tui
    import saber_tui.components as components

    assert saber_tui.SettingItem is components.SettingItem
    assert saber_tui.SettingsList is components.SettingsList
    assert saber_tui.SettingsListOptions is components.SettingsListOptions
    assert saber_tui.SettingsListTheme is components.SettingsListTheme
