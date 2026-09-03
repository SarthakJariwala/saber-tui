from examples.showcase import (
    MARKDOWN_DEMO,
    PAGE_TITLES,
    _FilterableSelectList,
    build_app,
    go_to_page,
    make_global_listener,
)
from saber_tui.components import Markdown, SelectItem
from tests.virtual_terminal import VirtualTerminal


def test_filterable_select_list_filters_from_typed_input() -> None:
    changes: list[SelectItem] = []
    select = _FilterableSelectList(
        [
            SelectItem("welcome", "Go to: Welcome"),
            SelectItem("editor", "Go to: Editor"),
        ]
    )
    select.on_selection_change = changes.append

    select.handle_input("editor")

    assert [item.value for item in select.filtered_items] == ["editor"]
    assert changes == [select.filtered_items[0]]
    assert "editor" in "\n".join(select.render(60))


def test_showcase_includes_streaming_markdown_page() -> None:
    app = build_app(VirtualTerminal(columns=100, rows=40))

    go_to_page(app, 7)

    assert PAGE_TITLES[7] == "Markdown — streaming renderer"
    assert isinstance(app.markdown, Markdown)
    assert MARKDOWN_DEMO.startswith(app.markdown.text)
    assert app.markdown.text

    app._teardown_page()


def test_showcase_can_replay_markdown_stream() -> None:
    app = build_app(VirtualTerminal(columns=100, rows=40))
    go_to_page(app, 7)
    assert app.markdown is not None
    if app.markdown_timer is not None:
        app.markdown_timer.cancel()
    app.markdown.set_text(MARKDOWN_DEMO)

    result = make_global_listener(app)("r")

    assert result == {"consume": True}
    assert MARKDOWN_DEMO.startswith(app.markdown.text)
    assert app.markdown.text
    app._teardown_page()
