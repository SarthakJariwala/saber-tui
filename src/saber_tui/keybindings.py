from dataclasses import dataclass


@dataclass(frozen=True)
class KeybindingConflict:
    key: str
    keybindings: list[str]


class KeybindingsManager:
    pass


def get_keybindings() -> KeybindingsManager:
    return KeybindingsManager()


def set_keybindings(keybindings: KeybindingsManager) -> None:
    return None
