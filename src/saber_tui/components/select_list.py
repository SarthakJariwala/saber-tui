from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from saber_tui.keybindings import get_keybindings
from saber_tui.utils import truncate_to_width, visible_width

DEFAULT_PRIMARY_COLUMN_WIDTH = 32
PRIMARY_COLUMN_GAP = 2
MIN_DESCRIPTION_WIDTH = 10


def _identity(text: str) -> str:
    return text


def _normalize_to_single_line(text: str) -> str:
    return " ".join(text.replace("\r", "\n").split())


def _clamp(value: int, min_value: int, max_value: int) -> int:
    return max(min_value, min(value, max_value))


@dataclass(frozen=True)
class SelectItem:
    value: str
    label: str
    description: str | None = None


@dataclass(frozen=True)
class SelectListTheme:
    selected_prefix: Callable[[str], str] = _identity
    selected_text: Callable[[str], str] = _identity
    description: Callable[[str], str] = _identity
    scroll_info: Callable[[str], str] = _identity
    no_match: Callable[[str], str] = _identity


@dataclass(frozen=True)
class SelectListTruncatePrimaryContext:
    text: str
    max_width: int
    column_width: int
    item: SelectItem
    is_selected: bool


@dataclass(frozen=True)
class SelectListLayoutOptions:
    min_primary_column_width: int | None = None
    max_primary_column_width: int | None = None
    truncate_primary: Callable[[SelectListTruncatePrimaryContext], str] | None = None


