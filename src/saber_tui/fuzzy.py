from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FuzzyMatch:
    value: str
    score: int
    indices: list[int]


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
