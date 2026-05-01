from __future__ import annotations

import os
import re
from dataclasses import dataclass

SHIFT = 1
ALT = 2
CTRL = 4
SUPER = 8
LOCK_MASK = 64 + 128

CODEPOINTS = {
    "escape": 27,
    "tab": 9,
    "enter": 13,
    "space": 32,
    "backspace": 127,
    "kpEnter": 57414,
}

ARROW_CODEPOINTS = {
    "up": -1,
    "down": -2,
    "right": -3,
    "left": -4,
}

FUNCTIONAL_CODEPOINTS = {
    "delete": -10,
    "insert": -11,
    "pageUp": -12,
    "pageDown": -13,
    "home": -14,
    "end": -15,
}

KITTY_FUNCTIONAL_KEY_EQUIVALENTS = {
    57399: 48,
    57400: 49,
    57401: 50,
    57402: 51,
    57403: 52,
    57404: 53,
    57405: 54,
    57406: 55,
    57407: 56,
    57408: 57,
    57409: 46,
    57410: 47,
    57411: 42,
    57412: 45,
    57413: 43,
    57415: 61,
    57416: 44,
    57417: ARROW_CODEPOINTS["left"],
    57418: ARROW_CODEPOINTS["right"],
    57419: ARROW_CODEPOINTS["up"],
    57420: ARROW_CODEPOINTS["down"],
    57421: FUNCTIONAL_CODEPOINTS["pageUp"],
    57422: FUNCTIONAL_CODEPOINTS["pageDown"],
    57423: FUNCTIONAL_CODEPOINTS["home"],
    57424: FUNCTIONAL_CODEPOINTS["end"],
    57425: FUNCTIONAL_CODEPOINTS["insert"],
    57426: FUNCTIONAL_CODEPOINTS["delete"],
}

SYMBOL_KEYS = {
    "`",
    "-",
    "=",
    "[",
    "]",
    "\\",
    ";",
    "'",
    ",",
    ".",
    "/",
    "!",
    "@",
    "#",
    "$",
    "%",
    "^",
    "&",
    "*",
    "(",
    ")",
    "_",
    "+",
    "|",
    "~",
    "{",
    "}",
    ":",
    "<",
    ">",
    "?",
}

LEGACY_KEY_SEQUENCES = {
    "up": ["\x1b[A", "\x1bOA"],
    "down": ["\x1b[B", "\x1bOB"],
    "right": ["\x1b[C", "\x1bOC"],
    "left": ["\x1b[D", "\x1bOD"],
    "home": ["\x1b[H", "\x1bOH", "\x1b[1~", "\x1b[7~"],
    "end": ["\x1b[F", "\x1bOF", "\x1b[4~", "\x1b[8~"],
    "insert": ["\x1b[2~"],
    "delete": ["\x1b[3~"],
    "pageUp": ["\x1b[5~", "\x1b[[5~"],
    "pageDown": ["\x1b[6~", "\x1b[[6~"],
    "clear": ["\x1b[E", "\x1bOE"],
    "f1": ["\x1bOP", "\x1b[11~", "\x1b[[A"],
    "f2": ["\x1bOQ", "\x1b[12~", "\x1b[[B"],
    "f3": ["\x1bOR", "\x1b[13~", "\x1b[[C"],
    "f4": ["\x1bOS", "\x1b[14~", "\x1b[[D"],
    "f5": ["\x1b[15~", "\x1b[[E"],
    "f6": ["\x1b[17~"],
    "f7": ["\x1b[18~"],
    "f8": ["\x1b[19~"],
    "f9": ["\x1b[20~"],
    "f10": ["\x1b[21~"],
    "f11": ["\x1b[23~"],
    "f12": ["\x1b[24~"],
}

LEGACY_SHIFT_SEQUENCES = {
    "up": ["\x1b[a"],
    "down": ["\x1b[b"],
    "right": ["\x1b[c"],
    "left": ["\x1b[d"],
    "clear": ["\x1b[e"],
    "insert": ["\x1b[2$"],
    "delete": ["\x1b[3$"],
    "pageUp": ["\x1b[5$"],
    "pageDown": ["\x1b[6$"],
    "home": ["\x1b[7$"],
    "end": ["\x1b[8$"],
}

