from __future__ import annotations

from typing import Generic, TypeVar

T = TypeVar("T")


class UndoStack(Generic[T]):
    def __init__(self, max_size: int = 100) -> None:
        self._max_size = max(1, max_size)
        self._items: list[T] = []

    def push(self, item: T) -> None:
        self._items.append(item)
        if len(self._items) > self._max_size:
            del self._items[0 : len(self._items) - self._max_size]

    def pop(self) -> T | None:
        if not self._items:
            return None
        return self._items.pop()

    def clear(self) -> None:
        self._items.clear()
