from saber_tui.components import SelectItem, SelectList
from saber_tui.components.select_list import SelectListTheme
from saber_tui.utils import visible_width


def test_select_list_filters_and_selects_item() -> None:
    selected: list[SelectItem] = []
    items = [SelectItem("delete", "delete", "Delete last"), SelectItem("clear", "clear", "Clear all")]
    select = SelectList(items, max_visible=5)
    select.on_select = selected.append

    select.set_filter("cl")
    select.handle_input("\r")

    assert selected == [items[1]]


def test_select_list_wraps_selection() -> None:
    items = [SelectItem("one", "one"), SelectItem("two", "two")]
    select = SelectList(items, max_visible=5)

    select.handle_input("\x1b[A")

    assert select.get_selected_item() == items[1]


def test_select_list_render_lines_are_width_bounded() -> None:
    items = [
        SelectItem("alphabet-soup", "alphabet-soup", "A long command description"),
        SelectItem("bravo", "bravo", "Another long command description"),
    ]
    select = SelectList(items, max_visible=5)

    lines = select.render(12)

    assert lines
    assert all(visible_width(line) <= 12 for line in lines)


def test_select_list_cancel_callback() -> None:
    cancelled: list[bool] = []
    select = SelectList([SelectItem("one", "one")], max_visible=5)
    select.on_cancel = lambda: cancelled.append(True)

    select.handle_input("\x1b")

    assert cancelled == [True]


def test_select_list_selection_change_callback() -> None:
    changes: list[SelectItem] = []
    items = [SelectItem("one", "one"), SelectItem("two", "two")]
    select = SelectList(items, max_visible=5)
    select.on_selection_change = changes.append

    select.handle_input("\x1b[B")

    assert changes == [items[1]]


def test_select_list_empty_filter_renders_no_match_and_ignores_navigation() -> None:
    select = SelectList([SelectItem("one", "one")], max_visible=5)

    select.set_filter("missing")
    select.handle_input("\x1b[A")

    assert select.get_selected_item() is None
    assert all(visible_width(line) <= 10 for line in select.render(10))


def test_select_list_empty_filter_bounds_no_match_after_theme() -> None:
    theme = SelectListTheme(no_match=lambda text: text + " EXTRA")
    select = SelectList([SelectItem("one", "one")], max_visible=5, theme=theme)

    select.set_filter("missing")
    lines = select.render(10)

    assert all(visible_width(line) <= 10 for line in lines)
