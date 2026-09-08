"""
tests/test_v2_rebuild.py — Coverage for the v2 rebuild additions.

The original repo had no test suite at all. These tests cover the new
services added/changed in the rebuild: checksum dedup, citation
extraction, hybrid-retrieval fusion math, and the API surface. They do
NOT re-test pre-existing extraction/embedding internals that weren't
touched by this rebuild.

Run with:  DATABASE_URL="sqlite:////tmp/test_v2.db" pytest tests/test_v2_rebuild.py -v
"""
from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/test_v2_rebuild.db")

import pytest


# ── citation_service ─────────────────────────────────────────────────────

def test_build_citations_picks_relevant_sentence():
    from app.services.citation_service import build_citations
    from app.models.schemas import SearchResult, TextChunk, SectionType

    chunk = TextChunk(
        chunk_id="c1", doc_id="d1", page_number=4, section_type=SectionType.METHODS,
        content="The Kelly Criterion sizes bets based on edge and odds. "
                "It was proposed by John Kelly in 1956.",
    )
    result = SearchResult(chunk=chunk, score=0.9, rank=1)

    citations = build_citations([result], "What is the Kelly Criterion?")

    assert len(citations) == 1
    c = citations[0]
    assert c.citation_id == "[1]"
    assert c.page_number == 4
    assert c.section_type == "methods"
    assert "Kelly Criterion" in c.snippet
    # Must not silently return the whole chunk when one sentence is clearly relevant
    assert c.snippet != chunk.content


def test_format_context_with_markers_includes_page_numbers():
    from app.services.citation_service import build_citations, format_context_with_markers
    from app.models.schemas import SearchResult, TextChunk

    chunk = TextChunk(chunk_id="c1", doc_id="d1", page_number=7, content="Some evidence text here.")
    result = SearchResult(chunk=chunk, score=0.5, rank=1)
    citations = build_citations([result], "evidence")

    block = format_context_with_markers([result], citations)
    assert "[1]" in block
    assert "p.7" in block


# ── hybrid_retrieval: reciprocal rank fusion ────────────────────────────

def test_rrf_favours_results_present_in_both_rankings():
    from app.services.hybrid_retrieval import _reciprocal_rank_fusion
    from app.models.schemas import SearchResult, TextChunk

    c_both = TextChunk(chunk_id="both", doc_id="d", content="in both")
    c_vec_only = TextChunk(chunk_id="vec", doc_id="d", content="vector only")
    c_bm25_only = TextChunk(chunk_id="bm25", doc_id="d", content="bm25 only")

    vector_results = [
        SearchResult(chunk=c_both, score=0.9, rank=1),
        SearchResult(chunk=c_vec_only, score=0.7, rank=2),
    ]
    bm25_results = [(c_both, 5.0), (c_bm25_only, 3.0)]

    fused = _reciprocal_rank_fusion(vector_results, bm25_results)

    assert fused[0].chunk.chunk_id == "both", "chunk ranked well in both lists should win"
    fused_ids = [f.chunk.chunk_id for f in fused]
    assert set(fused_ids) == {"both", "vec", "bm25"}


def test_rrf_handles_empty_bm25_gracefully():
    from app.services.hybrid_retrieval import _reciprocal_rank_fusion
    from app.models.schemas import SearchResult, TextChunk

    chunk = TextChunk(chunk_id="a", doc_id="d", content="x")
    fused = _reciprocal_rank_fusion([SearchResult(chunk=chunk, score=1.0, rank=1)], [])
    assert len(fused) == 1
    assert fused[0].chunk.chunk_id == "a"


# ── storage_service: checksum + local backend ───────────────────────────

def test_storage_service_checksum_is_deterministic():
    from app.services.storage_service import StorageService
    data = b"same bytes twice"
    assert StorageService.compute_checksum(data) == StorageService.compute_checksum(data)
    assert StorageService.compute_checksum(data) != StorageService.compute_checksum(b"different bytes")


def test_storage_service_key_strips_path_components():
    from app.services.storage_service import StorageService
    key = StorageService.build_key("doc123", "../../etc/passwd")
    assert key == "documents/doc123/passwd"


def test_local_backend_put_get_roundtrip(tmp_path):
    from app.services.storage_service import LocalStorageBackend
    backend = LocalStorageBackend(root=tmp_path)
    backend.put("documents/x/file.pdf", b"hello world", "application/pdf")
    assert backend.exists("documents/x/file.pdf")
    assert backend.get("documents/x/file.pdf") == b"hello world"
    assert backend.delete("documents/x/file.pdf") is True
    assert backend.exists("documents/x/file.pdf") is False


def test_local_backend_rejects_path_traversal(tmp_path):
    from app.services.storage_service import LocalStorageBackend
    backend = LocalStorageBackend(root=tmp_path)
    with pytest.raises(ValueError):
        backend.put("../../outside.pdf", b"x", "application/pdf")


# ── repository: checksum dedup against a real (SQLite) DB ───────────────

@pytest.fixture(scope="module")
def db():
    from app.db.repository import init_db
    init_db()


def test_checksum_dedup_roundtrip(db):
    from app.db.repository import repository
    from app.services.pdf_service import pdf_service

    doc, err = pdf_service.save_upload(b"%PDF-1.4 unique test content for dedup", "dedup_test.pdf")
    assert err is None

    ok = repository.set_document_checksum(doc.doc_id, "test-checksum-xyz")
    assert ok is True

    found = repository.get_document_by_checksum("test-checksum-xyz")
    assert found is not None
    assert found.doc_id == doc.doc_id

    assert repository.get_document_by_checksum("does-not-exist") is None

    repository.delete_document(doc.doc_id)


# ── api_main: endpoints with mocked Firebase auth ────────────────────────

@pytest.fixture()
def client(db):
    from fastapi.testclient import TestClient
    import api_main
    from app.auth import CurrentUser, get_current_user, require_admin

    fake_user = CurrentUser(
        id=1, firebase_uid="u1", email="staff@oau.edu.ng",
        full_name="Test Staff", role="admin", email_verified=True,
    )
    api_main.app.dependency_overrides[get_current_user] = lambda: fake_user
    api_main.app.dependency_overrides[require_admin] = lambda: fake_user
    yield TestClient(api_main.app)
    api_main.app.dependency_overrides.clear()


def test_health_endpoint(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "providers" in body


def test_upload_then_list_then_duplicate_detected(client):
    content = b"%PDF-1.4 pytest-unique-content-block"
    r1 = client.post("/api/documents/upload", files=[("files", ("a.pdf", content, "application/pdf"))])
    assert r1.status_code == 200
    body1 = r1.json()[0]
    assert body1["status"] == "processing"
    doc_id = body1["doc_id"]

    r2 = client.get("/api/documents")
    assert r2.status_code == 200
    assert any(d["doc_id"] == doc_id for d in r2.json())

    r3 = client.post("/api/documents/upload", files=[("files", ("a-copy.pdf", content, "application/pdf"))])
    body3 = r3.json()[0]
    assert body3["status"] == "duplicate"
    assert body3["duplicate_of"] == doc_id


def test_unauthenticated_request_rejected():
    from fastapi.testclient import TestClient
    import api_main
    api_main.app.dependency_overrides.clear()
    client = TestClient(api_main.app)
    r = client.get("/api/documents")
    assert r.status_code == 401
