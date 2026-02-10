from __future__ import annotations


def compute_stale(db_uris: set[str], current_uris: set[str]) -> set[str]:
    return db_uris - current_uris


def test_compute_stale():
    assert compute_stale({"a.md", "b.md"}, {"b.md", "c.md"}) == {"a.md"}

