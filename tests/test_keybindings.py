from saber_tui.keybindings import KeybindingsManager, get_keybindings, set_keybindings


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
