from __future__ import annotations

from aigate_assistant.rag.chunking import chunk_markdown


def test_chunk_markdown_respects_code_fences_for_heading_splits():
    md = """
# Title

Intro.

```python
# not a heading, inside code fence
def f():
    pass
```

## Real Heading
Text after.
""".strip()

    chunks = chunk_markdown(
        text=md,
        max_tokens=120,
        overlap_tokens=10,
        fallback_chunk_size_chars=500,
        fallback_overlap_chars=50,
    )

    assert chunks, "expected non-empty chunks"
    # Ensure we have both sections represented in section_path
    paths = {c.section_path for c in chunks}
    assert "Title" in " / ".join(sorted(paths))
    assert "Real Heading" in " / ".join(sorted(paths))


def test_chunk_markdown_includes_section_path_and_indexes():
    md = """
# A
one

## B
two
""".strip()

    chunks = chunk_markdown(
        text=md,
        max_tokens=64,
        overlap_tokens=8,
        fallback_chunk_size_chars=200,
        fallback_overlap_chars=20,
    )

    assert all(c.section_path for c in chunks)
    assert chunks[0].chunk_index == 0
    assert all(chunks[i].chunk_index == i for i in range(len(chunks)))

