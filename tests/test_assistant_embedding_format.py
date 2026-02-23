from __future__ import annotations

from aigate_assistant.rag.embeddings import format_for_embedding


def test_format_for_embedding_e5_prefixes():
    model = "intfloat/multilingual-e5-large"
    assert format_for_embedding(text="hello", kind="query", model_name=model) == "query: hello"
    assert format_for_embedding(text="hello", kind="document", model_name=model) == "passage: hello"


def test_format_for_embedding_non_e5_no_prefix():
    model = "sentence-transformers/all-MiniLM-L6-v2"
    assert format_for_embedding(text="hello", kind="query", model_name=model) == "hello"
    assert format_for_embedding(text="hello", kind="document", model_name=model) == "hello"

