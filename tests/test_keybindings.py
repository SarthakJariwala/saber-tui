from collections.abc import Iterator

import pytest

from saber_tui.keybindings import KeybindingsManager, get_keybindings, set_keybindings


@pytest.fixture(autouse=True)
def restore_global_keybindings() -> Iterator[None]:
    original = get_keybindings()
    yield
    set_keybindings(original)


def test_default_keybinding_matches_action() -> None:
    manager = KeybindingsManager()

    assert manager.matches("\x1b[A", "tui.select.up")
    assert manager.matches("\r", "tui.select.confirm")


def test_user_binding_replaces_default_keys() -> None:
    manager = KeybindingsManager({"tui.select.confirm": "ctrl+j"})

    assert manager.matches("\n", "tui.select.confirm")
    assert not manager.matches("\r", "tui.select.confirm")


def test_conflicts_report_user_claims() -> None:
    manager = KeybindingsManager({"tui.select.up": "ctrl+x", "tui.select.down": "ctrl+x"})

    conflicts = manager.get_conflicts()
    assert len(conflicts) == 1
    assert conflicts[0].key == "ctrl+x"
    assert set(conflicts[0].keybindings) == {"tui.select.up", "tui.select.down"}


def test_global_keybindings_can_be_replaced() -> None:
    custom = KeybindingsManager({"tui.select.confirm": "ctrl+j"})
    set_keybindings(custom)

    assert get_keybindings() is custom


def test_editor_jump_and_page_bindings_exist() -> None:
    keybindings = KeybindingsManager()

    assert keybindings.get_keys("tui.editor.jumpForward") == ["ctrl+]"]
    assert keybindings.get_keys("tui.editor.jumpBackward") == ["ctrl+alt+]"]
    assert keybindings.get_keys("tui.editor.pageUp") == ["pageUp"]
    assert keybindings.get_keys("tui.editor.pageDown") == ["pageDown"]


def test_editor_jump_binding_can_be_rebound_without_evicting_defaults() -> None:
    keybindings = KeybindingsManager({"tui.editor.jumpForward": "alt+j"})

    assert keybindings.get_keys("tui.editor.jumpForward") == ["alt+j"]
    assert keybindings.get_keys("tui.editor.cursorLeft") == ["left", "ctrl+b"]
