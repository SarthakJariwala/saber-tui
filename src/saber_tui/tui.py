from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, Protocol, TypedDict, runtime_checkable

from saber_tui.keys import is_key_release, matches_key
from saber_tui.terminal import Terminal
from saber_tui.utils import (
    extract_segments,
    normalize_terminal_output,
    slice_by_column,
    slice_with_width,
    visible_width,
)

CURSOR_MARKER = "\x1b_pi:c\x07"
SEGMENT_RESET = "\x1b[0m\x1b]8;;\x07"
_PERCENT_RE = re.compile(r"^(\d+(?:\.\d+)?)%$")


@runtime_checkable
class Component(Protocol):
    def render(self, width: int) -> list[str]: ...


@runtime_checkable
class Focusable(Protocol):
    focused: bool


OverlayAnchor = Literal[
    "center",
    "top-left",
    "top-right",
    "bottom-left",
    "bottom-right",
    "top-center",
    "bottom-center",
    "left-center",
    "right-center",
]
SizeValue = int | float | str


class OverlayMargin(TypedDict, total=False):
    top: int | float
    right: int | float
    bottom: int | float
    left: int | float


class OverlayOptions(TypedDict, total=False):
    width: SizeValue
    minWidth: int
    maxHeight: SizeValue
    anchor: OverlayAnchor
    offsetX: int
    offsetY: int
    row: SizeValue
    col: SizeValue
    margin: OverlayMargin | int | float
    visible: Callable[[int, int], bool]
    nonCapturing: bool


class OverlayHandle(Protocol):
    def hide(self) -> None: ...

    def set_hidden(self, hidden: bool) -> None: ...

    def is_hidden(self) -> bool: ...

    def focus(self) -> None: ...

    def unfocus(self) -> None: ...

    def is_focused(self) -> bool: ...


InputListenerResult = dict[str, Any] | None
InputListener = Callable[[str], InputListenerResult]


class Container:
    def __init__(self) -> None:
        self.children: list[Component] = []

    def add_child(self, component: Component) -> None:
        self.children.append(component)

    def remove_child(self, component: Component) -> None:
        if component in self.children:
            self.children.remove(component)

    def clear(self) -> None:
        self.children.clear()

    def invalidate(self) -> None:
        for child in self.children:
            invalidate = getattr(child, "invalidate", None)
            if invalidate is not None:
                invalidate()

    def render(self, width: int) -> list[str]:
        lines: list[str] = []
        for child in self.children:
            lines.extend(child.render(width))
        return lines


@dataclass
class _OverlayEntry:
    component: Component
    options: OverlayOptions
    pre_focus: Component | None
    hidden: bool
    focus_order: int


@dataclass(frozen=True)
class _OverlayLayout:
    width: int
    row: int
    col: int
    max_height: int | None


class _OverlayHandle:
    def __init__(self, tui: TUI, entry: _OverlayEntry) -> None:
        self._tui = tui
        self._entry = entry

    def hide(self) -> None:
        self._tui._hide_overlay_entry(self._entry)

    def set_hidden(self, hidden: bool) -> None:
        self._tui._set_overlay_hidden(self._entry, hidden)

    def is_hidden(self) -> bool:
        return self._entry.hidden

    def focus(self) -> None:
        self._tui._focus_overlay_entry(self._entry)

    def unfocus(self) -> None:
        self._tui._unfocus_overlay_entry(self._entry)

    def is_focused(self) -> bool:
        return self._tui._overlay_contains_focus(self._entry)


