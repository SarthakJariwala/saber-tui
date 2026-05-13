from __future__ import annotations

from collections.abc import Callable

from saber_tui.components import SettingItem, SettingsList, SettingsListOptions, SettingsListTheme
from saber_tui.keys import set_kitty_protocol_active
from saber_tui.utils import visible_width


def _theme() -> SettingsListTheme:
    return SettingsListTheme(
        label=lambda text, selected: f"[L*{text}*]" if selected else f"[L{text}]",
        value=lambda text, selected: f"[V*{text}*]" if selected else f"[V{text}]",
        description=lambda text: f"[D{text}]",
        cursor="-> ",
        hint=lambda text: f"[H{text}]",
    )


def test_settings_list_cycles_values_with_enter_and_space() -> None:
    changes: list[tuple[str, str]] = []
    items = [
        SettingItem(
            id="theme",
            label="Theme",
            current_value="dark",
            values=["dark", "light", "system"],
        )
    ]
    settings = SettingsList(items, max_visible=10, theme=_theme(), on_change=lambda *change: changes.append(change))

    settings.handle_input("\r")
    settings.handle_input(" ")

    assert items[0].current_value == "system"
    assert changes == [("theme", "light"), ("theme", "system")]


def test_settings_list_wraps_navigation_and_can_cancel() -> None:
    cancelled: list[bool] = []
    items = [
        SettingItem(id="theme", label="Theme", current_value="dark"),
        SettingItem(id="model", label="Model", current_value="gpt-4"),
    ]
    settings = SettingsList(items, max_visible=10, theme=_theme(), on_cancel=lambda: cancelled.append(True))

    settings.handle_input("\x1b[A")
    settings.handle_input("\x1b")

    assert settings.get_selected_item() == items[1]
    assert cancelled == [True]


def test_settings_list_search_filters_by_label_and_resets_selection() -> None:
    items = [
        SettingItem(id="theme", label="Theme", current_value="dark"),
        SettingItem(id="model", label="Model", current_value="gpt-4"),
        SettingItem(id="thinking", label="Thinking level", current_value="high"),
    ]
    settings = SettingsList(
        items,
        max_visible=10,
        theme=_theme(),
        options=SettingsListOptions(enable_search=True),
    )

    settings.handle_input("mo")
    lines = settings.render(40)

    assert settings.get_selected_item() == items[1]
    assert any("Model" in line for line in lines)
    assert not any("Theme" in line for line in lines)
    assert not any("Thinking level" in line for line in lines)
    assert any("Type to search" in line for line in lines)


def test_settings_list_search_ignores_space_key_to_leave_space_available_for_activation() -> None:
    changes: list[tuple[str, str]] = []
    item = SettingItem(id="theme", label="Theme", current_value="dark", values=["dark", "light"])
    settings = SettingsList(
        [item],
        max_visible=10,
        theme=_theme(),
        on_change=lambda *change: changes.append(change),
        options=SettingsListOptions(enable_search=True),
    )

    settings.handle_input(" ")

    assert item.current_value == "light"
    assert changes == [("theme", "light")]
    assert settings.get_search_value() == ""


def test_settings_list_encoded_space_activates_even_with_search_enabled() -> None:
    changes: list[tuple[str, str]] = []
    item = SettingItem(id="theme", label="Theme", current_value="dark", values=["dark", "light"])
    settings = SettingsList(
        [item],
        max_visible=10,
        theme=_theme(),
        on_change=lambda *change: changes.append(change),
        options=SettingsListOptions(enable_search=True),
    )

    set_kitty_protocol_active(True)
    try:
        settings.handle_input("\x1b[32u")
    finally:
        set_kitty_protocol_active(False)

    assert item.current_value == "light"
    assert changes == [("theme", "light")]
    assert settings.get_search_value() == ""


