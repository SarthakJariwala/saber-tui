from saber_tui.undo_stack import UndoStack


def test_pop_returns_latest_snapshot() -> None:
    stack: UndoStack[dict[str, int]] = UndoStack()
    stack.push({"cursor": 1})
    stack.push({"cursor": 2})

    assert stack.pop() == {"cursor": 2}
    assert stack.pop() == {"cursor": 1}
    assert stack.pop() is None


def test_max_size_discards_oldest_snapshot() -> None:
    stack: UndoStack[int] = UndoStack(max_size=2)
    stack.push(1)
    stack.push(2)
    stack.push(3)

    assert stack.pop() == 3
    assert stack.pop() == 2
    assert stack.pop() is None


def test_clear_removes_all_snapshots() -> None:
    stack: UndoStack[int] = UndoStack()
    stack.push(1)
    stack.push(2)

    stack.clear()

    assert stack.pop() is None
