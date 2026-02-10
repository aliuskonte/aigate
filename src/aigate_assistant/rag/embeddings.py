from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from fastembed import TextEmbedding


@dataclass(frozen=True)
class EmbeddingResult:
    vectors: list[list[float]]
    dim: int


class Embedder:
    def __init__(self, *, model_name: str):
        self._model_name = model_name
        self._embedder = TextEmbedding(model_name=model_name)

    @property
    def model_name(self) -> str:
        return self._model_name

    def embed_texts(self, texts: Iterable[str]) -> EmbeddingResult:
        vectors: list[list[float]] = []
        for v in self._embedder.embed(list(texts)):
            vec = list(map(float, v))
            vectors.append(vec)
        dim = len(vectors[0]) if vectors else 0
        return EmbeddingResult(vectors=vectors, dim=dim)

    def embed_query(self, text: str) -> list[float]:
        res = self.embed_texts([text])
        return res.vectors[0] if res.vectors else []

