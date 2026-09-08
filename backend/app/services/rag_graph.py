"""
app/services/rag_graph.py — Research orchestration graph (the "brain").

    rewrite_query → retrieve (hybrid) → grade_relevance → generate → cite
                          ↑_________________________|
                     (loop once if grading fails)

Deliberately a SINGLE graph, not a multi-agent system. Multi-agent
orchestration earns its complexity when sub-tasks genuinely need
independent tool access, memory, or planning loops that would tangle a
linear pipeline (e.g. a literature-review agent that itself spawns
per-paper summarizer agents). A "search my library and answer with
citations" flow doesn't — it's a linear pipeline with two quality gates
(relevance grading, and letting a bad retrieval retry once with a
rewritten query). Bolting a planner/critic/executor agent trio onto this
would add latency and failure surface without improving the answer.

Every LLM call goes through ModelRouter (Groq → OpenRouter → HuggingFace),
never a single hardcoded provider — model_router.py owns that fallback.
"""
from __future__ import annotations

import time
from typing import Optional, TypedDict

from app.config import TOP_K_RESULTS
from app.config_ext import RETRIEVAL_GRADE_ENABLED, RETRIEVAL_MAX_RETRIES
from app.models.schemas import SearchResult
from app.services.citation_service import Citation, build_citations, format_context_with_markers
from app.services.hybrid_retrieval import hybrid_search
from app.services.model_router import model_router
from app.utils.logger import get_logger

logger = get_logger(__name__)

_SYSTEM_PROMPT = (
    "You are a research assistant helping students and librarians get accurate, "
    "well-cited answers from a document library.\n\n"
    "Rules:\n"
    "- Answer ONLY using the numbered context excerpts provided.\n"
    "- Cite claims inline using the excerpt's marker, e.g. 'Findings show X [2].'\n"
    "- If the context is insufficient to answer, say so plainly — never invent facts, "
    "page numbers, or sources not present in the context.\n"
    "- Be concise but complete; prefer the shortest answer that fully addresses the question.\n"
    "- If excerpts disagree, note the discrepancy rather than silently picking one.\n"
)


class ResearchState(TypedDict, total=False):
    query: str
    doc_id: Optional[str]
    rewritten_query: str
    results: list[SearchResult]
    citations: list[Citation]
    context: str
    relevant: bool
    retries: int
    answer: str
    provider_used: str
    timings_ms: dict[str, int]


async def _node_rewrite_query(state: ResearchState) -> ResearchState:
    started = time.monotonic()
    try:
        resp = await model_router.complete(
            fast=True,
            messages=[
                {"role": "system", "content": (
                    "Rewrite the user's question into a short, specific search query "
                    "for a document search engine. Expand acronyms if obvious. "
                    "Return ONLY the rewritten query, nothing else."
                )},
                {"role": "user", "content": state["query"]},
            ],
            max_tokens=60,
        )
        rewritten = resp.text.strip().strip('"') or state["query"]
    except Exception as e:  # noqa: BLE001
        logger.warning("Query rewrite failed, using original query: %s", e)
        rewritten = state["query"]

    state["rewritten_query"] = rewritten
    state.setdefault("timings_ms", {})["rewrite"] = int((time.monotonic() - started) * 1000)
    return state


def _node_retrieve(state: ResearchState) -> ResearchState:
    started = time.monotonic()
    results = hybrid_search(
        query=state["rewritten_query"], doc_id=state.get("doc_id"), top_k=TOP_K_RESULTS,
    )
    state["results"] = results
    state["context"] = "\n\n".join(r.chunk.content for r in results)
    state.setdefault("timings_ms", {})["retrieve"] = int((time.monotonic() - started) * 1000)
    return state


