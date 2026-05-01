from __future__ import annotations


class Spacer:
    def __init__(self, height: int = 1) -> None:
        self._height = height

    def set_lines(self, lines: int) -> None:
        self._height = lines

    def invalidate(self) -> None:
        pass

    def render(self, width: int) -> list[str]:
        return [" " * max(0, width) for _ in range(self._height)]
