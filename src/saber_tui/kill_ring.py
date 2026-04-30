from __future__ import annotations


class KillRing:
    def __init__(self, max_size: int = 60) -> None:
        self._max_size = max(1, max_size)
        self._entries: list[str] = []

    def __len__(self) -> int:
        return len(self._entries)

    def push(self, text: str, *, prepend: bool = False, accumulate: bool = False) -> None:
        if text == "":
            return
        if accumulate and self._entries:
            current = self._entries[0]
            self._entries[0] = text + current if prepend else current + text
            return
        self._entries.insert(0, text)
        del self._entries[self._max_size :]

    def peek(self) -> str | None:
        return self._entries[0] if self._entries else None

    def rotate(self) -> None:
        if len(self._entries) <= 1:
            return
        first = self._entries.pop(0)
        self._entries.append(first)