async def _node_grade_relevance(state: ResearchState) -> ResearchState:
    if not RETRIEVAL_GRADE_ENABLED or not state["results"]:
        state["relevant"] = bool(state["results"])
        return state

    started = time.monotonic()
    preview = state["context"][:2000]
    try:
        resp = await model_router.complete(
            fast=True,
            messages=[
                {"role": "system", "content": (
                    "You grade whether search results are relevant to a question. "
                    "Reply with exactly one word: YES or NO."
                )},
                {"role": "user", "content": f"Question: {state['query']}\n\nResults:\n{preview}"},
            ],
            max_tokens=5,
        )
        state["relevant"] = resp.text.strip().upper().startswith("Y")
    except Exception as e:  # noqa: BLE001
        logger.warning("Relevance grading failed, assuming relevant: %s", e)
        state["relevant"] = True

    state.setdefault("timings_ms", {})["grade"] = int((time.monotonic() - started) * 1000)
    return state


async def _node_generate(state: ResearchState) -> ResearchState:
    started = time.monotonic()
    filenames_by_doc_id: dict[str, str] = {}
    citations = build_citations(state["results"], state["query"], filenames_by_doc_id)
    context_block = format_context_with_markers(state["results"], citations)

    if not state["results"]:
        state["answer"] = (
            "I couldn't find anything in the library relevant to that question. "
            "Try rephrasing, or check whether the document has been uploaded and processed yet."
        )
        state["citations"] = []
        state["provider_used"] = "none"
        return state

    try:
        resp = await model_router.complete(
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": f"Context:\n{context_block}\n\nQuestion: {state['query']}"},
            ],
        )
        state["answer"] = resp.text
        state["provider_used"] = resp.provider
    except Exception as e:  # noqa: BLE001
        logger.error("Generation failed on all providers: %s", e)
        state["answer"] = (
            "I found relevant material but couldn't generate an answer right now — "
            "the AI providers are unavailable. Please try again shortly."
        )
        state["provider_used"] = "none"

    state["citations"] = citations
    state.setdefault("timings_ms", {})["generate"] = int((time.monotonic() - started) * 1000)
    return state


async def run_research(query: str, doc_id: Optional[str] = None) -> ResearchState:
    """Runs the graph. Implemented as a plain async function rather than
    a compiled langgraph.StateGraph when langgraph isn't installed, so the
    pipeline degrades gracefully; the compiled-graph path (below) is used
    when the dependency is present, giving checkpointing for free."""
    state: ResearchState = {"query": query, "doc_id": doc_id, "retries": 0}

    state = await _node_rewrite_query(state)
    state = _node_retrieve(state)
    state = await _node_grade_relevance(state)

    if not state["relevant"] and state["retries"] < RETRIEVAL_MAX_RETRIES:
        logger.info("Retrieval graded not-relevant, retrying once with broader query")
        state["retries"] += 1
        state["rewritten_query"] = state["query"]  # fall back to the raw query on retry
        state = _node_retrieve(state)

    state = await _node_generate(state)
    return state


def build_compiled_graph():
    """Optional: compile an actual langgraph.StateGraph with a checkpointer
    for production use (gives resumable/inspectable runs). Falls back to
    the plain async pipeline above if langgraph isn't installed — callers
    should use `run_research()` directly unless they need checkpointing."""
    try:
        from langgraph.graph import StateGraph, END
    except ImportError:
        logger.info("langgraph not installed — using plain async pipeline (functionally identical)")
        return None

    graph = StateGraph(ResearchState)
    graph.add_node("rewrite_query", _node_rewrite_query)
    graph.add_node("retrieve", _node_retrieve)
    graph.add_node("grade_relevance", _node_grade_relevance)
    graph.add_node("generate", _node_generate)

    graph.set_entry_point("rewrite_query")
    graph.add_edge("rewrite_query", "retrieve")
    graph.add_edge("retrieve", "grade_relevance")

    def _route_after_grade(state: ResearchState) -> str:
        if not state["relevant"] and state.get("retries", 0) < RETRIEVAL_MAX_RETRIES:
            state["retries"] = state.get("retries", 0) + 1
            return "retrieve"
        return "generate"

    graph.add_conditional_edges("grade_relevance", _route_after_grade, {"retrieve": "retrieve", "generate": "generate"})
    graph.add_edge("generate", END)

    return graph.compile()
