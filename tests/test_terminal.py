from tests.virtual_terminal import VirtualTerminal


def test_virtual_terminal_records_writes_and_viewport() -> None:
    terminal = VirtualTerminal(columns=10, rows=3)
    terminal.write("hello")

    assert terminal.get_viewport()[0] == "hello"


def test_virtual_terminal_resize_invokes_handler() -> None:
    terminal = VirtualTerminal(columns=10, rows=3)
    resized = False

    def on_resize() -> None:
        nonlocal resized
        resized = True

    terminal.start(lambda data: None, on_resize)
    terminal.resize(20, 4)

    assert resized
    assert terminal.columns == 20
    assert terminal.rows == 4
