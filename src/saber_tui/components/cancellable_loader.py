from __future__ import annotations

from collections.abc import Callable

from saber_tui.components.loader import Loader
from saber_tui.keybindings import get_keybindings


class CancellableLoader(Loader):
    def __init__(
        self,
        tui: object,
        spinner_style: Callable[[str], str] | None = None,
        text_style: Callable[[str], str] | None = None,
        text: str = "Loading...",
        spinner_frames: list[str] | None = None,
    ) -> None:
        super().__init__(tui, spinner_style, text_style, text, spinner_frames)
        self.aborted = False
        self.on_cancel: Callable[[], None] | None = None

    def handle_input(self, data: str) -> None:
        kb = get_keybindings()
        if kb.matches(data, "tui.select.cancel"):
            if self.aborted:
                return
            self.aborted = True
            if self.on_cancel is not None:
                self.on_cancel()

    def dispose(self) -> None:
        self.stop()
