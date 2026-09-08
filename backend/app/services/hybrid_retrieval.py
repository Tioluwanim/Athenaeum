"""
app/services/hybrid_retrieval.py — Hybrid (vector + BM25) retrieval with
cross-encoder reranking.

Why this exists: rag_service.py's FAISS vector search is genuinely good
(multi-query expansion, parallel search, MMR diversity) but purely
semantic search misses exact terms — author surnames, acronyms, specific
figures — that library users type verbatim. This module doesn't replace
rag_service; it wraps it, adding:

  1. BM25Okapi keyword search over the same chunk set (rank_bm25), built
     lazily and cached per document / per library, invalidated by chunk
     count so a re-ingested document rebuilds its BM25 index automatically.
  2. Reciprocal Rank Fusion (RRF) to merge the vector-search ranking and
     the BM25 ranking into one list, weighted by HYBRID_VECTOR_WEIGHT.
  3. Cross-encoder reranking (sentence-transformers CrossEncoder) of the
     fused top-N candidates down to the final top-K — this is the step
     that most reliably improves answer relevance, since it scores
     (query, chunk) pairs jointly instead of comparing independent
     embeddings.

All three steps are deterministic / classical IR, not LLM calls — cheap,
fast, and don't compete with the model providers' rate limits.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Optional

from app.config import TOP_K_RESULTS, SIMILARITY_THRESHOLD
from app.config_ext import HYBRID_VECTOR_WEIGHT, RRF_K
from app.db.repository import repository
from app.models.schemas import SearchResult, TextChunk
from app.services.rag_service import rag_service
from app.utils.cache import make_key, retrieval_cache
from app.utils.logger import get_logger

logger = get_logger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


@dataclass
class _BM25Cache:
    doc_id: str
    chunk_count: int
    index: object          # rank_bm25.BM25Okapi
    chunks: list[TextChunk]


class BM25Index:
    """Tiny wrapper around rank_bm25, cached per doc_id (or 'library')."""

    def __init__(self) -> None:
        self._cache: dict[str, _BM25Cache] = {}

    def _build(self, doc_id: str, chunks: list[TextChunk]):
        from rank_bm25 import BM25Okapi
        tokenized = [_tokenize(c.content) for c in chunks]
        return BM25Okapi(tokenized)

    def get(self, doc_id: str, chunks: list[TextChunk]) -> _BM25Cache:
        cached = self._cache.get(doc_id)
        if cached is not None and cached.chunk_count == len(chunks):
            return cached
        started = time.monotonic()
        index = self._build(doc_id, chunks)
        cached = _BM25Cache(doc_id=doc_id, chunk_count=len(chunks), index=index, chunks=chunks)
        self._cache[doc_id] = cached
        logger.info(
            "BM25 index built for %s — %d chunks in %.1fms",
            doc_id, len(chunks), (time.monotonic() - started) * 1000,
        )
        return cached

    def search(self, doc_id: str, chunks: list[TextChunk], query: str, top_k: int) -> list[tuple[TextChunk, float]]:
        if not chunks:
            return []
        cached = self.get(doc_id, chunks)
        scores = cached.index.get_scores(_tokenize(query))
        ranked = sorted(zip(cached.chunks, scores), key=lambda pair: pair[1], reverse=True)
        return [(chunk, float(score)) for chunk, score in ranked[:top_k] if score > 0]


_bm25 = BM25Index()


class CrossEncoderReranker:
    """Lazily loads a small cross-encoder (ms-marco-MiniLM-L-6-v2, ~80MB,
    CPU-friendly) to jointly score (query, chunk) pairs. Falls back to
    passing candidates through unranked if the model can't load (e.g. no
    internet on first run in an offline LAN deployment) — retrieval still
    works, it just skips the quality boost rather than failing the request.
    """

    def __init__(self) -> None:
        self._model = None
        self._unavailable = False

    def _load(self):
        if self._model is None and not self._unavailable:
            try:
                from sentence_transformers import CrossEncoder
                self._model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
            except Exception as e:  # noqa: BLE001
                logger.warning("CrossEncoder unavailable, reranking disabled: %s", e)
                self._unavailable = True
        return self._model

    def rerank(self, query: str, candidates: list[SearchResult], top_n: int) -> list[SearchResult]:
        if len(candidates) <= 1:
            return candidates[:top_n]
        model = self._load()
        if model is None:
            return candidates[:top_n]

        pairs = [(query, c.chunk.content) for c in candidates]
        scores = model.predict(pairs)
        ordered = [
            c.model_copy(update={"score": round(float(s), 4)})
            for c, s in sorted(zip(candidates, scores), key=lambda p: p[1], reverse=True)
        ]
        for rank, r in enumerate(ordered, start=1):
            r.rank = rank
        return ordered[:top_n]


_reranker = CrossEncoderReranker()


def _reciprocal_rank_fusion(
    vector_results: list[SearchResult],
    bm25_results: list[tuple[TextChunk, float]],
    vector_weight: float = HYBRID_VECTOR_WEIGHT,
    k: int = RRF_K,
) -> list[SearchResult]:
    """Merge two independently-ranked lists into one, weighting each
    result by 1/(k + rank) — RRF is robust to the two scorers having
    incomparable scales (cosine similarity vs BM25 score)."""
    scored: dict[str, float] = {}
    chunk_by_id: dict[str, TextChunk] = {}

    for rank, r in enumerate(vector_results, start=1):
        cid = r.chunk.chunk_id
        chunk_by_id[cid] = r.chunk
        scored[cid] = scored.get(cid, 0.0) + vector_weight * (1.0 / (k + rank))

    for rank, (chunk, _score) in enumerate(bm25_results, start=1):
        cid = chunk.chunk_id
        chunk_by_id[cid] = chunk
        scored[cid] = scored.get(cid, 0.0) + (1.0 - vector_weight) * (1.0 / (k + rank))

    fused = sorted(scored.items(), key=lambda p: p[1], reverse=True)
    return [
        SearchResult(chunk=chunk_by_id[cid], score=round(s, 6), rank=i)
        for i, (cid, s) in enumerate(fused, start=1)
    ]


def _library_chunks_as_text_chunks() -> list[TextChunk]:
    """repository.get_library_chunks() returns ORM (DocumentChunk, Document)
    tuples; BM25 only needs chunk_id + content, but we carry page/section
    through too so citation mapping downstream doesn't need a second query."""
    rows = repository.get_library_chunks()
    out: list[TextChunk] = []
    for chunk, _doc in rows:
        out.append(TextChunk(
            chunk_id=chunk.id,
            doc_id=_doc.doc_id,
            content=chunk.content,
            section_type=chunk.section_type,
            chunk_index=chunk.chunk_index,
            total_chunks=chunk.total_chunks,
            page_number=chunk.page_number,
            word_count=chunk.word_count,
            char_count=chunk.char_count,
        ))
    return out


