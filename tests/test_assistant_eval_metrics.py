from __future__ import annotations

from aigate_assistant.eval.metrics import citation_validity, hit_at_k, mrr, parse_citations, recall_at_k


def test_hit_at_k():
    assert hit_at_k(expected={"a"}, ranked=["b", "a"], k=1) == 0
    assert hit_at_k(expected={"a"}, ranked=["b", "a"], k=2) == 1


def test_recall_at_k():
    assert recall_at_k(expected=set(), ranked=["a"], k=5) is None
    assert recall_at_k(expected={"a", "b"}, ranked=["a", "x", "b"], k=2) == 0.5
    assert recall_at_k(expected={"a", "b"}, ranked=["a", "x", "b"], k=3) == 1.0


def test_mrr():
    assert mrr(expected=set(), ranked=["a"]) == 0.0
    assert mrr(expected={"x"}, ranked=["a", "b"]) == 0.0
    assert mrr(expected={"b"}, ranked=["a", "b"]) == 0.5


def test_parse_citations():
    assert parse_citations("") == []
    assert parse_citations("см. [1] и [2]") == [1, 2]
    assert parse_citations("не число [x]") == []


def test_citation_validity():
    assert citation_validity(citations=[1, 2], n_sources=2) == {
        "valid": 2,
        "invalid_low": 0,
        "invalid_high": 0,
    }
    assert citation_validity(citations=[0, 3], n_sources=2) == {
        "valid": 0,
        "invalid_low": 1,
        "invalid_high": 1,
    }