class TUI(Container):
    def __init__(self, terminal: Terminal, show_hardware_cursor: bool = False) -> None:
        super().__init__()
        self.terminal = terminal
        self.focused_component: Component | None = None
        self.previous_lines: list[str] = []
        self.previous_width = 0
        self.previous_height = 0
        self.input_listeners: list[InputListener] = []
        self.overlay_stack: list[_OverlayEntry] = []
        self.focus_order_counter = 0
        self.show_hardware_cursor = show_hardware_cursor
        self.stopped = True
        self._full_redraws = 0
        self._force_full_redraw = False
        self._hardware_cursor_row = 0
        self.on_debug: Callable[[], None] | None = None

    @property
    def full_redraws(self) -> int:
        return self._full_redraws

    def set_focus(self, component: Component | None) -> None:
        old = self.focused_component
        if isinstance(old, Focusable):
            old.focused = False
        self.focused_component = component
        if isinstance(component, Focusable):
            component.focused = True

    def add_input_listener(self, listener: InputListener) -> Callable[[], None]:
        self.input_listeners.append(listener)

        def remove() -> None:
            self.remove_input_listener(listener)

        return remove

    def remove_input_listener(self, listener: InputListener) -> None:
        if listener in self.input_listeners:
            self.input_listeners.remove(listener)

    def show_overlay(self, component: Component, options: OverlayOptions | None = None) -> OverlayHandle:
        overlay_options: OverlayOptions = options if options is not None else {}
        entry = _OverlayEntry(
            component=component,
            options=overlay_options,
            pre_focus=self.focused_component,
            hidden=False,
            focus_order=self._next_focus_order(),
        )
        self.overlay_stack.append(entry)
        if not entry.options.get("nonCapturing") and self._is_overlay_visible(entry):
            self.set_focus(component)
        self.terminal.hide_cursor()
        self.request_render()
        return _OverlayHandle(self, entry)

    def hide_overlay(self) -> None:
        if self.overlay_stack:
            self._hide_overlay_entry(self.overlay_stack[-1])

    def has_overlay(self) -> bool:
        return any(self._is_overlay_visible(entry) for entry in self.overlay_stack)

    def invalidate(self) -> None:
        super().invalidate()
        for entry in self.overlay_stack:
            invalidate = getattr(entry.component, "invalidate", None)
            if invalidate is not None:
                invalidate()

    def start(self) -> None:
        self.stopped = False
        self.terminal.start(self._handle_input, self._handle_resize)
        self.terminal.hide_cursor()
        self.request_render()

    def stop(self) -> None:
        if self.stopped:
            return
        self.stopped = True
        self.terminal.show_cursor()
        self.terminal.stop()

    def request_render(self, force: bool = False) -> None:
        if force:
            self.previous_lines = []
            self.previous_width = 0
            self.previous_height = 0
            self._force_full_redraw = True
            self._hardware_cursor_row = 0
        if self.stopped:
            return
        self._do_render()

    def _next_focus_order(self) -> int:
        self.focus_order_counter += 1
        return self.focus_order_counter

    def _handle_resize(self) -> None:
        self.invalidate()
        self.request_render(force=True)

    def _handle_input(self, data: str) -> None:
        for listener in list(self.input_listeners):
            result = listener(data)
            if result and result.get("consume"):
                return
            if result and "data" in result:
                data = str(result["data"])
        if not data:
            return

        if matches_key(data, "shift+ctrl+d") and self.on_debug is not None:
            self.on_debug()
            return

        self._reconcile_overlay_focus()

        focused = self.focused_component
        if focused is None:
            return
        if is_key_release(data) and not bool(getattr(focused, "wants_key_release", False)):
            return
        handle_input = getattr(focused, "handle_input", None)
        if handle_input is not None:
            handle_input(data)
            self.request_render()

    def _hide_overlay_entry(self, entry: _OverlayEntry) -> None:
        if entry not in self.overlay_stack:
            return
        self.overlay_stack.remove(entry)
        for overlay in self.overlay_stack:
            if self._component_contains(entry.component, overlay.pre_focus):
                overlay.pre_focus = entry.pre_focus
        if self._overlay_contains_focus(entry):
            self.set_focus(self._restore_focus_target(entry.pre_focus))
        self.request_render()

    def _set_overlay_hidden(self, entry: _OverlayEntry, hidden: bool) -> None:
        if entry not in self.overlay_stack or entry.hidden == hidden:
            return
        entry.hidden = hidden
        if hidden:
            if self._overlay_contains_focus(entry):
                self.set_focus(self._restore_focus_target(entry.pre_focus))
        elif not entry.options.get("nonCapturing") and self._is_overlay_visible(entry):
            entry.focus_order = self._next_focus_order()
            self.set_focus(entry.component)
        self.request_render()

    def _focus_overlay_entry(self, entry: _OverlayEntry) -> None:
        if entry not in self.overlay_stack or not self._is_overlay_visible(entry):
            return
        entry.focus_order = self._next_focus_order()
        self.set_focus(entry.component)
        self.request_render()

    def _unfocus_overlay_entry(self, entry: _OverlayEntry) -> None:
        if not self._overlay_contains_focus(entry):
            return
        top_visible = self._topmost_visible_overlay(except_entry=entry)
        previous_focus = self._valid_previous_focus(entry.pre_focus)
        self.set_focus(previous_focus if previous_focus is not None else top_visible.component if top_visible else None)
        self.request_render()

    def _overlay_contains_focus(self, entry: _OverlayEntry) -> bool:
        return self._component_contains(entry.component, self.focused_component)

    def _component_contains(self, root: Component, component: Component | None) -> bool:
        if component is root:
            return True
        return isinstance(root, Container) and self._contains_child(root, component)

    def _is_overlay_visible(self, entry: _OverlayEntry) -> bool:
        if entry.hidden:
            return False
        visible = entry.options.get("visible")
        if visible is not None:
            return bool(visible(self.terminal.columns, self.terminal.rows))
        return True

    def _topmost_visible_overlay(self, except_entry: _OverlayEntry | None = None) -> _OverlayEntry | None:
        visible_entries = [
            entry
            for entry in self.overlay_stack
            if entry is not except_entry and not entry.options.get("nonCapturing") and self._is_overlay_visible(entry)
        ]
        return max(visible_entries, key=lambda entry: entry.focus_order, default=None)

    def _reconcile_overlay_focus(self) -> None:
        focused_overlay = next(
            (entry for entry in self.overlay_stack if self._overlay_contains_focus(entry)),
            None,
        )
        if focused_overlay is not None and not self._is_overlay_visible(focused_overlay):
            self.set_focus(self._restore_focus_target(focused_overlay.pre_focus))

    def _restore_focus_target(self, previous_focus: Component | None) -> Component | None:
        valid_previous = self._valid_previous_focus(previous_focus)
        if valid_previous is not None:
            return valid_previous
        top_visible = self._topmost_visible_overlay()
        return top_visible.component if top_visible is not None else None

    def _valid_previous_focus(self, component: Component | None) -> Component | None:
        if self._contains_child(self, component):
            return component
        for entry in self.overlay_stack:
            if entry.component is component and self._is_overlay_visible(entry):
                return component
            if (
                isinstance(entry.component, Container)
                and self._is_overlay_visible(entry)
                and self._contains_child(entry.component, component)
            ):
                return component
        return None

    def _contains_child(self, container: Container, component: Component | None) -> bool:
        if component is None:
            return False
        for child in container.children:
            if child is component:
                return True
            if isinstance(child, Container) and self._contains_child(child, component):
                return True
        return False

    def _resolve_overlay_layout(
        self,
        options: OverlayOptions,
        overlay_height: int,
        term_width: int,
        term_height: int,
    ) -> _OverlayLayout:
        margin_top, margin_right, margin_bottom, margin_left = self._resolve_overlay_margin(options.get("margin"))
        avail_width = max(1, term_width - margin_left - margin_right)
        avail_height = max(1, term_height - margin_top - margin_bottom)

        width = self._parse_size_value(options.get("width"), term_width)
        if width is None:
            width = min(80, avail_width)
        min_width = options.get("minWidth")
        if min_width is not None:
            width = max(width, int(min_width))
        width = max(1, min(width, avail_width))

        max_height = self._parse_size_value(options.get("maxHeight"), term_height)
        if max_height is not None:
            max_height = max(1, min(max_height, avail_height))
        effective_height = min(overlay_height, max_height) if max_height is not None else overlay_height

        row = self._resolve_overlay_row(options, effective_height, avail_height, margin_top)
        col = self._resolve_overlay_col(options, width, avail_width, margin_left)
        row += int(options.get("offsetY", 0))
        col += int(options.get("offsetX", 0))

        row = max(margin_top, min(row, term_height - margin_bottom - effective_height))
        col = max(margin_left, min(col, term_width - margin_right - width))
        return _OverlayLayout(width=width, row=row, col=col, max_height=max_height)

    def _resolve_overlay_margin(self, margin: OverlayMargin | int | float | None) -> tuple[int, int, int, int]:
        if isinstance(margin, int | float):
            value = max(0, int(margin))
            return value, value, value, value
        if isinstance(margin, dict):
            return (
                max(0, int(margin.get("top", 0))),
                max(0, int(margin.get("right", 0))),
                max(0, int(margin.get("bottom", 0))),
                max(0, int(margin.get("left", 0))),
            )
        return 0, 0, 0, 0

    def _parse_size_value(self, value: SizeValue | None, reference_size: int) -> int | None:
        if value is None:
            return None
        if isinstance(value, int | float):
            return int(value)
        match = _PERCENT_RE.fullmatch(value)
        if match is None:
            return None
        return math.floor(reference_size * float(match.group(1)) / 100)

    def _resolve_overlay_row(
        self,
        options: OverlayOptions,
        height: int,
        avail_height: int,
        margin_top: int,
    ) -> int:
        row = options.get("row")
        if row is not None:
            if isinstance(row, str):
                match = _PERCENT_RE.fullmatch(row)
                if match is not None:
                    max_row = max(0, avail_height - height)
                    return margin_top + math.floor(max_row * float(match.group(1)) / 100)
                return self._resolve_anchor_row("center", height, avail_height, margin_top)
            return int(row)
        return self._resolve_anchor_row(options.get("anchor", "center"), height, avail_height, margin_top)

    def _resolve_overlay_col(
        self,
        options: OverlayOptions,
        width: int,
        avail_width: int,
        margin_left: int,
    ) -> int:
        col = options.get("col")
        if col is not None:
            if isinstance(col, str):
                match = _PERCENT_RE.fullmatch(col)
                if match is not None:
                    max_col = max(0, avail_width - width)
                    return margin_left + math.floor(max_col * float(match.group(1)) / 100)
                return self._resolve_anchor_col("center", width, avail_width, margin_left)
            return int(col)
        return self._resolve_anchor_col(options.get("anchor", "center"), width, avail_width, margin_left)

    def _resolve_anchor_row(
        self,
        anchor: OverlayAnchor,
        height: int,
        avail_height: int,
        margin_top: int,
    ) -> int:
        if anchor in {"top-left", "top-center", "top-right"}:
            return margin_top
        if anchor in {"bottom-left", "bottom-center", "bottom-right"}:
            return margin_top + avail_height - height
        return margin_top + math.floor((avail_height - height) / 2)

    def _resolve_anchor_col(
        self,
        anchor: OverlayAnchor,
        width: int,
        avail_width: int,
        margin_left: int,
    ) -> int:
        if anchor in {"top-left", "left-center", "bottom-left"}:
            return margin_left
        if anchor in {"top-right", "right-center", "bottom-right"}:
            return margin_left + avail_width - width
        return margin_left + math.floor((avail_width - width) / 2)

    def _composite_overlays(self, lines: list[str], term_width: int, term_height: int) -> list[str]:
        if not self.overlay_stack:
            return lines
        result = list(lines)
        rendered: list[tuple[list[str], int, int, int]] = []
        min_lines_needed = len(result)
        visible_entries = [entry for entry in self.overlay_stack if self._is_overlay_visible(entry)]
        visible_entries.sort(key=lambda entry: entry.focus_order)

        for entry in visible_entries:
            initial_layout = self._resolve_overlay_layout(entry.options, 0, term_width, term_height)
            overlay_lines = entry.component.render(initial_layout.width)
            if initial_layout.max_height is not None and len(overlay_lines) > initial_layout.max_height:
                overlay_lines = overlay_lines[: initial_layout.max_height]
            layout = self._resolve_overlay_layout(entry.options, len(overlay_lines), term_width, term_height)
            rendered.append((overlay_lines, layout.row, layout.col, layout.width))
            min_lines_needed = max(min_lines_needed, layout.row + len(overlay_lines))

        working_height = max(len(result), term_height, min_lines_needed)
        while len(result) < working_height:
            result.append("")
        viewport_start = max(0, working_height - term_height)

        for overlay_lines, row, col, width in rendered:
            for line_index, overlay_line in enumerate(overlay_lines):
                target = viewport_start + row + line_index
                if 0 <= target < len(result):
                    if visible_width(overlay_line) > width:
                        overlay_line = slice_by_column(overlay_line, 0, width, True)
                    result[target] = self._composite_line_at(result[target], overlay_line, col, width, term_width)
        return result

    def _composite_line_at(
        self,
        base_line: str,
        overlay_line: str,
        start_col: int,
        overlay_width: int,
        total_width: int,
    ) -> str:
        after_start = start_col + overlay_width
        base = extract_segments(base_line, start_col, after_start, total_width - after_start, True)
        overlay = slice_with_width(overlay_line, 0, overlay_width, True)
        before_pad = max(0, start_col - base.before_width)
        overlay_pad = max(0, overlay_width - overlay.width)
        actual_before_width = max(start_col, base.before_width)
        actual_overlay_width = max(overlay_width, overlay.width)
        after_target = max(0, total_width - actual_before_width - actual_overlay_width)
        after_pad = max(0, after_target - base.after_width)
        result = (
            base.before
            + (" " * before_pad)
            + SEGMENT_RESET
            + overlay.text
            + (" " * overlay_pad)
            + SEGMENT_RESET
            + base.after
            + (" " * after_pad)
        )
        if visible_width(result) <= total_width:
            return result
        return slice_by_column(result, 0, total_width, True)

    def _extract_cursor_position(self, lines: list[str], height: int) -> tuple[int, int] | None:
        viewport_top = max(0, len(lines) - height)
        cursor_pos: tuple[int, int] | None = None
        for row in range(len(lines) - 1, viewport_top - 1, -1):
            marker_index = lines[row].find(CURSOR_MARKER)
            if marker_index == -1:
                continue
            col = visible_width(lines[row][:marker_index])
            cursor_pos = row, col
            break

        for row, line in enumerate(lines):
            if CURSOR_MARKER in line:
                lines[row] = line.replace(CURSOR_MARKER, "")
        return cursor_pos

    def _prepare_lines(self, width: int, height: int) -> tuple[list[str], tuple[int, int] | None]:
        self._reconcile_overlay_focus()
        lines = self.render(width)
        lines = self._composite_overlays(lines, width, height)
        cursor_pos = self._extract_cursor_position(lines, height)
        normalized: list[str] = []
        for line in lines:
            line = normalize_terminal_output(line)
            line_width = visible_width(line)
            if line_width > width:
                raise ValueError(f"Rendered line exceeds terminal width: {line_width} > {width}")
            normalized.append(line + SEGMENT_RESET)
        return normalized, cursor_pos

    def _do_render(self) -> None:
        width = self.terminal.columns
        height = self.terminal.rows
        lines, cursor_pos = self._prepare_lines(width, height)
        width_changed = self.previous_width not in {0, width}
        height_changed = self.previous_height not in {0, height}
        first_render = not self.previous_lines
        full_redraw = self._force_full_redraw or not self.previous_lines or width_changed or height_changed
        if full_redraw:
            clear = (not first_render and (width_changed or height_changed)) or self._force_full_redraw
            self._write_full_render(lines, clear=clear)
        else:
            self._write_changed_lines(lines, height)
        self._position_hardware_cursor(cursor_pos, len(lines), height)
        self.previous_lines = lines
        self.previous_width = width
        self.previous_height = height
        self._force_full_redraw = False

    def _write_full_render(self, lines: list[str], clear: bool) -> None:
        self._full_redraws += 1
        buffer = "\x1b[?2026h"
        if clear:
            buffer += "\x1b[2J\x1b[H"
        for index, line in enumerate(lines):
            if index > 0:
                buffer += "\r\n"
            buffer += line
        buffer += "\x1b[?2026l"
        self.terminal.write(buffer)
        self._hardware_cursor_row = max(0, len(lines) - 1)

    def _write_changed_lines(self, lines: list[str], height: int) -> None:
        previous_viewport_top = max(0, len(self.previous_lines) - height)
        viewport_top = max(0, len(lines) - height)
        if previous_viewport_top != viewport_top:
            self._write_full_render(lines, clear=True)
            return

        max_lines = max(len(lines), len(self.previous_lines))
        changed = [
            index
            for index in range(max_lines)
            if (lines[index] if index < len(lines) else "")
            != (self.previous_lines[index] if index < len(self.previous_lines) else "")
        ]
        if not changed:
            return

        viewport_bottom = viewport_top + height
        visible_changed = [index for index in changed if viewport_top <= index < viewport_bottom]
        if not visible_changed:
            return

        buffer = "\x1b[?2026h"
        for index in visible_changed:
            screen_row = index - viewport_top + 1
            buffer += f"\x1b[{screen_row};1H\x1b[K"
            if index < len(lines):
                buffer += lines[index]
        buffer += "\x1b[?2026l"
        self.terminal.write(buffer)
        self._hardware_cursor_row = visible_changed[-1]

    def _position_hardware_cursor(
        self,
        cursor_pos: tuple[int, int] | None,
        total_lines: int,
        height: int,
    ) -> None:
        if not self.show_hardware_cursor or cursor_pos is None:
            self.terminal.hide_cursor()
            return
        row, col = cursor_pos
        viewport_top = max(0, total_lines - height)
        screen_row = max(0, row - viewport_top)
        self.terminal.write(f"\x1b[{screen_row + 1};{col + 1}H")
        self.terminal.show_cursor()
        self._hardware_cursor_row = row