LEGACY_CTRL_SEQUENCES = {
    "up": ["\x1bOa"],
    "down": ["\x1bOb"],
    "right": ["\x1bOc"],
    "left": ["\x1bOd"],
    "clear": ["\x1bOe"],
    "insert": ["\x1b[2^"],
    "delete": ["\x1b[3^"],
    "pageUp": ["\x1b[5^"],
    "pageDown": ["\x1b[6^"],
    "home": ["\x1b[7^"],
    "end": ["\x1b[8^"],
}

LEGACY_SEQUENCE_KEY_IDS = {
    "\x1bOA": "up",
    "\x1bOB": "down",
    "\x1bOC": "right",
    "\x1bOD": "left",
    "\x1bOH": "home",
    "\x1bOF": "end",
    "\x1b[E": "clear",
    "\x1bOE": "clear",
    "\x1bOe": "ctrl+clear",
    "\x1b[e": "shift+clear",
    "\x1b[2~": "insert",
    "\x1b[2$": "shift+insert",
    "\x1b[2^": "ctrl+insert",
    "\x1b[3$": "shift+delete",
    "\x1b[3^": "ctrl+delete",
    "\x1b[[5~": "pageUp",
    "\x1b[[6~": "pageDown",
    "\x1b[a": "shift+up",
    "\x1b[b": "shift+down",
    "\x1b[c": "shift+right",
    "\x1b[d": "shift+left",
    "\x1bOa": "ctrl+up",
    "\x1bOb": "ctrl+down",
    "\x1bOc": "ctrl+right",
    "\x1bOd": "ctrl+left",
    "\x1b[5$": "shift+pageUp",
    "\x1b[6$": "shift+pageDown",
    "\x1b[7$": "shift+home",
    "\x1b[8$": "shift+end",
    "\x1b[5^": "ctrl+pageUp",
    "\x1b[6^": "ctrl+pageDown",
    "\x1b[7^": "ctrl+home",
    "\x1b[8^": "ctrl+end",
    "\x1bOP": "f1",
    "\x1bOQ": "f2",
    "\x1bOR": "f3",
    "\x1bOS": "f4",
    "\x1b[11~": "f1",
    "\x1b[12~": "f2",
    "\x1b[13~": "f3",
    "\x1b[14~": "f4",
    "\x1b[[A": "f1",
    "\x1b[[B": "f2",
    "\x1b[[C": "f3",
    "\x1b[[D": "f4",
    "\x1b[[E": "f5",
    "\x1b[15~": "f5",
    "\x1b[17~": "f6",
    "\x1b[18~": "f7",
    "\x1b[19~": "f8",
    "\x1b[20~": "f9",
    "\x1b[21~": "f10",
    "\x1b[23~": "f11",
    "\x1b[24~": "f12",
    "\x1bb": "alt+left",
    "\x1bf": "alt+right",
    "\x1bp": "alt+up",
    "\x1bn": "alt+down",
}

KITTY_CSI_U_REGEX = re.compile(r"^\x1b\[(\d+)(?::(\d*))?(?::(\d+))?(?:;(\d+))?(?::(\d+))?u$")
KITTY_PRINTABLE_ALLOWED_MODIFIERS = SHIFT | LOCK_MASK

_kitty_protocol_active = False


@dataclass(frozen=True)
class ParsedKittySequence:
    codepoint: int
    modifier: int
    event_type: str
    shifted_key: int | None = None
    base_layout_key: int | None = None


@dataclass(frozen=True)
class ParsedModifyOtherKeysSequence:
    codepoint: int
    modifier: int


def set_kitty_protocol_active(active: bool) -> None:
    global _kitty_protocol_active
    _kitty_protocol_active = active


def is_kitty_protocol_active() -> bool:
    return _kitty_protocol_active


def is_key_release(data: str) -> bool:
    if "\x1b[200~" in data:
        return False
    return any(token in data for token in (":3u", ":3~", ":3A", ":3B", ":3C", ":3D", ":3H", ":3F"))


def is_key_repeat(data: str) -> bool:
    if "\x1b[200~" in data:
        return False
    return any(token in data for token in (":2u", ":2~", ":2A", ":2B", ":2C", ":2D", ":2H", ":2F"))


