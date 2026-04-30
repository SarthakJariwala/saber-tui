from saber_tui.kill_ring import KillRing


def test_push_and_peek_latest_text() -> None:
    ring = KillRing()
    ring.push("first")
    ring.push("second")

    assert ring.peek() == "second"
    assert len(ring) == 2


def test_rotate_cycles_entries() -> None:
    ring = KillRing()
    ring.push("first")
    ring.push("second")
    ring.push("third")

    ring.rotate()
    assert ring.peek() == "second"
    ring.rotate()
    assert ring.peek() == "first"
    ring.rotate()
    assert ring.peek() == "third"


def test_accumulate_appends_or_prepends_to_latest_entry() -> None:
    ring = KillRing()
    ring.push("world")
    ring.push("hello ", prepend=True, accumulate=True)
    assert ring.peek() == "hello world"

    ring.push("!", prepend=False, accumulate=True)
    assert ring.peek() == "hello world!"
