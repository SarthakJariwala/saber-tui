from __future__ import annotations

import threading
from collections.abc import Callable
from typing import TypedDict

from saber_tui.components.text import Text
from saber_tui.utils import truncate_to_width

DEFAULT_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
DEFAULT_INTERVAL_MS = 80


def _identity(text: str) -> str:
    return text


class LoaderIndicatorOptions(TypedDict, total=False):
    frames: list[str]
    intervalMs: int | float


class Loader(Text):
    def __init__(
        self,
        tui: object,
        spinner_style: Callable[[str], str] | None = None,
        text_style: Callable[[str], str] | None = None,
        text: str = "Loading...",
        spinner_frames: list[str] | None = None,
        indicator: LoaderIndicatorOptions | None = None,
        interval_ms: int | None = None,
    ) -> None:
        super().__init__("", 1, 0)
        self.tui = tui
        self.spinner_style = spinner_style or _identity
        self.text_style = text_style or _identity
        self.message = text
        self.spinner_frames = list(DEFAULT_FRAMES)
        self.interval_ms = DEFAULT_INTERVAL_MS
        self.current_frame = 0
        self._timer: threading.Timer | None = None
        self._timer_active = False
        self._render_indicator_verbatim = False

        resolved_indicator = indicator
        if resolved_indicator is None and (spinner_frames is not None or interval_ms is not None):
            resolved_indicator: LoaderIndicatorOptions = {}
            if spinner_frames is not None:
                resolved_indicator["frames"] = spinner_frames
            if interval_ms is not None:
                resolved_indicator["intervalMs"] = interval_ms
        self.set_indicator(resolved_indicator)

    def render(self, width: int) -> list[str]:
        rendered = super().render(width)
        if len(rendered) == 1:
            rendered = [truncate_to_width(rendered[0], width, "")]
        return ["", *rendered]

    def start(self) -> None:
        self._update_display()
        self._restart_animation()

    def _restart_animation(self) -> None:
        self.stop()
        if len(self.spinner_frames) <= 1:
            return
        self._timer_active = True
        self._schedule_timer()

    def _schedule_timer(self) -> None:
        timer = threading.Timer(self.interval_ms / 1000, self._timer_tick)
        timer.daemon = True
        self._timer = timer
        timer.start()

    def _timer_tick(self) -> None:
        if not self._timer_active:
            return
        self.tick()
        if self._timer_active:
            self._schedule_timer()

    def tick(self) -> None:
        if self.spinner_frames:
            self.current_frame = (self.current_frame + 1) % len(self.spinner_frames)
        self._update_display()

    def set_message(self, message: str) -> None:
        self.message = message
        self._update_display()

    def set_indicator(self, indicator: LoaderIndicatorOptions | None = None) -> None:
        self._render_indicator_verbatim = indicator is not None
        frames = indicator.get("frames") if indicator is not None else None
        interval = indicator.get("intervalMs") if indicator is not None else None

        self.spinner_frames = list(frames) if frames is not None else list(DEFAULT_FRAMES)
        self.interval_ms = int(interval) if isinstance(interval, int | float) and interval > 0 else DEFAULT_INTERVAL_MS
        self.current_frame = 0
        self.start()

    def _update_display(self) -> None:
        frame = self.spinner_frames[self.current_frame] if self.spinner_frames else ""
        rendered_frame = frame if self._render_indicator_verbatim else self.spinner_style(frame)
        indicator = f"{rendered_frame} " if frame else ""
        self.set_text(f"{indicator}{self.text_style(self.message)}")
        request_render = getattr(self.tui, "request_render", None)
        if request_render is not None:
            request_render()

    def stop(self) -> None:
        self._timer_active = False
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