def _normalize_kitty_functional_codepoint(codepoint: int) -> int:
    return KITTY_FUNCTIONAL_KEY_EQUIVALENTS.get(codepoint, codepoint)


def _normalize_shifted_letter_identity_codepoint(codepoint: int, modifier: int) -> int:
    effective_modifier = modifier & ~LOCK_MASK
    if effective_modifier & SHIFT and 65 <= codepoint <= 90:
        return codepoint + 32
    return codepoint


def _matches_legacy_sequence(data: str, sequences: list[str]) -> bool:
    return data in sequences


def _matches_legacy_modifier_sequence(data: str, key: str, modifier: int) -> bool:
    if modifier == SHIFT:
        return _matches_legacy_sequence(data, LEGACY_SHIFT_SEQUENCES[key])
    if modifier == CTRL:
        return _matches_legacy_sequence(data, LEGACY_CTRL_SEQUENCES[key])
    return False


def _parse_event_type(event_type: str | None) -> str:
    if not event_type:
        return "press"
    if int(event_type) == 2:
        return "repeat"
    if int(event_type) == 3:
        return "release"
    return "press"


def _parse_kitty_sequence(data: str) -> ParsedKittySequence | None:
    csi_u_match = KITTY_CSI_U_REGEX.match(data)
    if csi_u_match:
        codepoint = int(csi_u_match.group(1))
        shifted = csi_u_match.group(2)
        shifted_key = int(shifted) if shifted else None
        base = csi_u_match.group(3)
        base_layout_key = int(base) if base else None
        mod_value = int(csi_u_match.group(4)) if csi_u_match.group(4) else 1
        event_type = _parse_event_type(csi_u_match.group(5))
        return ParsedKittySequence(codepoint, mod_value - 1, event_type, shifted_key, base_layout_key)

    arrow_match = re.match(r"^\x1b\[1;(\d+)(?::(\d+))?([ABCD])$", data)
    if arrow_match:
        arrow_codes = {"A": -1, "B": -2, "C": -3, "D": -4}
        return ParsedKittySequence(
            arrow_codes[arrow_match.group(3)],
            int(arrow_match.group(1)) - 1,
            _parse_event_type(arrow_match.group(2)),
        )

    func_match = re.match(r"^\x1b\[(\d+)(?:;(\d+))?(?::(\d+))?~$", data)
    if func_match:
        func_codes = {
            2: FUNCTIONAL_CODEPOINTS["insert"],
            3: FUNCTIONAL_CODEPOINTS["delete"],
            5: FUNCTIONAL_CODEPOINTS["pageUp"],
            6: FUNCTIONAL_CODEPOINTS["pageDown"],
            7: FUNCTIONAL_CODEPOINTS["home"],
            8: FUNCTIONAL_CODEPOINTS["end"],
        }
        codepoint = func_codes.get(int(func_match.group(1)))
        if codepoint is not None:
            mod_value = int(func_match.group(2)) if func_match.group(2) else 1
            return ParsedKittySequence(codepoint, mod_value - 1, _parse_event_type(func_match.group(3)))

    home_end_match = re.match(r"^\x1b\[1;(\d+)(?::(\d+))?([HF])$", data)
    if home_end_match:
        codepoint = FUNCTIONAL_CODEPOINTS["home"] if home_end_match.group(3) == "H" else FUNCTIONAL_CODEPOINTS["end"]
        return ParsedKittySequence(
            codepoint,
            int(home_end_match.group(1)) - 1,
            _parse_event_type(home_end_match.group(2)),
        )

    return None


def _matches_kitty_sequence(data: str, expected_codepoint: int, expected_modifier: int) -> bool:
    parsed = _parse_kitty_sequence(data)
    if not parsed:
        return False

    actual_modifier = parsed.modifier & ~LOCK_MASK
    expected_modifier = expected_modifier & ~LOCK_MASK
    if actual_modifier != expected_modifier:
        return False

    normalized_codepoint = _normalize_shifted_letter_identity_codepoint(
        _normalize_kitty_functional_codepoint(parsed.codepoint), parsed.modifier
    )
    normalized_expected = _normalize_shifted_letter_identity_codepoint(
        _normalize_kitty_functional_codepoint(expected_codepoint), expected_modifier
    )
    if normalized_codepoint == normalized_expected:
        return True

    if parsed.base_layout_key is not None and parsed.base_layout_key == expected_codepoint:
        char = chr(normalized_codepoint) if normalized_codepoint >= 0 else ""
        if not (97 <= normalized_codepoint <= 122) and char not in SYMBOL_KEYS:
            return True

    return False