def hybrid_search(
    query: str,
    doc_id: Optional[str] = None,
    top_k: int = TOP_K_RESULTS,
    rerank: bool = True,
    fetch_k: int = 20,
) -> list[SearchResult]:
    """
    Main entry point. doc_id=None searches the whole library.
    Pipeline: vector search (rag_service, already multi-query+MMR) + BM25
    → reciprocal rank fusion → optional cross-encoder rerank → top_k.
    Cached 3 minutes per (query, doc_id, top_k) — several students often
    ask near-identical questions about the same set-text document.
    """
    from app.utils.logger import ServiceLogger

    cache_key = make_key("hybrid_search", query, doc_id, top_k, rerank, fetch_k)
    cached_result = retrieval_cache.get(cache_key)
    if cached_result is not None:
        return cached_result

    started = time.monotonic()

    if doc_id:
        vector_resp = rag_service.search(doc_id=doc_id, query=query, top_k=fetch_k, threshold=0.0)
        _, all_chunks = rag_service._load_index(doc_id, ServiceLogger("hybrid_retrieval", doc_id=doc_id))
    else:
        vector_resp = rag_service.search_library(query=query, top_k=fetch_k, threshold=0.0)
        all_chunks = _library_chunks_as_text_chunks()

    bm25_key = doc_id or "library"
    try:
        bm25_results = _bm25.search(bm25_key, all_chunks, query, top_k=fetch_k) if all_chunks else []
    except ImportError:
        logger.warning("rank_bm25 not installed — falling back to vector-only search")
        bm25_results = []
    except Exception as e:  # noqa: BLE001
        logger.warning("BM25 search failed, continuing vector-only: %s", e)
        bm25_results = []

    fused = _reciprocal_rank_fusion(vector_resp.results, bm25_results)
    fused = [r for r in fused if r.score >= 0][: fetch_k]

    final = _reranker.rerank(query, fused, top_n=top_k) if rerank else fused[:top_k]

    logger.info(
        "hybrid_search(%s) — vector=%d bm25=%d fused=%d final=%d in %.1fms",
        bm25_key, len(vector_resp.results), len(bm25_results), len(fused), len(final),
        (time.monotonic() - started) * 1000,
    )
    retrieval_cache.set(cache_key, final)
    return final
