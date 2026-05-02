from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class FuzzyMatch:
    value: str
    score: int
    indices: list[int]


@dataclass(frozen=True)
class FuzzyScore:
    matches: bool
    score: float


def fuzzy_match(query: str, value: str) -> FuzzyMatch | None:
    if query == "":
        return FuzzyMatch(value=value, score=0, indices=[])

    q = query.lower()
    v = value.lower()
    indices: list[int] = []
    search_from = 0
    for char in q:
        index = v.find(char, search_from)
        if index == -1:
            return None
        indices.append(index)
        search_from = index + 1

    score = 1000
    score -= indices[0] * 10
    score -= (indices[-1] - indices[0] + 1 - len(indices)) * 5
    for previous, current in zip(indices, indices[1:], strict=False):
        if current == previous + 1:
            score += 20
    if value[indices[0]].isupper() or indices[0] == 0:
        score += 10
    return FuzzyMatch(value=value, score=score, indices=indices)


def fuzzy_filter(query: str, values: list[str]) -> list[FuzzyMatch]:
    matches = [match for value in values if (match := fuzzy_match(query, value)) is not None]
    return sorted(matches, key=lambda match: (-match.score, match.value))


def fuzzy_match_score(query: str, text: str) -> FuzzyScore:
    query_lower = query.lower()
    text_lower = text.lower()

    def match_query(normalized_query: str) -> FuzzyScore:
        if normalized_query == "":
            return FuzzyScore(True, 0)
        if len(normalized_query) > len(text_lower):
            return FuzzyScore(False, 0)

        query_index = 0
        score = 0.0
        last_match_index = -1
        consecutive_matches = 0

        for index, char in enumerate(text_lower):
            if query_index >= len(normalized_query):
                break
            if char != normalized_query[query_index]:
                continue

            is_word_boundary = index == 0 or text_lower[index - 1] in " \t-_./:"
            if last_match_index == index - 1:
                consecutive_matches += 1
                score -= consecutive_matches * 5
            else:
                consecutive_matches = 0
                if last_match_index >= 0:
                    score += (index - last_match_index - 1) * 2
            if is_word_boundary:
                score -= 10
            score += index * 0.1
            last_match_index = index
            query_index += 1

        if query_index < len(normalized_query):
            return FuzzyScore(False, 0)
        return FuzzyScore(True, score)

    primary_match = match_query(query_lower)
    if primary_match.matches:
        return primary_match

    alpha_numeric = re.fullmatch(r"(?P<letters>[a-z]+)(?P<digits>[0-9]+)", query_lower)
    numeric_alpha = re.fullmatch(r"(?P<digits>[0-9]+)(?P<letters>[a-z]+)", query_lower)
    swapped_query = ""
    if alpha_numeric is not None:
        swapped_query = f"{alpha_numeric.group('digits')}{alpha_numeric.group('letters')}"
    elif numeric_alpha is not None:
        swapped_query = f"{numeric_alpha.group('letters')}{numeric_alpha.group('digits')}"

    if not swapped_query:
        return primary_match

    swapped_match = match_query(swapped_query)
    if not swapped_match.matches:
        return primary_match
    return FuzzyScore(True, swapped_match.score + 5)


def fuzzy_filter_items(  # noqa: UP047
    items: Sequence[T], query: str, get_text: Callable[[T], str]
) -> list[T]:
    if not query.strip():
        return list(items)

    tokens = [token for token in query.strip().split() if token]
    if not tokens:
        return list(items)

    results: list[tuple[T, float]] = []
    for item in items:
        total_score = 0.0
        for token in tokens:
            match = fuzzy_match_score(token, get_text(item))
            if not match.matches:
                break
            total_score += match.score
        else:
            results.append((item, total_score))

    results.sort(key=lambda result: result[1])
    return [item for item, _ in results]
