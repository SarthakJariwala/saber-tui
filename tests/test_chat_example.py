from examples.chat import Message, build_app
from tests.virtual_terminal import VirtualTerminal


def test_chat_page_up_does_not_start_on_separator_before_assistant_reply() -> None:
    terminal = VirtualTerminal(columns=120, rows=16)
    app = build_app(terminal)
    app.tui.start()
    app.messages.clear()

    for index in range(1, 9):
        app.messages.append(Message("user", f"msg {index}"))
        app.messages.append(Message("assistant", f"reply {index} " * 8))

    app.tui.request_render(force=True)
    app.tui.flush_render()

    app.page_up()
    app.tui.flush_render()

    assert terminal.get_viewport()[1].startswith("  You: msg 3")
