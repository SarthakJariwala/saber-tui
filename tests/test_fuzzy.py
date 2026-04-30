from saber_tui.fuzzy import fuzzy_filter, fuzzy_match


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