def _parse_modify_other_keys_sequence(data: str) -> ParsedModifyOtherKeysSequence | None:
    match = re.match(r"^\x1b\[27;(\d+);(\d+)~$", data)
    if not match:
        return None
    return ParsedModifyOtherKeysSequence(int(match.group(2)), int(match.group(1)) - 1)


def _matches_modify_other_keys(data: str, expected_keycode: int, expected_modifier: int) -> bool:
    parsed = _parse_modify_other_keys_sequence(data)
    return bool(parsed and parsed.codepoint == expected_keycode and parsed.modifier == expected_modifier)


def _matches_printable_modify_other_keys(data: str, expected_keycode: int, expected_modifier: int) -> bool:
    if expected_modifier == 0:
        return False
    parsed = _parse_modify_other_keys_sequence(data)
    if not parsed or parsed.modifier != expected_modifier:
        return False
    return _normalize_shifted_letter_identity_codepoint(
        parsed.codepoint, parsed.modifier
    ) == _normalize_shifted_letter_identity_codepoint(expected_keycode, expected_modifier)


def _is_windows_terminal_session() -> bool:
    return bool(os.environ.get("WT_SESSION")) and not any(
        os.environ.get(name) for name in ("SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY")
    )


def _matches_raw_backspace(data: str, expected_modifier: int) -> bool:
    if data == "\x7f":
        return expected_modifier == 0
    if data != "\x08":
        return False
    return expected_modifier == CTRL if _is_windows_terminal_session() else expected_modifier == 0


def _raw_ctrl_char(key: str) -> str | None:
    char = key.lower()
    code = ord(char)
    if 97 <= code <= 122 or char in {"[", "\\", "]", "_"}:
        return chr(code & 0x1F)
    if char == "-":
        return chr(31)
    return None


def _is_digit_key(key: str) -> bool:
    return "0" <= key <= "9"


def _format_key_name_with_modifiers(key_name: str, modifier: int) -> str | None:
    mods: list[str] = []
    effective_modifier = modifier & ~LOCK_MASK
    supported_modifier_mask = SHIFT | CTRL | ALT | SUPER
    if effective_modifier & ~supported_modifier_mask:
        return None
    if effective_modifier & SHIFT:
        mods.append("shift")
    if effective_modifier & CTRL:
        mods.append("ctrl")
    if effective_modifier & ALT:
        mods.append("alt")
    if effective_modifier & SUPER:
        mods.append("super")
    return f"{'+'.join(mods)}+{key_name}" if mods else key_name


def _parse_key_id(key_id: str) -> tuple[str, int] | None:
    parts = key_id.lower().split("+")
    if key_id.endswith("+"):
        key = "+"
        modifier_parts = parts[:-2]
    else:
        key = parts[-1]
        modifier_parts = parts[:-1]
    if not key or any(part not in {"shift", "alt", "ctrl", "super"} for part in modifier_parts):
        return None
    modifier = 0
    if "shift" in modifier_parts:
        modifier |= SHIFT
    if "alt" in modifier_parts:
        modifier |= ALT
    if "ctrl" in modifier_parts:
        modifier |= CTRL
    if "super" in modifier_parts:
        modifier |= SUPER
    return key, modifier


