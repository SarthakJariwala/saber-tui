from __future__ import annotations

from dataclasses import dataclass

from saber_tui.keys import matches_key

KeyId = str
Keybinding = str
KeybindingsConfig = dict[str, KeyId | list[KeyId] | None]


@dataclass(frozen=True)
class KeybindingConflict:
    key: KeyId
    keybindings: list[Keybinding]


TUI_KEYBINDINGS: dict[str, dict[str, KeyId | list[KeyId] | str]] = {
    "tui.editor.cursorUp": {"default_keys": "up", "description": "Move cursor up"},
    "tui.editor.cursorDown": {"default_keys": "down", "description": "Move cursor down"},
    "tui.editor.cursorLeft": {"default_keys": ["left", "ctrl+b"], "description": "Move cursor left"},
    "tui.editor.cursorRight": {"default_keys": ["right", "ctrl+f"], "description": "Move cursor right"},
    "tui.editor.cursorWordLeft": {
        "default_keys": ["alt+left", "ctrl+left", "alt+b"],
        "description": "Move cursor word left",
    },
    "tui.editor.cursorWordRight": {
        "default_keys": ["alt+right", "ctrl+right", "alt+f"],
        "description": "Move cursor word right",
    },
    "tui.editor.cursorLineStart": {"default_keys": ["home", "ctrl+a"], "description": "Move to line start"},
    "tui.editor.cursorLineEnd": {"default_keys": ["end", "ctrl+e"], "description": "Move to line end"},
    "tui.editor.jumpForward": {"default_keys": "ctrl+]", "description": "Jump forward to character"},
    "tui.editor.jumpBackward": {"default_keys": "ctrl+alt+]", "description": "Jump backward to character"},
    "tui.editor.pageUp": {"default_keys": "pageUp", "description": "Page up"},
    "tui.editor.pageDown": {"default_keys": "pageDown", "description": "Page down"},
    "tui.editor.deleteCharBackward": {"default_keys": "backspace", "description": "Delete character backward"},
    "tui.editor.deleteCharForward": {"default_keys": ["delete", "ctrl+d"], "description": "Delete character forward"},
    "tui.editor.deleteWordBackward": {
        "default_keys": ["ctrl+w", "alt+backspace"],
        "description": "Delete word backward",
    },
    "tui.editor.deleteWordForward": {"default_keys": ["alt+d", "alt+delete"], "description": "Delete word forward"},
    "tui.editor.deleteToLineStart": {"default_keys": "ctrl+u", "description": "Delete to line start"},
    "tui.editor.deleteToLineEnd": {"default_keys": "ctrl+k", "description": "Delete to line end"},
    "tui.editor.yank": {"default_keys": "ctrl+y", "description": "Yank"},
    "tui.editor.yankPop": {"default_keys": "alt+y", "description": "Yank pop"},
    "tui.editor.undo": {"default_keys": "ctrl+-", "description": "Undo"},
    "tui.input.newLine": {"default_keys": "shift+enter", "description": "Insert newline"},
    "tui.input.submit": {"default_keys": "enter", "description": "Submit input"},
    "tui.input.tab": {"default_keys": "tab", "description": "Tab / autocomplete"},
    "tui.input.copy": {"default_keys": "ctrl+c", "description": "Copy selection"},
    "tui.select.up": {"default_keys": "up", "description": "Move selection up"},
    "tui.select.down": {"default_keys": "down", "description": "Move selection down"},
    "tui.select.pageUp": {"default_keys": "pageUp", "description": "Selection page up"},
    "tui.select.pageDown": {"default_keys": "pageDown", "description": "Selection page down"},
    "tui.select.confirm": {"default_keys": "enter", "description": "Confirm selection"},
    "tui.select.cancel": {"default_keys": ["escape", "ctrl+c"], "description": "Cancel selection"},
}


def _normalize_keys(keys: KeyId | list[KeyId] | None) -> list[KeyId]:
    if keys is None:
        return []

    key_list = keys if isinstance(keys, list) else [keys]
    seen: set[KeyId] = set()
    result: list[KeyId] = []
    for key in key_list:
        if key not in seen:
            seen.add(key)
            result.append(key)
    return result


class KeybindingsManager:
    def __init__(
        self,
        user_bindings: KeybindingsConfig | None = None,
        definitions: dict[str, dict[str, KeyId | list[KeyId] | str]] | None = None,
    ) -> None:
        self._definitions = definitions or TUI_KEYBINDINGS
        self._user_bindings = user_bindings or {}
        self._keys_by_id: dict[Keybinding, list[KeyId]] = {}
        self._conflicts: list[KeybindingConflict] = []
        self._rebuild()

    def _rebuild(self) -> None:
        self._keys_by_id.clear()
        self._conflicts = []

        user_claims: dict[KeyId, set[Keybinding]] = {}
        for keybinding, keys in self._user_bindings.items():
            if keybinding not in self._definitions:
                continue
            for key in _normalize_keys(keys):
                user_claims.setdefault(key, set()).add(keybinding)

        for key, keybindings in user_claims.items():
            if len(keybindings) > 1:
                self._conflicts.append(KeybindingConflict(key, list(keybindings)))

        for keybinding, definition in self._definitions.items():
            user_keys = self._user_bindings.get(keybinding)
            default_keys = definition["default_keys"]
            if user_keys is None and keybinding not in self._user_bindings:
                keys = _normalize_keys(default_keys)
            else:
                keys = _normalize_keys(user_keys)
            self._keys_by_id[keybinding] = keys

    def matches(self, data: str, keybinding: Keybinding) -> bool:
        return any(matches_key(data, key) for key in self._keys_by_id.get(keybinding, []))

    def get_keys(self, keybinding: Keybinding) -> list[KeyId]:
        return list(self._keys_by_id.get(keybinding, []))

    def get_definition(self, keybinding: Keybinding) -> dict[str, KeyId | list[KeyId] | str]:
        return self._definitions[keybinding]

    def get_conflicts(self) -> list[KeybindingConflict]:
        return [KeybindingConflict(conflict.key, list(conflict.keybindings)) for conflict in self._conflicts]

    def set_user_bindings(self, user_bindings: KeybindingsConfig) -> None:
        self._user_bindings = user_bindings
        self._rebuild()

    def get_user_bindings(self) -> KeybindingsConfig:
        return dict(self._user_bindings)

    def get_resolved_bindings(self) -> KeybindingsConfig:
        resolved: KeybindingsConfig = {}
        for keybinding in self._definitions:
            keys = self._keys_by_id.get(keybinding, [])
            resolved[keybinding] = keys[0] if len(keys) == 1 else list(keys)
        return resolved


_global_keybindings: KeybindingsManager | None = None


def set_keybindings(keybindings: KeybindingsManager) -> None:
    global _global_keybindings
    _global_keybindings = keybindings


def get_keybindings() -> KeybindingsManager:
    global _global_keybindings
    if _global_keybindings is None:
        _global_keybindings = KeybindingsManager()
    return _global_keybindings
