import shlex
import shutil
import subprocess
import textwrap
import time
import uuid
from pathlib import Path

import pytest


def _run(command: list[str], timeout: float = 5) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=True, capture_output=True, text=True, timeout=timeout)


def _capture(session: str) -> str:
    return _run(["tmux", "capture-pane", "-pt", session]).stdout


def _wait_for_pane_text(session: str, text: str, timeout: float = 5) -> str:
    deadline = time.monotonic() + timeout
    pane = ""
    while time.monotonic() < deadline:
        pane = _capture(session)
        if text in pane:
            return pane
        time.sleep(0.05)
    return pane


def test_tui_process_terminal_smoke_in_tmux(tmp_path: Path) -> None:
    if shutil.which("tmux") is None:
        pytest.skip("tmux is not installed")

    script = tmp_path / "tmux_smoke.py"
    script.write_text(
        textwrap.dedent(
            """
            import time

            from saber_tui import ProcessTerminal, TUI


            class App:
                def __init__(self) -> None:
                    self.text = "ready"

                def render(self, width: int) -> list[str]:
                    return [self.text[:width]]


            app = App()
            tui = TUI(ProcessTerminal())
            tui.add_child(app)


            def on_input(data: str):
                if data == "x":
                    app.text = "changed"
                    tui.request_render()
                    return {"consume": True}
                if data == "q":
                    tui.stop()
                    return {"consume": True}
                return None


            tui.add_input_listener(on_input)
            tui.start()
            deadline = time.monotonic() + 10
            while not tui.stopped and time.monotonic() < deadline:
                time.sleep(0.05)
            if not tui.stopped:
                tui.stop()
            """
        ),
        encoding="utf-8",
    )

    session = f"saber_tui_{uuid.uuid4().hex}"
    repo = Path(__file__).resolve().parents[1]
    command = f"cd {shlex.quote(str(repo))} && uv run python {shlex.quote(str(script))}"

    try:
        _run(["tmux", "new-session", "-d", "-x", "40", "-y", "8", "-s", session, command])
        pane = _wait_for_pane_text(session, "ready")
        assert "ready" in pane

        _run(["tmux", "send-keys", "-t", session, "x"])
        pane = _wait_for_pane_text(session, "changed")
        assert "changed" in pane

        _run(["tmux", "resize-window", "-t", session, "-x", "30", "-y", "6"])
        pane = _wait_for_pane_text(session, "changed")
        assert "changed" in pane

        _run(["tmux", "send-keys", "-t", session, "q"])
    finally:
        subprocess.run(["tmux", "kill-session", "-t", session], check=False, capture_output=True, text=True, timeout=5)
