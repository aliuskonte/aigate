from __future__ import annotations

import re
from dataclasses import dataclass


_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")


@dataclass(frozen=True)
class MarkdownChunk:
    text: str
    section_path: str
    chunk_index: int


def _tokenizer():
    # Approximate tokenization for chunk sizing.
    # We intentionally use cl100k_base for stable sizing across languages.
    import tiktoken

    return tiktoken.get_encoding("cl100k_base")


def _count_tokens(enc, text: str) -> int:
    return len(enc.encode(text or ""))


def _split_markdown_into_sections(md: str) -> list[tuple[str, str]]:
    """
    Return list of (section_path, section_text) where section_text includes markdown lines
    belonging to that section. Code fences are treated as opaque blocks and do not allow
    heading splits inside.
    """

    lines = (md or "").splitlines()
    stack: list[str] = []
    buf: list[str] = []
    sections: list[tuple[str, str]] = []
    in_fence = False

    def flush():
        nonlocal buf
        text = "\n".join(buf).strip()
        if text:
            path = " / ".join(stack) if stack else "(root)"
            sections.append((path, text))
        buf = []

    for line in lines:
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            buf.append(line)
            continue

        m = _HEADING_RE.match(line)
        if m and not in_fence:
            # new section
            flush()
            level = len(m.group(1))
            title = m.group(2).strip()
            # adjust stack to heading level
            while len(stack) >= level:
                stack.pop()
            stack.append(title)
            buf.append(line)
            continue

        buf.append(line)

    flush()
    return sections


def _chunk_section_by_tokens(
    *,
    section_path: str,
    section_text: str,
    max_tokens: int,
    overlap_tokens: int,
    chunk_index_start: int,
) -> list[MarkdownChunk]:
    enc = _tokenizer()
    max_tokens = max(1, int(max_tokens))
    overlap_tokens = max(0, min(int(overlap_tokens), max_tokens - 1))

    # Tokenize whole section once
    tokens = enc.encode(section_text)
    if not tokens:
        return []

    chunks: list[MarkdownChunk] = []
    start = 0
    idx = chunk_index_start
    while start < len(tokens):
        end = min(len(tokens), start + max_tokens)
        text = enc.decode(tokens[start:end]).strip()
        if text:
            chunks.append(MarkdownChunk(text=text, section_path=section_path, chunk_index=idx))
            idx += 1
        if end >= len(tokens):
            break
        start = end - overlap_tokens
    return chunks


def chunk_markdown(
    *,
    text: str,
    max_tokens: int,
    overlap_tokens: int,
    fallback_chunk_size_chars: int,
    fallback_overlap_chars: int,
) -> list[MarkdownChunk]:
    """
    Markdown-aware chunking:
    - split by headings (#..######)
    - do not split on headings inside fenced code blocks
    - then chunk each section by tokens (cl100k_base)
    - fallback to character chunking if tokenization fails
    """

    text = (text or "").strip()
    if not text:
        return []

    try:
        sections = _split_markdown_into_sections(text)
        chunks: list[MarkdownChunk] = []
        next_idx = 0
        for path, sec_text in sections:
            sec_chunks = _chunk_section_by_tokens(
                section_path=path,
                section_text=sec_text,
                max_tokens=max_tokens,
                overlap_tokens=overlap_tokens,
                chunk_index_start=next_idx,
            )
            chunks.extend(sec_chunks)
            next_idx = (chunks[-1].chunk_index + 1) if chunks else next_idx
        return chunks
    except Exception:
        # Fallback to old char-based chunking
        out: list[MarkdownChunk] = []
        for i, ch in enumerate(
            chunk_text(text=text, chunk_size=fallback_chunk_size_chars, overlap=fallback_overlap_chars),
            start=0,
        ):
            out.append(MarkdownChunk(text=ch, section_path="(fallback)", chunk_index=i))
        return out


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

