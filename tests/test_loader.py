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

    line = loader.render(20)[0]

    assert "Thinking..." in line


def test_loader_tick_requests_render() -> None:
    tui = DummyTUI()
    loader = Loader(tui, text="Thinking...")

    loader.tick()

    assert tui.render_count == 1


def test_loader_render_is_width_bounded() -> None:
    tui = DummyTUI()
    loader = Loader(tui, text="Thinking about a long answer")

    line = loader.render(12)[0]

    assert visible_width(line) <= 12


def test_loader_tick_advances_frame() -> None:
    tui = DummyTUI()
    loader = Loader(tui, text="Working", spinner_frames=["a", "b"])

    before = loader.render(20)[0]
    loader.tick()
    after = loader.render(20)[0]

    assert before != after
    assert after.startswith("b ")


def test_cancellable_loader_cancel_sets_aborted_and_calls_callback() -> None:
    tui = DummyTUI()
    cancelled: list[bool] = []
    loader = CancellableLoader(tui, text="Working")
    loader.on_cancel = lambda: cancelled.append(True)

    loader.handle_input("\x1b")

    assert loader.aborted is True
    assert cancelled == [True]
