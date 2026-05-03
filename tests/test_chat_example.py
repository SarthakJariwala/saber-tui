from examples.chat import _make_global_listener, build_app
from tests.virtual_terminal import VirtualTerminal


def test_chat_leaves_page_keys_for_terminal_scrollback() -> None:
    app = build_app(VirtualTerminal(columns=120, rows=16))
    listener = _make_global_listener(app)

    assert listener("\x1b[5~") is None
    assert listener("\x1b[6~") is None
    assert listener("g") is None
    assert listener("G") is None


def test_chat_appends_messages_to_unbounded_chat_container() -> None:
    terminal = VirtualTerminal(columns=120, rows=16)
    app = build_app(terminal)
    app.tui.start()
    initial_children = len(app.chat_container.children)

    app.submit("hello")
    app._cancel_stream()
    app.tui.flush_render()

    assert len(app.chat_container.children) > initial_children
    viewport = "\n".join(terminal.get_viewport())
    assert "You:" in viewport
    assert "hello" in viewport


def test_chat_submit_preserves_terminal_scrollback_when_editor_clears() -> None:
    terminal = VirtualTerminal(columns=120, rows=8)
    app = build_app(terminal)
    app.tui.start()

    terminal.send_input("h")
    app.tui.flush_render()
    terminal.clear_writes()

    terminal.send_input("\r")
    app._cancel_stream()
    app.tui.flush_render()

    joined = "".join(terminal.writes)
    assert "\x1b[1;1H" not in joined
    assert "\r\n" in joined