def test_settings_list_renders_description_scroll_and_bounded_lines() -> None:
    items = [
        SettingItem(id=f"item-{index}", label=f"Setting {index}", current_value=f"value-{index}") for index in range(6)
    ]
    items[3].description = "A long description that should wrap over multiple narrow terminal lines."
    settings = SettingsList(items, max_visible=3, theme=_theme())

    settings.set_selected_index(3)
    lines = settings.render(28)

    assert any("(4/6)" in line for line in lines)
    assert any("description" in line for line in lines)
    assert all(visible_width(line) <= 28 for line in lines)


def test_settings_list_truncates_overwide_label_before_rendering_value() -> None:
    item = SettingItem(id="long", label="L" * 50, current_value="visible-value")
    settings = SettingsList([item], max_visible=5, theme=SettingsListTheme())

    lines = settings.render(55)

    assert "visible-value" in lines[0]
    assert visible_width(lines[0]) <= 55


def test_settings_list_update_value_updates_rendered_item() -> None:
    item = SettingItem(id="theme", label="Theme", current_value="dark", values=["dark", "light"])
    settings = SettingsList([item], max_visible=10, theme=_theme())

    settings.update_value("theme", "light")
    lines = settings.render(40)

    assert item.current_value == "light"
    assert any("light" in line for line in lines)


class _Submenu:
    def __init__(self, done: Callable[[str | None], None]) -> None:
        self.done = done
        self.inputs: list[str] = []
        self.invalidated = False

    def render(self, width: int) -> list[str]:
        return [f"submenu {width}"]

    def handle_input(self, data: str) -> None:
        self.inputs.append(data)
        if data == "x":
            self.done("gpt-5")

    def invalidate(self) -> None:
        self.invalidated = True


def test_settings_list_submenu_delegates_input_and_done_updates_value() -> None:
    changes: list[tuple[str, str]] = []
    opened_with: list[str] = []
    submenu_ref: list[_Submenu] = []

    def submenu(current_value: str, done: Callable[[str | None], None]) -> _Submenu:
        opened_with.append(current_value)
        component = _Submenu(done)
        submenu_ref.append(component)
        return component

    item = SettingItem(id="model", label="Model", current_value="gpt-4", submenu=submenu)
    settings = SettingsList([item], max_visible=10, theme=_theme(), on_change=lambda *change: changes.append(change))

    settings.handle_input("\r")

    assert opened_with == ["gpt-4"]
    assert settings.render(12) == ["submenu 12"]

    settings.invalidate()
    settings.handle_input("x")

    assert submenu_ref[0].invalidated is True
    assert submenu_ref[0].inputs == ["x"]
    assert item.current_value == "gpt-5"
    assert changes == [("model", "gpt-5")]
    assert settings.render(40) != ["submenu 40"]


def test_settings_list_submenu_done_without_value_closes_without_change() -> None:
    changes: list[tuple[str, str]] = []
    done_ref: list[Callable[[str | None], None]] = []

    def submenu(_current_value: str, done: Callable[[str | None], None]) -> _Submenu:
        done_ref.append(done)
        return _Submenu(done)

    item = SettingItem(id="model", label="Model", current_value="gpt-4", submenu=submenu)
    settings = SettingsList([item], max_visible=10, theme=_theme(), on_change=lambda *change: changes.append(change))

    settings.handle_input("\r")
    done_ref[0](None)

    assert item.current_value == "gpt-4"
    assert changes == []
    assert any("Model" in line for line in settings.render(40))


def test_settings_list_empty_and_no_match_states() -> None:
    empty = SettingsList([], max_visible=10, theme=_theme(), options=SettingsListOptions(enable_search=True))
    no_match = SettingsList(
        [SettingItem(id="theme", label="Theme", current_value="dark")],
        max_visible=10,
        theme=_theme(),
        options=SettingsListOptions(enable_search=True),
    )

    no_match.handle_input("z")

    assert any("No settings available" in line for line in empty.render(32))
    assert any("No matching settings" in line for line in no_match.render(32))
    assert all(visible_width(line) <= 32 for line in no_match.render(32))