def matches_key(data: str, key_id: str) -> bool:
    parsed_key = _parse_key_id(key_id)
    if not parsed_key:
        return False
    key, modifier = parsed_key

    if key in {"escape", "esc"}:
        if modifier == 0:
            return (
                data == "\x1b"
                or _matches_kitty_sequence(data, CODEPOINTS["escape"], 0)
                or _matches_modify_other_keys(data, CODEPOINTS["escape"], 0)
            )
        return _matches_kitty_sequence(data, CODEPOINTS["escape"], modifier) or _matches_modify_other_keys(
            data, CODEPOINTS["escape"], modifier
        )

    if key == "space":
        if not _kitty_protocol_active:
            if modifier == CTRL and data == "\x00":
                return True
            if modifier == ALT and data == "\x1b ":
                return True
        if modifier == 0:
            return (
                data == " "
                or _matches_kitty_sequence(data, CODEPOINTS["space"], 0)
                or _matches_modify_other_keys(data, CODEPOINTS["space"], 0)
            )
        return _matches_kitty_sequence(data, CODEPOINTS["space"], modifier) or _matches_modify_other_keys(
            data, CODEPOINTS["space"], modifier
        )

    if key == "tab":
        if modifier == SHIFT:
            return (
                data == "\x1b[Z"
                or _matches_kitty_sequence(data, CODEPOINTS["tab"], SHIFT)
                or _matches_modify_other_keys(data, CODEPOINTS["tab"], SHIFT)
            )
        if modifier == 0:
            return data == "\t" or _matches_kitty_sequence(data, CODEPOINTS["tab"], 0)
        return _matches_kitty_sequence(data, CODEPOINTS["tab"], modifier) or _matches_modify_other_keys(
            data, CODEPOINTS["tab"], modifier
        )

    if key in {"enter", "return"}:
        if modifier == SHIFT:
            if _matches_kitty_sequence(data, CODEPOINTS["enter"], SHIFT) or _matches_kitty_sequence(
                data, CODEPOINTS["kpEnter"], SHIFT
            ):
                return True
            if _matches_modify_other_keys(data, CODEPOINTS["enter"], SHIFT):
                return True
            return _kitty_protocol_active and data in {"\x1b\r", "\n"}
        if modifier == ALT:
            if _matches_kitty_sequence(data, CODEPOINTS["enter"], ALT) or _matches_kitty_sequence(
                data, CODEPOINTS["kpEnter"], ALT
            ):
                return True
            if _matches_modify_other_keys(data, CODEPOINTS["enter"], ALT):
                return True
            return not _kitty_protocol_active and data == "\x1b\r"
        if modifier == 0:
            return (
                data == "\r"
                or (not _kitty_protocol_active and data == "\n")
                or data == "\x1bOM"
                or _matches_kitty_sequence(data, CODEPOINTS["enter"], 0)
                or _matches_kitty_sequence(data, CODEPOINTS["kpEnter"], 0)
            )
        return (
            _matches_kitty_sequence(data, CODEPOINTS["enter"], modifier)
            or _matches_kitty_sequence(data, CODEPOINTS["kpEnter"], modifier)
            or _matches_modify_other_keys(data, CODEPOINTS["enter"], modifier)
        )

    if key == "backspace":
        if modifier == ALT:
            return (
                data in {"\x1b\x7f", "\x1b\b"}
                or _matches_kitty_sequence(data, CODEPOINTS["backspace"], ALT)
                or _matches_modify_other_keys(data, CODEPOINTS["backspace"], ALT)
            )
        if modifier == CTRL:
            return (
                _matches_raw_backspace(data, CTRL)
                or _matches_kitty_sequence(data, CODEPOINTS["backspace"], CTRL)
                or _matches_modify_other_keys(data, CODEPOINTS["backspace"], CTRL)
            )
        if modifier == 0:
            return (
                _matches_raw_backspace(data, 0)
                or _matches_kitty_sequence(data, CODEPOINTS["backspace"], 0)
                or _matches_modify_other_keys(data, CODEPOINTS["backspace"], 0)
            )
        return _matches_kitty_sequence(data, CODEPOINTS["backspace"], modifier) or _matches_modify_other_keys(
            data, CODEPOINTS["backspace"], modifier
        )

    if key in {"insert", "delete", "clear", "home", "end", "pageup", "pagedown", "up", "down", "left", "right"}:
        return _matches_special_key(data, key, modifier)

    if key in {f"f{i}" for i in range(1, 13)}:
        return modifier == 0 and _matches_legacy_sequence(data, LEGACY_KEY_SEQUENCES[key])

    if len(key) == 1 and ("a" <= key <= "z" or _is_digit_key(key) or key in SYMBOL_KEYS):
        return _matches_printable_key(data, key, modifier)

    return False


