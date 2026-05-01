from collections.abc import Callable

from saber_tui.components.cancellable_loader import CancellableLoader
from saber_tui.components.loader import Loader
from saber_tui.utils import visible_width


class DummyTUI:
    def __init__(self) -> None:
        self.render_count = 0

    def request_render(self, force: bool = False) -> None:
        self.render_count += 1


def test_loader_renders_label_and_spinner() -> None:
    tui = DummyTUI()
    loader = Loader(tui, text="Thinking...")

    try:
        line = "\n".join(loader.render(20))

        assert "Thinking..." in line
    finally:
        loader.stop()


def test_loader_tick_requests_render() -> None:
    tui = DummyTUI()
    loader = Loader(tui, text="Thinking...")
    initial_count = tui.render_count

    try:
        loader.tick()

        assert tui.render_count == initial_count + 1
    finally:
        loader.stop()


def test_loader_render_is_width_bounded() -> None:
    tui = DummyTUI()
    loader = Loader(tui, text="Thinking about a long answer")

    try:
        line = loader.render(12)[-1]

        assert visible_width(line) <= 12
    finally:
        loader.stop()


def test_loader_tick_advances_frame() -> None:
    tui = DummyTUI()
    loader = Loader(tui, text="Working", spinner_frames=["a", "b"])

    try:
        before = loader.render(20)[-1]
        loader.tick()
        after = loader.render(20)[-1]

        assert before != after
        assert "b Working" in after
    finally:
        loader.stop()


def test_loader_start_schedules_repeating_timer_and_stop_cancels(monkeypatch) -> None:
    class FakeTimer:
        def __init__(self, interval: float, function: Callable[[], None]) -> None:
            self.interval = interval
            self.function = function
            self.daemon = False
            self.started = False
            self.cancelled = False
            timers.append(self)

        def start(self) -> None:
            self.started = True

        def cancel(self) -> None:
            self.cancelled = True

        def fire(self) -> None:
            self.function()

    timers: list[FakeTimer] = []
    tui = DummyTUI()
    monkeypatch.setattr("threading.Timer", FakeTimer)
    loader = Loader(tui, text="Working", spinner_frames=["a", "b"], interval_ms=25)
    loader.stop()
    timers.clear()

    loader.start()
    assert len(timers) == 1
    assert timers[0].interval == 0.025
    assert timers[0].started

    timers[0].fire()

    assert len(timers) == 2
    assert "b Working" in loader.render(20)[-1]

    loader.stop()
    assert timers[-1].cancelled


def test_loader_set_message_and_indicator_request_render(monkeypatch) -> None:
    class FakeTimer:
        def __init__(self, interval: float, function: Callable[[], None]) -> None:
            self.interval = interval
            self.function = function
            self.daemon = False

        def start(self) -> None:
            return None

        def cancel(self) -> None:
            return None

    tui = DummyTUI()
    monkeypatch.setattr("threading.Timer", FakeTimer)
    loader = Loader(tui, text="Working", spinner_frames=["a"], interval_ms=25)
    initial_count = tui.render_count

    try:
        loader.set_message("Done")
        loader.set_indicator({"frames": ["*"], "intervalMs": 50})

        assert tui.render_count == initial_count + 2
        assert "* Done" in loader.render(20)[-1]
    finally:
        loader.stop()


def test_cancellable_loader_cancel_sets_aborted_and_calls_callback() -> None:
    tui = DummyTUI()
    cancelled: list[bool] = []
    loader = CancellableLoader(tui, text="Working")
    loader.on_cancel = lambda: cancelled.append(True)

    try:
        loader.handle_input("\x1b")

        assert loader.aborted is True
        assert cancelled == [True]
    finally:
        loader.stop()


def test_cancellable_loader_cancel_is_idempotent() -> None:
    tui = DummyTUI()
    cancelled: list[bool] = []
    loader = CancellableLoader(tui, text="Working")
    loader.on_cancel = lambda: cancelled.append(True)

    try:
        loader.handle_input("\x1b")
        loader.handle_input("\x1b")

        assert loader.aborted is True
        assert cancelled == [True]
    finally:
        loader.stop()
