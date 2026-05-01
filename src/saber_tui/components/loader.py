from __future__ import annotations

from collections.abc import Callable

from saber_tui.utils import truncate_to_width

DEFAULT_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


def _identity(text: str) -> str:
    return text


class Loader:
    def __init__(
        self,
        tui: object,
        spinner_style: Callable[[str], str] | None = None,
        text_style: Callable[[str], str] | None = None,
        text: str = "Loading...",
        spinner_frames: list[str] | None = None,
    ) -> None:
        self.tui = tui
        self.spinner_style = spinner_style or _identity
        self.text_style = text_style or _identity
        self.text = text
        self.spinner_frames = list(DEFAULT_FRAMES if spinner_frames is None else spinner_frames)
        self.current_frame = 0

    def render(self, width: int) -> list[str]:
        frame = self.spinner_frames[self.current_frame] if self.spinner_frames else ""
        indicator = f"{self.spinner_style(frame)} " if frame else ""
        return [truncate_to_width(f"{indicator}{self.text_style(self.text)}", width, "")]

    def tick(self) -> None:
        if self.spinner_frames:
            self.current_frame = (self.current_frame + 1) % len(self.spinner_frames)
        request_render = getattr(self.tui, "request_render", None)
        if request_render is not None:
            request_render()

    def set_message(self, message: str) -> None:
        self.text = message

    def stop(self) -> None:
        pass