def _matches_special_key(data: str, key: str, modifier: int) -> bool:
    sequence_key = {"pageup": "pageUp", "pagedown": "pageDown"}.get(key, key)

    if key == "clear":
        if modifier == 0:
            return _matches_legacy_sequence(data, LEGACY_KEY_SEQUENCES["clear"])
        return _matches_legacy_modifier_sequence(data, "clear", modifier)

    if key in {"insert", "delete", "home", "end", "pageup", "pagedown"}:
        functional_key = {"pageup": "pageUp", "pagedown": "pageDown"}.get(key, key)
        if modifier == 0:
            return _matches_legacy_sequence(data, LEGACY_KEY_SEQUENCES[sequence_key]) or _matches_kitty_sequence(
                data, FUNCTIONAL_CODEPOINTS[functional_key], 0
            )
        return _matches_legacy_modifier_sequence(data, sequence_key, modifier) or _matches_kitty_sequence(
            data, FUNCTIONAL_CODEPOINTS[functional_key], modifier
        )

    if key == "up":
        if modifier == ALT:
            return data == "\x1bp" or _matches_kitty_sequence(data, ARROW_CODEPOINTS["up"], ALT)
        if modifier == 0:
            return _matches_legacy_sequence(data, LEGACY_KEY_SEQUENCES["up"]) or _matches_kitty_sequence(
                data, ARROW_CODEPOINTS["up"], 0
            )
        return _matches_legacy_modifier_sequence(data, "up", modifier) or _matches_kitty_sequence(
            data, ARROW_CODEPOINTS["up"], modifier
        )

    if key == "down":
        if modifier == ALT:
            return data == "\x1bn" or _matches_kitty_sequence(data, ARROW_CODEPOINTS["down"], ALT)
        if modifier == 0:
            return _matches_legacy_sequence(data, LEGACY_KEY_SEQUENCES["down"]) or _matches_kitty_sequence(
                data, ARROW_CODEPOINTS["down"], 0
            )
        return _matches_legacy_modifier_sequence(data, "down", modifier) or _matches_kitty_sequence(
            data, ARROW_CODEPOINTS["down"], modifier
        )

    if key == "left":
        if modifier == ALT:
            return (
                data == "\x1b[1;3D"
                or (not _kitty_protocol_active and data == "\x1bB")
                or data == "\x1bb"
                or _matches_kitty_sequence(data, ARROW_CODEPOINTS["left"], ALT)
            )
        if modifier == CTRL:
            return (
                data == "\x1b[1;5D"
                or _matches_legacy_modifier_sequence(data, "left", CTRL)
                or _matches_kitty_sequence(data, ARROW_CODEPOINTS["left"], CTRL)
            )
        if modifier == 0:
            return _matches_legacy_sequence(data, LEGACY_KEY_SEQUENCES["left"]) or _matches_kitty_sequence(
                data, ARROW_CODEPOINTS["left"], 0
            )
        return _matches_legacy_modifier_sequence(data, "left", modifier) or _matches_kitty_sequence(
            data, ARROW_CODEPOINTS["left"], modifier
        )

    if key == "right":
        if modifier == ALT:
            return (
                data == "\x1b[1;3C"
                or (not _kitty_protocol_active and data == "\x1bF")
                or data == "\x1bf"
                or _matches_kitty_sequence(data, ARROW_CODEPOINTS["right"], ALT)
            )
        if modifier == CTRL:
            return (
                data == "\x1b[1;5C"
                or _matches_legacy_modifier_sequence(data, "right", CTRL)
                or _matches_kitty_sequence(data, ARROW_CODEPOINTS["right"], CTRL)
            )
        if modifier == 0:
            return _matches_legacy_sequence(data, LEGACY_KEY_SEQUENCES["right"]) or _matches_kitty_sequence(
                data, ARROW_CODEPOINTS["right"], 0
            )
        return _matches_legacy_modifier_sequence(data, "right", modifier) or _matches_kitty_sequence(
            data, ARROW_CODEPOINTS["right"], modifier
        )

    return False


