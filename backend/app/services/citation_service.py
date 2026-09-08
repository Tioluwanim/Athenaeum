"""
app/services/citation_service.py — Evidence extraction & citation mapping.

Deliberately NOT an LLM call. A citation's job is to be exactly right —
correct doc_id, correct page number, the exact sentence that supports a
claim — so it's built deterministically from data we already have on
every chunk (page_number, section_type, char offsets) rather than asked
of a model that could hallucinate a page number.

This is what powers "click citation → exact PDF page + highlight" in the
frontend: each Citation carries enough to jump the PDF viewer straight to
(doc_id, page_number) and highlight `snippet` on that page.
"""
from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel

from app.models.schemas import SearchResult


class Citation(BaseModel):
    citation_id: str        # short id used inline in the answer, e.g. "[1]"
    doc_id: str
    filename: str = ""
    chunk_id: str
    page_number: int
    section_type: str
    snippet: str             # the evidence sentence(s), trimmed for display
    score: float


def _best_sentence(chunk_content: str, query_terms: set[str], max_len: int = 320) -> str:
    """Pick the sentence(s) within a chunk most likely to be the actual
    evidence for the query, rather than dumping the whole chunk as the
    'snippet' shown next to a citation. Falls back to a leading excerpt
    if no sentence scores well."""
    sentences = re.split(r"(?<=[.!?])\s+", chunk_content.strip())
    if not sentences:
        return chunk_content[:max_len]

    def score(sentence: str) -> int:
        words = set(w.lower() for w in re.findall(r"[a-zA-Z0-9]+", sentence))
        return len(words & query_terms)

    ranked = sorted(sentences, key=score, reverse=True)
    best = ranked[0] if ranked and score(ranked[0]) > 0 else sentences[0]

    if len(best) > max_len:
        best = best[: max_len - 1].rsplit(" ", 1)[0] + "…"
    return best.strip()


def build_citations(
    results: list[SearchResult],
    query: str,
    filenames_by_doc_id: Optional[dict[str, str]] = None,
) -> list[Citation]:
    """Turn ranked retrieval results into numbered, page-accurate citations."""
    query_terms = set(re.findall(r"[a-zA-Z0-9]+", query.lower()))
    filenames_by_doc_id = filenames_by_doc_id or {}
    citations: list[Citation] = []

    for i, r in enumerate(results, start=1):
        chunk = r.chunk
        citations.append(Citation(
            citation_id=f"[{i}]",
            doc_id=chunk.doc_id,
            filename=filenames_by_doc_id.get(chunk.doc_id, ""),
            chunk_id=chunk.chunk_id,
            page_number=chunk.page_number,
            section_type=chunk.section_type.value if hasattr(chunk.section_type, "value") else str(chunk.section_type),
            snippet=_best_sentence(chunk.content, query_terms),
            score=r.score,
        ))
    return citations


def format_context_with_markers(results: list[SearchResult], citations: list[Citation]) -> str:
    """Builds the context block sent to the LLM, with inline [n] markers
    matching each Citation so the model can (and is instructed to) cite
    inline — e.g. 'Findings show X [2].' — instead of inventing sources."""
    parts = []
    for r, c in zip(results, citations):
        parts.append(f"{c.citation_id} (p.{c.page_number}, {c.section_type}):\n{r.chunk.content}")
    return "\n\n".join(parts)
