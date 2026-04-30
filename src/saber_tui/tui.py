from typing import Protocol

CURSOR_MARKER = "\x1b_pi:c\x07"


class Component(Protocol):
    pass


class Focusable(Protocol):
    focused: bool


class Container:
    pass


class TUI(Container):
    pass


class OverlayOptions(dict):
    pass


class OverlayHandle(Protocol):
    pass
