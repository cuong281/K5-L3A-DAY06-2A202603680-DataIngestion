"""Real embedding provider: BAAI/bge-m3 (dense vectors) run locally with sentence-transformers.

No API key, no cost. If the model cannot be loaded the error propagates: there is no
fallback to mock or random vectors. bge-m3 dense retrieval needs no query instruction,
so documents and queries are encoded the same way; vectors are L2-normalized, which makes
cosine distance in pgvector equivalent to the model's similarity.
"""
from __future__ import annotations

from typing import Protocol

MODEL_NAME = "BAAI/bge-m3"
MODEL_REVISION = "5617a9f61b028005a4858fdac845db406aefb181"  # HF snapshot used for all runs
MAX_SEQ_LENGTH = 1024  # chunks are <= 1000 characters, far below this many tokens


class Embedder(Protocol):
    model_name: str
    dimensions: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per input text, in the same order."""
        ...

    def embed_query(self, question: str) -> list[float]:
        """Return a query vector compatible with the stored document vectors."""
        ...


class BgeM3Embedder:
    """sentence-transformers adapter for BAAI/bge-m3 on CPU."""

    def __init__(self, model_name: str = MODEL_NAME, revision: str = MODEL_REVISION,
                 device: str = "cpu", batch_size: int = 16) -> None:
        from sentence_transformers import SentenceTransformer  # heavy import, only when used

        self.model_name = model_name
        self.revision = revision
        self.batch_size = batch_size
        self._model = SentenceTransformer(model_name, revision=revision, device=device)
        self._model.max_seq_length = MAX_SEQ_LENGTH
        get_dim = getattr(self._model, "get_embedding_dimension", None) or self._model.get_sentence_embedding_dimension
        self.dimensions = int(get_dim())

    def _encode(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(texts, batch_size=self.batch_size, normalize_embeddings=True,
                                     convert_to_numpy=True, show_progress_bar=False)
        if vectors.shape != (len(texts), self.dimensions):
            raise RuntimeError(f"unexpected embedding shape {vectors.shape}")
        return vectors.tolist()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._encode(texts) if texts else []

    def embed_query(self, question: str) -> list[float]:
        return self._encode([question])[0]
