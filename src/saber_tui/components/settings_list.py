from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from saber_tui.components.input import Input
from saber_tui.fuzzy import fuzzy_filter_items
from saber_tui.keybindings import get_keybindings
from saber_tui.keys import matches_key
from saber_tui.tui import Component
from saber_tui.utils import truncate_to_width, visible_width, wrap_text_with_ansi


def _identity(text: str) -> str:
    return text


def _label_identity(text: str, _selected: bool) -> str:
    return text


def _value_identity(text: str, _selected: bool) -> str:
    return text


def _noop_change(_id: str, _new_value: str) -> None:
    return None


def _noop_cancel() -> None:
    return None


type SettingsSubmenuFactory = Callable[[str, Callable[[str | None], None]], Component]


@dataclass
class SettingItem:
    id: str
    label: str
    current_value: str
    description: str | None = None
    values: list[str] | None = None
    submenu: SettingsSubmenuFactory | None = None


@dataclass(frozen=True)
class SettingsListTheme:
    label: Callable[[str, bool], str] = _label_identity
    value: Callable[[str, bool], str] = _value_identity
    description: Callable[[str], str] = _identity
    cursor: str = "-> "
    hint: Callable[[str], str] = _identity


@dataclass(frozen=True)
class SettingsListOptions:
    enable_search: bool = False


