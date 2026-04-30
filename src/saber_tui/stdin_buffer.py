from __future__ import annotations

import re
from collections.abc import Callable

ESC = "\x1b"
BRACKETED_PASTE_START = "\x1b[200~"
BRACKETED_PASTE_END = "\x1b[201~"
_KITTY_PRINTABLE_RE = re.compile(r"^\x1b\[(\d+)(?::\d*)?(?::\d+)?u$")
_SGR_MOUSE_RE = re.compile(r"^<\d+;\d+;\d+[Mm]$")


def _is_complete_csi_sequence(data: str) -> str:
    if not data.startswith(f"{ESC}["):
        return "complete"

    if len(data) < 3:
        return "incomplete"

    payload = data[2:]
    final = payload[-1]
    final_code = ord(final)

    if 0x40 <= final_code <= 0x7E:
        if payload.startswith("<"):
            if _SGR_MOUSE_RE.fullmatch(payload):
                return "complete"

            if final in ("M", "m"):
                parts = payload[1:-1].split(";")
                if len(parts) == 3 and all(part.isdigit() for part in parts):
                    return "complete"
                return "incomplete"

            return "complete"

        return "complete"

    return "incomplete"


def _is_complete_osc_sequence(data: str) -> str:
    if not data.startswith(f"{ESC}]"):
        return "complete"
    return "complete" if data.endswith(f"{ESC}\\") or data.endswith("\x07") else "incomplete"


def _is_complete_dcs_sequence(data: str) -> str:
    if not data.startswith(f"{ESC}P"):
        return "complete"
    return "complete" if data.endswith(f"{ESC}\\") else "incomplete"


def _is_complete_apc_sequence(data: str) -> str:
    if not data.startswith(f"{ESC}_"):
        return "complete"
    return "complete" if data.endswith(f"{ESC}\\") else "incomplete"


def _is_complete_sequence(data: str) -> str:
    if not data.startswith(ESC):
        return "not-escape"

    if len(data) == 1:
        return "incomplete"

    after = data[1:]

    if after.startswith("["):
        if after.startswith("[M"):
            return "complete" if len(data) >= 6 else "incomplete"
        return _is_complete_csi_sequence(data)

    if after.startswith("]"):
        return _is_complete_osc_sequence(data)

    if after.startswith("P"):
        return _is_complete_dcs_sequence(data)

    if after.startswith("_"):
        return _is_complete_apc_sequence(data)

    if after.startswith("O"):
        return "complete" if len(after) >= 2 else "incomplete"

    if len(after) == 1:
        return "complete"

    return "complete"


def _parse_unmodified_kitty_printable_codepoint(sequence: str) -> int | None:
    match = _KITTY_PRINTABLE_RE.fullmatch(sequence)
    if match is None:
        return None

    codepoint = int(match.group(1))
    return codepoint if codepoint >= 32 else None


def _extract_complete_sequences(buffer: str) -> tuple[list[str], str]:
    sequences: list[str] = []
    pos = 0

    while pos < len(buffer):
        remaining = buffer[pos:]

        if remaining.startswith(ESC):
            seq_end = 1
            while seq_end <= len(remaining):
                candidate = remaining[:seq_end]
                status = _is_complete_sequence(candidate)

                if status == "complete":
                    sequences.append(candidate)
                    pos += seq_end
                    break

                if status == "incomplete":
                    seq_end += 1
                    continue

                sequences.append(candidate)
                pos += seq_end
                break

            if seq_end > len(remaining):
                return sequences, remaining
        else:
            sequences.append(remaining[0])
            pos += 1

    return sequences, ""


def _decode_input(data: str | bytes) -> str:
    if isinstance(data, bytes):
        if len(data) == 1 and data[0] > 127:
            return f"{ESC}{chr(data[0] - 128)}"
        return data.decode()

    return data


class StdinBuffer:
    def __init__(
        self,
        *,
        on_data: Callable[[str], None] | None = None,
        on_paste: Callable[[str], None] | None = None,
    ) -> None:
        self._buffer = ""
        self._paste_mode = False
        self._paste_buffer = ""
        self._pending_kitty_printable_codepoint: int | None = None
        self._on_data = on_data
        self._on_paste = on_paste

    def process(self, data: str | bytes) -> None:
        text = _decode_input(data)

        if text == "" and self._buffer == "":
            self._emit_data("")
            return

        self._buffer += text

        if self._paste_mode:
            self._paste_buffer += self._buffer
            self._buffer = ""
            self._finish_paste_if_complete()
            return

        start_index = self._buffer.find(BRACKETED_PASTE_START)
        if start_index != -1:
            if start_index > 0:
                before = self._buffer[:start_index]
                sequences, _ = _extract_complete_sequences(before)
                for sequence in sequences:
                    self._emit_data(sequence)

            self._pending_kitty_printable_codepoint = None
            self._paste_mode = True
            self._paste_buffer = self._buffer[start_index + len(BRACKETED_PASTE_START) :]
            self._buffer = ""
            self._finish_paste_if_complete()
            return

        sequences, remainder = _extract_complete_sequences(self._buffer)
        self._buffer = remainder

        for sequence in sequences:
            self._emit_data(sequence)

    def _finish_paste_if_complete(self) -> None:
        end_index = self._paste_buffer.find(BRACKETED_PASTE_END)
        if end_index == -1:
            return

        content = self._paste_buffer[:end_index]
        remaining = self._paste_buffer[end_index + len(BRACKETED_PASTE_END) :]
        self._paste_buffer = ""
        self._paste_mode = False
        self._pending_kitty_printable_codepoint = None

        if self._on_paste is not None:
            self._on_paste(content)

        if remaining:
            self.process(remaining)

    def _emit_data(self, sequence: str) -> None:
        raw_codepoint = ord(sequence) if len(sequence) == 1 else None
        if raw_codepoint is not None and raw_codepoint == self._pending_kitty_printable_codepoint:
            self._pending_kitty_printable_codepoint = None
            return

        self._pending_kitty_printable_codepoint = _parse_unmodified_kitty_printable_codepoint(sequence)
        if self._on_data is not None:
            self._on_data(sequence)

    def flush(self) -> list[str]:
        if not self._buffer:
            return []

        result = [self._buffer]
        self._buffer = ""
        self._pending_kitty_printable_codepoint = None
        return result

    def clear(self) -> None:
        self._buffer = ""
        self._paste_mode = False
        self._paste_buffer = ""
        self._pending_kitty_printable_codepoint = None

    def get_buffer(self) -> str:
        return self._buffer

    def destroy(self) -> None:
        self.clear()