def _matches_printable_key(data: str, key: str, modifier: int) -> bool:
    codepoint = ord(key)
    raw_ctrl = _raw_ctrl_char(key)
    is_letter = "a" <= key <= "z"
    is_digit = _is_digit_key(key)

    if modifier == CTRL + ALT and not _kitty_protocol_active and raw_ctrl and data == f"\x1b{raw_ctrl}":
        return True

    if modifier == ALT and not _kitty_protocol_active and (is_letter or is_digit) and data == f"\x1b{key}":
        return True

    if modifier == CTRL:
        if raw_ctrl and data == raw_ctrl:
            return True
        return _matches_kitty_sequence(data, codepoint, CTRL) or _matches_printable_modify_other_keys(
            data, codepoint, CTRL
        )

    if modifier == SHIFT + CTRL:
        return _matches_kitty_sequence(data, codepoint, SHIFT + CTRL) or _matches_printable_modify_other_keys(
            data, codepoint, SHIFT + CTRL
        )

    if modifier == SHIFT:
        if is_letter and data == key.upper():
            return True
        return _matches_kitty_sequence(data, codepoint, SHIFT) or _matches_printable_modify_other_keys(
            data, codepoint, SHIFT
        )

    if modifier != 0:
        return _matches_kitty_sequence(data, codepoint, modifier) or _matches_printable_modify_other_keys(
            data, codepoint, modifier
        )

    return data == key or _matches_kitty_sequence(data, codepoint, 0)


def _format_parsed_key(codepoint: int, modifier: int, base_layout_key: int | None = None) -> str | None:
    normalized_codepoint = _normalize_kitty_functional_codepoint(codepoint)
    identity_codepoint = _normalize_shifted_letter_identity_codepoint(normalized_codepoint, modifier)

    char = chr(identity_codepoint) if identity_codepoint >= 0 else ""
    is_latin_letter = 97 <= identity_codepoint <= 122
    is_digit = 48 <= identity_codepoint <= 57
    is_known_symbol = char in SYMBOL_KEYS
    if is_latin_letter or is_digit or is_known_symbol:
        effective_codepoint = identity_codepoint
    else:
        effective_codepoint = base_layout_key or identity_codepoint

    key_name: str | None = None
    if effective_codepoint == CODEPOINTS["escape"]:
        key_name = "escape"
    elif effective_codepoint == CODEPOINTS["tab"]:
        key_name = "tab"
    elif effective_codepoint in {CODEPOINTS["enter"], CODEPOINTS["kpEnter"]}:
        key_name = "enter"
    elif effective_codepoint == CODEPOINTS["space"]:
        key_name = "space"
    elif effective_codepoint == CODEPOINTS["backspace"]:
        key_name = "backspace"
    elif effective_codepoint == FUNCTIONAL_CODEPOINTS["delete"]:
        key_name = "delete"
    elif effective_codepoint == FUNCTIONAL_CODEPOINTS["insert"]:
        key_name = "insert"
    elif effective_codepoint == FUNCTIONAL_CODEPOINTS["home"]:
        key_name = "home"
    elif effective_codepoint == FUNCTIONAL_CODEPOINTS["end"]:
        key_name = "end"
    elif effective_codepoint == FUNCTIONAL_CODEPOINTS["pageUp"]:
        key_name = "pageUp"
    elif effective_codepoint == FUNCTIONAL_CODEPOINTS["pageDown"]:
        key_name = "pageDown"
    elif effective_codepoint == ARROW_CODEPOINTS["up"]:
        key_name = "up"
    elif effective_codepoint == ARROW_CODEPOINTS["down"]:
        key_name = "down"
    elif effective_codepoint == ARROW_CODEPOINTS["left"]:
        key_name = "left"
    elif effective_codepoint == ARROW_CODEPOINTS["right"]:
        key_name = "right"
    elif (
        48 <= effective_codepoint <= 57
        or 97 <= effective_codepoint <= 122
        or (effective_codepoint >= 0 and chr(effective_codepoint) in SYMBOL_KEYS)
    ):
        key_name = chr(effective_codepoint)

    if not key_name:
        return None
    return _format_key_name_with_modifiers(key_name, modifier)


