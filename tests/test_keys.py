import pytest

from saber_tui.keys import decode_printable_key, is_key_release, matches_key, parse_key, set_kitty_protocol_active


@pytest.fixture(autouse=True)
def restore_kitty_protocol_state() -> None:
    set_kitty_protocol_active(False)
    yield
    set_kitty_protocol_active(False)


def test_matches_legacy_control_and_arrows() -> None:
    assert matches_key("\x03", "ctrl+c")
    assert matches_key("\x1b[A", "up")
    assert matches_key("\x1b[Z", "shift+tab")


def test_parse_key_legacy_sequences() -> None:
    assert parse_key("\x03") == "ctrl+c"
    assert parse_key("\x1b[A") == "up"
    assert parse_key("\r") == "enter"


def test_matches_kitty_csi_u_modified_key() -> None:
    set_kitty_protocol_active(True)
    assert matches_key("\x1b[99;5u", "ctrl+c")


def test_release_detection() -> None:
    assert is_key_release("\x1b[99;5:3u")


def test_decode_printable_key_from_kitty() -> None:
    assert decode_printable_key("\x1b[97u") == "a"
    assert decode_printable_key("\x1b[97;5u") is None


def test_unknown_modifier_segment_does_not_match() -> None:
    assert not matches_key("c", "bogus+c")


def test_parse_uppercase_printable_round_trips() -> None:
    key_id = parse_key("A")

    assert key_id == "shift+a"
    assert matches_key("A", key_id)


def test_parse_modified_escape_round_trips() -> None:
    key_id = parse_key("\x1b[27;3u")

    assert key_id == "alt+escape"
    assert matches_key("\x1b[27;3u", key_id)