class SettingsList:
    def __init__(
        self,
        items: list[SettingItem],
        max_visible: int = 5,
        theme: SettingsListTheme | None = None,
        on_change: Callable[[str, str], None] | None = None,
        on_cancel: Callable[[], None] | None = None,
        options: SettingsListOptions | None = None,
    ) -> None:
        self.items = items
        self.filtered_items = items
        self.theme = theme or SettingsListTheme()
        self.selected_index = 0
        self.max_visible = max_visible
        self.on_change = on_change or _noop_change
        self.on_cancel = on_cancel or _noop_cancel
        self.options = options or SettingsListOptions()
        self.search_input = Input() if self.options.enable_search else None

        self._submenu_component: Component | None = None
        self._submenu_item_index: int | None = None

    def update_value(self, id: str, new_value: str) -> None:
        for item in self.items:
            if item.id == id:
                item.current_value = new_value
                return

    def set_selected_index(self, index: int) -> None:
        display_items = self._get_display_items()
        if not display_items:
            self.selected_index = 0
            return
        self.selected_index = max(0, min(index, len(display_items) - 1))

    def get_selected_item(self) -> SettingItem | None:
        display_items = self._get_display_items()
        if 0 <= self.selected_index < len(display_items):
            return display_items[self.selected_index]
        return None

    def get_search_value(self) -> str:
        return self.search_input.get_value() if self.search_input is not None else ""

    def invalidate(self) -> None:
        invalidate = getattr(self._submenu_component, "invalidate", None)
        if invalidate is not None:
            invalidate()

    def render(self, width: int) -> list[str]:
        if self._submenu_component is not None:
            return self._submenu_component.render(width)
        if width <= 0:
            return [""]
        return self._render_main_list(width)

    def handle_input(self, data: str) -> None:
        if self._submenu_component is not None:
            handle_input = getattr(self._submenu_component, "handle_input", None)
            if handle_input is not None:
                handle_input(data)
            return

        kb = get_keybindings()
        display_items = self._get_display_items()

        if kb.matches(data, "tui.select.up"):
            if display_items:
                self.selected_index = len(display_items) - 1 if self.selected_index == 0 else self.selected_index - 1
            return

        if kb.matches(data, "tui.select.down"):
            if display_items:
                self.selected_index = 0 if self.selected_index == len(display_items) - 1 else self.selected_index + 1
            return

        if kb.matches(data, "tui.select.confirm") or matches_key(data, "space"):
            self._activate_item()
            return

        if kb.matches(data, "tui.select.cancel"):
            self.on_cancel()
            return

        if self.search_input is not None:
            sanitized = data.replace(" ", "")
            if not sanitized:
                return
            self.search_input.handle_input(sanitized)
            self._apply_filter(self.search_input.get_value())

    def _render_main_list(self, width: int) -> list[str]:
        lines: list[str] = []

        if self.search_input is not None:
            lines.extend(self._bound_lines(self.search_input.render(width), width))
            lines.append("")

        if not self.items:
            lines.append(self._bound_line(self.theme.hint("  No settings available"), width))
            if self.search_input is not None:
                self._add_hint_line(lines, width)
            return lines

        display_items = self._get_display_items()
        if not display_items:
            lines.append(self._bound_line(self.theme.hint("  No matching settings"), width))
            self._add_hint_line(lines, width)
            return lines

        max_visible = max(1, self.max_visible)
        start_index = max(0, min(self.selected_index - max_visible // 2, len(display_items) - max_visible))
        end_index = min(start_index + max_visible, len(display_items))
        max_label_width = min(30, max(visible_width(item.label) for item in self.items))

        for index in range(start_index, end_index):
            item = display_items[index]
            is_selected = index == self.selected_index
            prefix = self.theme.cursor if is_selected else "  "
            prefix_width = visible_width(prefix)
            label = truncate_to_width(item.label, max_label_width, "")
            label_padded = label + " " * max(0, max_label_width - visible_width(label))
            label_text = self.theme.label(label_padded, is_selected)
            separator = "  "
            used_width = prefix_width + max_label_width + visible_width(separator)
            value_max_width = max(0, width - used_width - 2)
            value = truncate_to_width(item.current_value, value_max_width, "")
            value_text = self.theme.value(value, is_selected)
            lines.append(self._bound_line(prefix + label_text + separator + value_text, width))

        if start_index > 0 or end_index < len(display_items):
            scroll_text = f"  ({self.selected_index + 1}/{len(display_items)})"
            scroll_line = self.theme.hint(truncate_to_width(scroll_text, max(0, width - 2), ""))
            lines.append(self._bound_line(scroll_line, width))

        selected_item = self.get_selected_item()
        if selected_item is not None and selected_item.description:
            lines.append("")
            desc_width = max(1, width - 4)
            for line in wrap_text_with_ansi(selected_item.description, desc_width):
                lines.append(self._bound_line(self.theme.description(f"  {line}"), width))

        self._add_hint_line(lines, width)
        return lines

    def _activate_item(self) -> None:
        item = self.get_selected_item()
        if item is None:
            return

        if item.submenu is not None:
            self._submenu_item_index = self.selected_index

            def done(selected_value: str | None = None) -> None:
                if selected_value is not None:
                    item.current_value = selected_value
                    self.on_change(item.id, selected_value)
                self._close_submenu()

            self._submenu_component = item.submenu(item.current_value, done)
            return

        if item.values:
            try:
                current_index = item.values.index(item.current_value)
            except ValueError:
                current_index = -1
            new_value = item.values[(current_index + 1) % len(item.values)]
            item.current_value = new_value
            self.on_change(item.id, new_value)

    def _close_submenu(self) -> None:
        self._submenu_component = None
        if self._submenu_item_index is not None:
            self.selected_index = self._submenu_item_index
            self._submenu_item_index = None

    def _apply_filter(self, query: str) -> None:
        self.filtered_items = fuzzy_filter_items(self.items, query, lambda item: item.label)
        self.selected_index = 0

    def _get_display_items(self) -> list[SettingItem]:
        return self.filtered_items if self.search_input is not None else self.items

    def _add_hint_line(self, lines: list[str], width: int) -> None:
        lines.append("")
        if self.search_input is not None:
            hint = "  Type to search - Enter/Space to change - Esc to cancel"
        else:
            hint = "  Enter/Space to change - Esc to cancel"
        lines.append(self._bound_line(self.theme.hint(hint), width))

    def _bound_lines(self, lines: list[str], width: int) -> list[str]:
        return [self._bound_line(line, width) for line in lines]

    def _bound_line(self, line: str, width: int) -> str:
        return truncate_to_width(line, width, "")
