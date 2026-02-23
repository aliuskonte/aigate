from __future__ import annotations

import re


def hit_at_k(*, expected: set[str], ranked: list[str], k: int) -> int:
    if not expected:
        return 0
    k = max(1, int(k))
    top = ranked[:k]
    return 1 if any(u in expected for u in top) else 0


def recall_at_k(*, expected: set[str], ranked: list[str], k: int) -> float | None:
    if not expected:
        return None
    k = max(1, int(k))
    top = ranked[:k]
    got = sum(1 for u in set(top) if u in expected)
    return got / max(1, len(expected))


def mrr(*, expected: set[str], ranked: list[str]) -> float:
    if not expected:
        return 0.0
    for i, uri in enumerate(ranked, start=1):
        if uri in expected:
            return 1.0 / float(i)
    return 0.0


_CITE_RE = re.compile(r"\[(\d{1,4})\]")


def parse_citations(answer: str) -> list[int]:
    if not answer:
        return []
    out: list[int] = []
    for m in _CITE_RE.finditer(answer):
        try:
            out.append(int(m.group(1)))
        except Exception:
            continue
    return out


def citation_validity(*, citations: list[int], n_sources: int) -> dict[str, int]:
    """
    Validate that citations [N] point to an existing source index (1..n_sources).
    Returns counts to avoid baking policy into the metric.
    """

    n_sources = max(0, int(n_sources))
    invalid_low = 0
    invalid_high = 0
    valid = 0
    for c in citations:
        if c <= 0:
            invalid_low += 1
        elif c > n_sources:
            invalid_high += 1
        else:
            valid += 1
    return {"valid": valid, "invalid_low": invalid_low, "invalid_high": invalid_high}

