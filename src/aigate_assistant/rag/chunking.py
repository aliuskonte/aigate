from __future__ import annotations


def chunk_text(*, text: str, chunk_size: int, overlap: int) -> list[str]:
    """
    Simple character-based chunking for MVP.

    - chunk_size: number of chars per chunk
    - overlap: number of chars overlapped between chunks
    """

    text = (text or "").strip()
    if not text:
        return []
    if chunk_size <= 0:
        return [text]

    overlap = max(0, min(overlap, chunk_size - 1)) if chunk_size > 1 else 0

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + chunk_size)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = end - overlap
    return chunks

