"""Retrieval backend for the Retrieval (RAG) agent.

Chroma + BM25 + cross-encoder-rerank hybrid retrieval, the same pattern used
for the compliance Q&A assistant. Ingests plain text extracted from
data/raw/regulatory/guidance/ (via scripts/ingest_guidance.py).

Two persistence design notes worth knowing if you're reading this file for
the first time:

1. BM25 has no native on-disk persistence (unlike Chroma's dense index,
   which PersistentClient handles automatically). This module persists the
   tokenized corpus as a small JSON sidecar next to persist_dir and rebuilds
   the in-memory BM25Okapi index from it on __init__ -- cheap (tokenizing
   only), versus re-ingesting from the raw .txt files, which would also
   re-chunk and re-embed everything from scratch.
2. ingest_dir() fully clears and resyncs the Chroma collection on every
   call, rather than relying on upsert()'s ID-based dedup. Chroma's
   upsert() only overwrites a row when the SAME id is reused; random ids
   would mean every re-run duplicates every chunk instead of replacing the
   previous ingest. Since this method already re-reads and re-embeds every
   file on every call (fine at this project's corpus size -- see the TODO
   below), clearing first adds no extra cost and also correctly drops
   chunks for any file removed from guidance_dir since the last ingest.
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

import chromadb
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder

from aml_agents import config
from aml_agents.schemas import RetrievedPassage

_TOKEN_RE = re.compile(r"[A-Za-z0-9']+")


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def _chunk(text: str, chunk_size: int = 800, overlap: int = 120) -> list[str]:
    """Fixed-size chunking with overlap. Returns non-empty, stripped chunks."""

    chunks = []
    step = chunk_size - overlap
    if step <= 0:
        raise ValueError("Chunk size must be greater than overlap size.")

    for i in range(0, len(text), step):
        raw_chunk = text[i : i + chunk_size]
        chunk = raw_chunk.strip()
        if chunk:
            chunks.append(chunk)
        if i + chunk_size >= len(text):
            break

    return chunks


class VectorStore:
    def __init__(self, persist_dir: Path = config.VECTOR_STORE_DIR, collection_name: str = "regulatory_guidance"):
        self._client = chromadb.PersistentClient(path=str(persist_dir))
        self._collection = self._client.get_or_create_collection(collection_name)
        self._cross_encoder: CrossEncoder | None = None
        self._bm25: BM25Okapi | None = None
        self._bm25_docs: list[dict] = []

        # See module docstring, point 1: BM25 isn't natively persisted, so
        # we keep our own small JSON sidecar and rebuild from it here.
        self._bm25_cache_path = Path(persist_dir) / "bm25_docs.json"
        if self._bm25_cache_path.exists():
            self._bm25_docs = json.loads(self._bm25_cache_path.read_text())
            self._bm25 = BM25Okapi([_tokenize(d["text"]) for d in self._bm25_docs])

    # -- ingestion -----------------------------------------------------

    def ingest_dir(self, guidance_dir: Path = config.GUIDANCE_DIR) -> int:
        """Chunk and index every .txt file in guidance_dir. Returns the
        number of chunks indexed. Raises FileNotFoundError if there are no
        .txt files yet.

        TODO: this re-reads, re-chunks and re-embeds every file on every
        call, regardless of whether its content changed -- fine for a
        handful of practice documents, but add a content-hash check before
        doing this against a larger corpus.
        """

        text_files = sorted(Path(guidance_dir).rglob("*.txt"))
        if not text_files:
            raise FileNotFoundError(f"No text files found in {guidance_dir}.")

        # See module docstring, point 2: full resync rather than relying on
        # upsert()'s ID-based dedup, so repeated calls (e.g. every run of
        # scripts/test_case_rag.py) don't duplicate every chunk.
        existing = self._collection.get(include=[])
        if existing["ids"]:
            self._collection.delete(ids=existing["ids"])

        ids, docs, metadatas = [], [], []
        for f in text_files:
            rel_path = str(f.relative_to(guidance_dir))
            for chunk in _chunk(f.read_text(encoding="utf-8", errors="ignore")):
                ids.append(str(uuid.uuid4()))
                docs.append(chunk)
                metadatas.append({"source_document": rel_path})

        self._collection.upsert(ids=ids, documents=docs, metadatas=metadatas)
        self._rebuild_bm25(ids, docs, metadatas)

        return len(ids)

    def _rebuild_bm25(self, ids: list[str], docs: list[str], metadatas: list[dict]) -> None:
        self._bm25_docs = [
            {"id": i, "text": d, "source_document": m["source_document"]} for i, d, m in zip(ids, docs, metadatas)
        ]
        self._bm25 = BM25Okapi([_tokenize(d["text"]) for d in self._bm25_docs])
        self._bm25_cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._bm25_cache_path.write_text(json.dumps(self._bm25_docs))

    # -- query -----------------------------------------------------------

    def query(self, text: str, top_k: int = config.RETRIEVAL_TOP_K) -> list[RetrievedPassage]:
        """Dense search -> sparse search -> reciprocal rank fusion ->
        cross-encoder rerank -> top config.RETRIEVAL_RERANK_TOP_K passages.
        """

        dense = self._dense_search(text, top_k)
        sparse = self._sparse_search(text, top_k)
        fused = self._reciprocal_rank_fusion(dense, sparse)
        reranked = self._rerank(text, fused)

        return reranked

    def _dense_search(self, text: str, top_k: int) -> list[dict]:
        search_results = self._collection.query(query_texts=[text], n_results=top_k)

        return [
            {"id": doc_id, "text": doc, "source_document": metadata["source_document"]}
            for doc_id, doc, metadata in zip(
                search_results["ids"][0], search_results["documents"][0], search_results["metadatas"][0] # type: ignore
            )  
        ]

    def _sparse_search(self, text: str, top_k: int) -> list[dict]:
        if self._bm25 is None:
            return []
        search_scores = self._bm25.get_scores(_tokenize(text))
        top_k_indices = sorted(range(len(search_scores)), key=lambda i: search_scores[i], reverse=True)[:top_k]

        return [self._bm25_docs[i] for i in top_k_indices]

    @staticmethod
    def _reciprocal_rank_fusion(dense: list[dict], sparse: list[dict], k: int = 60) -> list[dict]:
        scores: dict[str, float] = {}
        seen: dict[str, dict] = {}
        for rank_list in (dense, sparse):
            for rank, item in enumerate(rank_list):
                doc_id = item["id"]
                scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
                seen[doc_id] = item
        ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        return [seen[doc_id] for doc_id, _ in ordered]

    def _rerank(self, query: str, candidates: list[dict]) -> list[RetrievedPassage]:
        if not candidates:
            return []
        if self._cross_encoder is None:
            self._cross_encoder = CrossEncoder(config.CROSS_ENCODER_MODEL)
        pairs = [(query, c["text"]) for c in candidates]
        scores = self._cross_encoder.predict(pairs)
        ranked = sorted(zip(candidates, scores), key=lambda cs: cs[1], reverse=True)
        return [
            RetrievedPassage(text=c["text"], source_document=c["source_document"], score=float(s))
            for c, s in ranked
        ][: config.RETRIEVAL_RERANK_TOP_K]