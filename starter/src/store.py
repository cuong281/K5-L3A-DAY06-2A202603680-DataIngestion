"""Persist and search chunk vectors in PostgreSQL + pgvector.

Design:
- One table for all strategies; primary key (strategy, chunk_id) makes re-ingestion idempotent.
- ``content_hash`` (text + metadata + model) lets the caller re-embed only changed chunks.
- ``upsert`` also deletes chunks of the same document that no longer exist (changed source).
- Search is EXACT cosine distance (``<=>``) with no ANN index: a few hundred rows per
  strategy, and exact search avoids approximate-index recall loss under metadata filters.
- Filters are restricted to whitelisted columns and always passed as SQL parameters.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from .models import Chunk

TABLE = "day6_chunks"
FILTERABLE = {"article_id", "page", "document_id"}


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{x:.7g}" for x in vector) + "]"


class PgVectorStore:
    def __init__(self, database_url: str, dimensions: int, model_name: str) -> None:
        if not database_url:
            raise ValueError("DATABASE_URL is empty: copy starter/.env.example to starter/.env")
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        self.database_url = database_url
        self.dimensions = dimensions
        self.model_name = model_name

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self.database_url, connect_timeout=5)

    def create_schema(self) -> None:
        with self._connect() as conn:
            conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            conn.execute(sql.SQL("""
                CREATE TABLE IF NOT EXISTS {table} (
                    strategy     text        NOT NULL,
                    chunk_id     text        NOT NULL,
                    document_id  text        NOT NULL,
                    source       text        NOT NULL,
                    page         integer     NOT NULL,
                    article_id   text        NOT NULL,
                    text         text        NOT NULL,
                    metadata     jsonb       NOT NULL,
                    model_name   text        NOT NULL,
                    content_hash text        NOT NULL,
                    embedding    vector({dims}) NOT NULL,
                    updated_at   timestamptz NOT NULL DEFAULT now(),
                    PRIMARY KEY (strategy, chunk_id)
                )""").format(table=sql.Identifier(TABLE), dims=sql.Literal(self.dimensions)))
            conn.execute(sql.SQL("CREATE INDEX IF NOT EXISTS {idx} ON {table} (strategy, article_id)")
                         .format(idx=sql.Identifier(f"{TABLE}_strategy_article"), table=sql.Identifier(TABLE)))
            row = conn.execute(
                "SELECT format_type(atttypid, atttypmod) FROM pg_attribute "
                "WHERE attrelid = %s::regclass AND attname = 'embedding'", (TABLE,)).fetchone()
            if row[0] != f"vector({self.dimensions})":
                raise RuntimeError(f"{TABLE}.embedding is {row[0]}, model produces vector({self.dimensions})")

    def content_hash(self, chunk: Chunk) -> str:
        payload = json.dumps([chunk.text, chunk.source, chunk.page, chunk.metadata, self.model_name],
                             ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def existing_hashes(self, strategy: str) -> dict[str, str]:
        with self._connect() as conn:
            rows = conn.execute(sql.SQL("SELECT chunk_id, content_hash FROM {t} WHERE strategy = %s")
                                .format(t=sql.Identifier(TABLE)), (strategy,)).fetchall()
        return dict(rows)

    def count(self, strategy: str) -> int:
        with self._connect() as conn:
            return conn.execute(sql.SQL("SELECT count(*) FROM {t} WHERE strategy = %s")
                                .format(t=sql.Identifier(TABLE)), (strategy,)).fetchone()[0]

    def upsert(self, strategy: str, chunks: list[Chunk], vectors: list[list[float]],
               keep_ids: set[str] | None = None) -> dict[str, int]:
        """Write ``chunks`` with stable IDs, then delete obsolete chunks of the same documents.

        ``keep_ids`` is the full set of current chunk IDs when only changed chunks are passed;
        it defaults to the IDs of ``chunks``. Returns counts of inserted/updated/deleted rows.
        """
        if len(chunks) != len(vectors):
            raise ValueError(f"{len(chunks)} chunks but {len(vectors)} vectors")
        if any(len(v) != self.dimensions for v in vectors):
            raise ValueError(f"every vector must have {self.dimensions} dimensions")
        ids = [c.chunk_id for c in chunks]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate chunk_id in batch")
        keep = set(ids) if keep_ids is None else set(keep_ids)
        documents = {c.document_id for c in chunks} or {cid.split(":", 1)[0] for cid in keep}
        stats = {"inserted": 0, "updated": 0, "deleted": 0}
        insert = sql.SQL("""
            INSERT INTO {t} (strategy, chunk_id, document_id, source, page, article_id, text,
                             metadata, model_name, content_hash, embedding)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector)
            ON CONFLICT (strategy, chunk_id) DO UPDATE SET
                document_id = EXCLUDED.document_id, source = EXCLUDED.source, page = EXCLUDED.page,
                article_id = EXCLUDED.article_id, text = EXCLUDED.text, metadata = EXCLUDED.metadata,
                model_name = EXCLUDED.model_name, content_hash = EXCLUDED.content_hash,
                embedding = EXCLUDED.embedding, updated_at = now()
            WHERE {t}.content_hash IS DISTINCT FROM EXCLUDED.content_hash
            RETURNING (xmax = 0) AS inserted""").format(t=sql.Identifier(TABLE))
        with self._connect() as conn, conn.transaction():
            for chunk, vector in zip(chunks, vectors):
                row = conn.execute(insert, (
                    strategy, chunk.chunk_id, chunk.document_id, chunk.source, chunk.page,
                    chunk.metadata["article_id"], chunk.text, Jsonb(chunk.metadata), self.model_name,
                    self.content_hash(chunk), _vector_literal(vector))).fetchone()
                if row is not None:
                    stats["inserted" if row[0] else "updated"] += 1
            for document_id in documents:
                deleted = conn.execute(sql.SQL(
                    "DELETE FROM {t} WHERE strategy = %s AND document_id = %s AND NOT (chunk_id = ANY(%s))")
                    .format(t=sql.Identifier(TABLE)), (strategy, document_id, list(keep)))
                stats["deleted"] += deleted.rowcount
        return stats

    def search(self, strategy: str, query_vector: list[float], top_k: int = 3,
               filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Rank by cosine distance; apply whitelisted metadata filters in SQL; return top-k."""
        if len(query_vector) != self.dimensions:
            raise ValueError(f"query vector must have {self.dimensions} dimensions")
        conditions, params = [sql.SQL("strategy = %s")], [strategy]
        for key, value in (filters or {}).items():
            if key not in FILTERABLE:
                raise ValueError(f"filter on {key!r} is not allowed; allowed: {sorted(FILTERABLE)}")
            conditions.append(sql.SQL("{} = %s").format(sql.Identifier(key)))
            params.append(value)
        literal = _vector_literal(query_vector)
        query = sql.SQL("""
            SELECT chunk_id, document_id, source, page, article_id, text, metadata,
                   1 - (embedding <=> %s::vector) AS score
            FROM {t} WHERE {where}
            ORDER BY embedding <=> %s::vector, chunk_id
            LIMIT %s""").format(t=sql.Identifier(TABLE), where=sql.SQL(" AND ").join(conditions))
        with self._connect() as conn:
            rows = conn.execute(query, [literal, *params, literal, top_k]).fetchall()
        keys = ("chunk_id", "document_id", "source", "page", "article_id", "text", "metadata", "score")
        return [dict(zip(keys, row), rank=rank) for rank, row in enumerate(rows, start=1)]
