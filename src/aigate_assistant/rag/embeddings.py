from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from fastembed import TextEmbedding


@dataclass(frozen=True)
class EmbeddingResult:
    vectors: list[list[float]]
    dim: int


def format_for_embedding(*, text: str, kind: str, model_name: str) -> str:
    """
    Apply model-specific prefixes when required.

    kind:
      - "query"
      - "document"
    """

    text = (text or "").strip()
    mn = (model_name or "").lower()
    if not text:
        return ""

    # E5 family expects explicit prefixes for best quality.
    # (e.g. "query: ..." and "passage: ...")
    if "e5" in mn:
        if kind == "query":
            return f"query: {text}"
        return f"passage: {text}"

    return text


class Embedder:
    def __init__(self, *, model_name: str):
        self._model_name = model_name
        self._embedder = TextEmbedding(model_name=model_name)

    @property
    def model_name(self) -> str:
        return self._model_name

    def embed_documents(self, texts: Iterable[str]) -> EmbeddingResult:
        prepared = [
            format_for_embedding(text=t, kind="document", model_name=self._model_name) for t in texts
        ]
        return self._embed_prepared(prepared)

    def embed_texts(self, texts: Iterable[str]) -> EmbeddingResult:
        # Back-compat: treat as documents.
        return self.embed_documents(texts)

    def _embed_prepared(self, prepared_texts: list[str]) -> EmbeddingResult:
        vectors: list[list[float]] = []
        for v in self._embedder.embed(prepared_texts):
            vec = list(map(float, v))
            vectors.append(vec)
        dim = len(vectors[0]) if vectors else 0
        return EmbeddingResult(vectors=vectors, dim=dim)

    def embed_query(self, text: str) -> list[float]:
        prepared = format_for_embedding(text=text, kind="query", model_name=self._model_name)
        res = self._embed_prepared([prepared])
        return res.vectors[0] if res.vectors else []