class SelectList:
    def __init__(
        self,
        items: list[SelectItem],
        max_visible: int = 5,
        theme: SelectListTheme | None = None,
        layout: SelectListLayoutOptions | None = None,
    ) -> None:
        self.items = items
        self.filtered_items = items
        self.selected_index = 0
        self.max_visible = max_visible
        self.theme = theme or SelectListTheme()
        self.layout = layout or SelectListLayoutOptions()
        self.on_select: Callable[[SelectItem], None] | None = None
        self.on_cancel: Callable[[], None] | None = None
        self.on_selection_change: Callable[[SelectItem], None] | None = None

    def set_filter(self, filter_text: str) -> None:
        lower_filter = filter_text.lower()
        self.filtered_items = [item for item in self.items if item.value.lower().startswith(lower_filter)]
        self.selected_index = 0

    def set_selected_index(self, index: int) -> None:
        if not self.filtered_items:
            self.selected_index = 0
            return
        self.selected_index = _clamp(index, 0, len(self.filtered_items) - 1)

    def invalidate(self) -> None:
        pass

    def render(self, width: int) -> list[str]:
        if width <= 0:
            return [""]

        if not self.filtered_items:
            return [self.theme.no_match(truncate_to_width("  No matching commands", width, ""))]

        lines: list[str] = []
        primary_column_width = self._get_primary_column_width()
        max_visible = max(1, self.max_visible)
        start_index = max(
            0,
            min(self.selected_index - max_visible // 2, len(self.filtered_items) - max_visible),
        )
        end_index = min(start_index + max_visible, len(self.filtered_items))

        for index in range(start_index, end_index):
            item = self.filtered_items[index]
            description = _normalize_to_single_line(item.description) if item.description else None
            lines.append(
                self._render_item(item, index == self.selected_index, width, description, primary_column_width)
            )

        if start_index > 0 or end_index < len(self.filtered_items):
            scroll_text = f"  ({self.selected_index + 1}/{len(self.filtered_items)})"
            lines.append(self.theme.scroll_info(truncate_to_width(scroll_text, max(0, width - 2), "")))

        return [truncate_to_width(line, width, "") for line in lines]

    def handle_input(self, data: str) -> None:
        kb = get_keybindings()
        if kb.matches(data, "tui.select.up"):
            if self.filtered_items:
                self.selected_index = (
                    len(self.filtered_items) - 1 if self.selected_index == 0 else self.selected_index - 1
                )
                self._notify_selection_change()
        elif kb.matches(data, "tui.select.down"):
            if self.filtered_items:
                self.selected_index = (
                    0 if self.selected_index == len(self.filtered_items) - 1 else self.selected_index + 1
                )
                self._notify_selection_change()
        elif kb.matches(data, "tui.select.confirm"):
            selected_item = self.get_selected_item()
            if selected_item is not None and self.on_select is not None:
                self.on_select(selected_item)
        elif kb.matches(data, "tui.select.cancel") and self.on_cancel is not None:
            self.on_cancel()

    def get_selected_item(self) -> SelectItem | None:
        if 0 <= self.selected_index < len(self.filtered_items):
            return self.filtered_items[self.selected_index]
        return None

    def _render_item(
        self,
        item: SelectItem,
        is_selected: bool,
        width: int,
        description: str | None,
        primary_column_width: int,
    ) -> str:
        prefix = self.theme.selected_prefix("-> ") if is_selected else "  "
        prefix_width = visible_width(prefix)

        if description and width > 40:
            effective_primary_width = max(1, min(primary_column_width, width - prefix_width - 4))
            max_primary_width = max(1, effective_primary_width - PRIMARY_COLUMN_GAP)
            truncated_value = self._truncate_primary(item, is_selected, max_primary_width, effective_primary_width)
            truncated_value_width = visible_width(truncated_value)
            spacing = " " * max(1, effective_primary_width - truncated_value_width)
            description_start = prefix_width + truncated_value_width + len(spacing)
            remaining_width = width - description_start - 2

            if remaining_width > MIN_DESCRIPTION_WIDTH:
                truncated_desc = truncate_to_width(description, remaining_width, "")
                if is_selected:
                    return self.theme.selected_text(f"{prefix}{truncated_value}{spacing}{truncated_desc}")
                return f"{prefix}{truncated_value}{self.theme.description(spacing + truncated_desc)}"

        max_width = max(0, width - prefix_width - 2)
        truncated_value = self._truncate_primary(item, is_selected, max_width, max_width)
        text = f"{prefix}{truncated_value}"
        return self.theme.selected_text(text) if is_selected else text

    def _get_primary_column_width(self) -> int:
        min_width, max_width = self._get_primary_column_bounds()
        widest = 0
        for item in self.filtered_items:
            widest = max(widest, visible_width(self._get_display_value(item)) + PRIMARY_COLUMN_GAP)
        return _clamp(widest, min_width, max_width)

    def _get_primary_column_bounds(self) -> tuple[int, int]:
        raw_min = (
            self.layout.min_primary_column_width
            if self.layout.min_primary_column_width is not None
            else self.layout.max_primary_column_width
            if self.layout.max_primary_column_width is not None
            else DEFAULT_PRIMARY_COLUMN_WIDTH
        )
        raw_max = (
            self.layout.max_primary_column_width
            if self.layout.max_primary_column_width is not None
            else self.layout.min_primary_column_width
            if self.layout.min_primary_column_width is not None
            else DEFAULT_PRIMARY_COLUMN_WIDTH
        )
        return max(1, min(raw_min, raw_max)), max(1, max(raw_min, raw_max))

    def _truncate_primary(self, item: SelectItem, is_selected: bool, max_width: int, column_width: int) -> str:
        display_value = self._get_display_value(item)
        if self.layout.truncate_primary is not None:
            truncated_value = self.layout.truncate_primary(
                SelectListTruncatePrimaryContext(display_value, max_width, column_width, item, is_selected)
            )
        else:
            truncated_value = truncate_to_width(display_value, max_width, "")
        return truncate_to_width(truncated_value, max_width, "")

    def _get_display_value(self, item: SelectItem) -> str:
        return item.label or item.value

    def _notify_selection_change(self) -> None:
        selected_item = self.get_selected_item()
        if selected_item is not None and self.on_selection_change is not None:
            self.on_selection_change(selected_item)