def parse_key(data: str) -> str | None:
    kitty = _parse_kitty_sequence(data)
    if kitty:
        return _format_parsed_key(kitty.codepoint, kitty.modifier, kitty.base_layout_key)

    modify_other_keys = _parse_modify_other_keys_sequence(data)
    if modify_other_keys:
        return _format_parsed_key(modify_other_keys.codepoint, modify_other_keys.modifier)

    if _kitty_protocol_active and data in {"\x1b\r", "\n"}:
        return "shift+enter"

    legacy_sequence_key_id = LEGACY_SEQUENCE_KEY_IDS.get(data)
    if legacy_sequence_key_id:
        return legacy_sequence_key_id

    if data == "\x1b":
        return "escape"
    if data == "\x1c":
        return "ctrl+\\"
    if data == "\x1d":
        return "ctrl+]"
    if data == "\x1f":
        return "ctrl+-"
    if data == "\x1b\x1b":
        return "ctrl+alt+["
    if data == "\x1b\x1c":
        return "ctrl+alt+\\"
    if data == "\x1b\x1d":
        return "ctrl+alt+]"
    if data == "\x1b\x1f":
        return "ctrl+alt+-"
    if data == "\t":
        return "tab"
    if data == "\r" or (not _kitty_protocol_active and data == "\n") or data == "\x1bOM":
        return "enter"
    if data == "\x00":
        return "ctrl+space"
    if data == " ":
        return "space"
    if data == "\x7f":
        return "backspace"
    if data == "\x08":
        return "ctrl+backspace" if _is_windows_terminal_session() else "backspace"
    if data == "\x1b[Z":
        return "shift+tab"
    if not _kitty_protocol_active and data == "\x1b\r":
        return "alt+enter"
    if not _kitty_protocol_active and data == "\x1b ":
        return "alt+space"
    if data in {"\x1b\x7f", "\x1b\b"}:
        return "alt+backspace"
    if not _kitty_protocol_active and data == "\x1bB":
        return "alt+left"
    if not _kitty_protocol_active and data == "\x1bF":
        return "alt+right"
    if not _kitty_protocol_active and len(data) == 2 and data[0] == "\x1b":
        code = ord(data[1])
        if 1 <= code <= 26:
            return f"ctrl+alt+{chr(code + 96)}"
        if 97 <= code <= 122 or 48 <= code <= 57:
            return f"alt+{chr(code)}"
    if data == "\x1b[A":
        return "up"
    if data == "\x1b[B":
        return "down"
    if data == "\x1b[C":
        return "right"
    if data == "\x1b[D":
        return "left"
    if data in {"\x1b[H", "\x1bOH"}:
        return "home"
    if data in {"\x1b[F", "\x1bOF"}:
        return "end"
    if data == "\x1b[3~":
        return "delete"
    if data == "\x1b[5~":
        return "pageUp"
    if data == "\x1b[6~":
        return "pageDown"

    if len(data) == 1:
        code = ord(data)
        if 1 <= code <= 26:
            return f"ctrl+{chr(code + 96)}"
        if 65 <= code <= 90:
            return f"shift+{data.lower()}"
        if 32 <= code <= 126:
            return data

    return None


def decode_kitty_printable(data: str) -> str | None:
    match = KITTY_CSI_U_REGEX.match(data)
    if not match:
        return None

    codepoint = int(match.group(1))
    shifted_key = int(match.group(2)) if match.group(2) else None
    mod_value = int(match.group(4)) if match.group(4) else 1
    modifier = mod_value - 1

    if modifier & ~KITTY_PRINTABLE_ALLOWED_MODIFIERS:
        return None
    if modifier & (ALT | CTRL):
        return None

    effective_codepoint = codepoint
    if modifier & SHIFT and shifted_key is not None:
        effective_codepoint = shifted_key
    effective_codepoint = _normalize_kitty_functional_codepoint(effective_codepoint)
    if effective_codepoint < 32:
        return None

    try:
        return chr(effective_codepoint)
    except ValueError:
        return None


def _decode_modify_other_keys_printable(data: str) -> str | None:
    parsed = _parse_modify_other_keys_sequence(data)
    if not parsed:
        return None
    modifier = parsed.modifier & ~LOCK_MASK
    if modifier & ~SHIFT:
        return None
    if parsed.codepoint < 32:
        return None
    try:
        return chr(parsed.codepoint)
    except ValueError:
        return None


def decode_printable_key(data: str) -> str | None:
    return decode_kitty_printable(data) or _decode_modify_other_keys_printable(data)
