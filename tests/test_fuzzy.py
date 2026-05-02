from dataclasses import dataclass

from saber_tui.fuzzy import fuzzy_filter, fuzzy_filter_items, fuzzy_match, fuzzy_match_score


def test_fuzzy_match_scores_ordered_subsequence() -> None:
    match = fuzzy_match("slt", "select-list")

    assert match is not None
    assert match.value == "select-list"
    assert match.indices == [0, 2, 5]
    assert match.score > 0


def test_fuzzy_match_rejects_missing_characters() -> None:
    assert fuzzy_match("xyz", "select-list") is None


def test_fuzzy_filter_orders_better_matches_first() -> None:
    result = fuzzy_filter("sl", ["settings-list", "select-list", "box"])

    assert [item.value for item in result] == ["select-list", "settings-list"]


def test_fuzzy_filter_orders_equal_scores_by_value() -> None:
    result = fuzzy_filter("x", ["bx", "ax"])

    assert [item.value for item in result] == ["ax", "bx"]


@dataclass(frozen=True)
class Command:
    name: str
    label: str


def test_fuzzy_match_score_empty_query_matches_with_zero_score() -> None:
    match = fuzzy_match_score("", "anything")

    assert match.matches is True
    assert match.score == 0


def test_fuzzy_filter_items_returns_original_items_for_empty_query() -> None:
    items = [Command("delete", "Delete"), Command("clear", "Clear")]

    assert fuzzy_filter_items(items, "", lambda item: item.name) == items


def test_fuzzy_filter_items_filters_and_sorts_by_match_quality() -> None:
    items = [Command("src/components/editor.py", "Editor"), Command("docs/editor.md", "Docs")]

    result = fuzzy_filter_items(items, "ed", lambda item: item.name)

    assert [item.name for item in result] == ["docs/editor.md", "src/components/editor.py"]


def test_fuzzy_filter_items_requires_all_space_separated_tokens() -> None:
    items = [
        Command("src/components/editor.py", "Editor"),
        Command("src/components/input.py", "Input"),
        Command("tests/test_editor.py", "Editor tests"),
    ]

    result = fuzzy_filter_items(items, "src ed", lambda item: item.name)

    assert [item.name for item in result] == ["src/components/editor.py"]


def test_fuzzy_match_score_matches_swapped_alpha_numeric_tokens() -> None:
    match = fuzzy_match_score("abc123", "123abc")

    assert match.matches is True
