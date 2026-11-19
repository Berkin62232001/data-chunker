import io
from unittest.mock import MagicMock, patch


# ── helpers ───────────────────────────────────────────────────────────────────

def full_pipeline(client, content: bytes, filename: str) -> str:
    r = client.post("/api/files/upload", files={"file": (filename, io.BytesIO(content), "text/plain")})
    assert r.status_code == 200, r.text
    doc_id = r.json()["document_id"]
    assert client.get(f"/api/files/{doc_id}/profile").status_code == 200
    assert client.get(f"/api/files/{doc_id}/pipeline").status_code == 200
    assert client.post(f"/api/files/{doc_id}/convert").status_code == 200
    assert client.post(f"/api/files/{doc_id}/chunk").status_code == 200
    return doc_id


def hybrid(client, doc_id: str, query: str = "topic", top_k: int = 5,
           kw: float = 0.4, sem: float = 0.6):
    return client.post(
        f"/api/files/{doc_id}/hybrid-search",
        json={"query": query, "top_k": top_k, "keyword_weight": kw, "semantic_weight": sem},
    )


_MD = (
    "# Introduction\n\nThis document covers the main topic in detail.\n\n"
    "# Details\n\nMore information about the topic and its implementation.\n"
)


# ── normalize_scores (pure unit tests) ───────────────────────────────────────

def test_normalize_scores_basic():
    from services.hybrid_search_service import normalize_scores
    scores = {"a": 0.0, "b": 0.5, "c": 1.0}
    normed = normalize_scores(scores)
    assert normed["a"] == 0.0
    assert normed["c"] == 1.0
    assert abs(normed["b"] - 0.5) < 1e-9


def test_normalize_scores_single_item():
    from services.hybrid_search_service import normalize_scores
    normed = normalize_scores({"only": 0.42})
    assert normed["only"] == 1.0


def test_normalize_scores_all_equal():
    from services.hybrid_search_service import normalize_scores
    normed = normalize_scores({"a": 3.0, "b": 3.0})
    assert normed["a"] == 1.0
    assert normed["b"] == 1.0


def test_normalize_scores_empty():
    from services.hybrid_search_service import normalize_scores
    assert normalize_scores({}) == {}


def test_normalize_scores_all_zero():
    from services.hybrid_search_service import normalize_scores
    normed = normalize_scores({"a": 0.0, "b": 0.0, "c": 0.0})
    assert all(v == 1.0 for v in normed.values())


# ── _merge (pure unit tests) ──────────────────────────────────────────────────

def test_merge_deduplication():
    from services.hybrid_search_service import _merge
    meta = {"chunk_index": 0, "section_path": [], "content_type": "text",
            "estimated_tokens": 50, "text_preview": "hello"}
    kw = [("c1", 0.8, meta), ("c2", 0.3, meta)]
    sem = [("c1", 0.9, meta), ("c3", 0.7, meta)]
    results = _merge(kw, sem, 0.4, 0.6)
    chunk_ids = [r.chunk_id for r in results]
    assert len(chunk_ids) == len(set(chunk_ids)), "Duplicate chunk_ids after merge"


def test_merge_result_ordering():
    from services.hybrid_search_service import _merge
    meta = {"chunk_index": 0, "section_path": [], "content_type": "text",
            "estimated_tokens": 50, "text_preview": ""}
    # c1: high keyword + high semantic → highest combined
    # c2: low keyword + no semantic
    kw = [("c1", 1.0, meta), ("c2", 0.1, meta)]
    sem = [("c1", 1.0, meta)]
    results = _merge(kw, sem, 0.5, 0.5)
    assert results[0].chunk_id == "c1"


def test_merge_keyword_only_chunk_has_zero_semantic():
    from services.hybrid_search_service import _merge
    meta = {"chunk_index": 0, "section_path": [], "content_type": "text",
            "estimated_tokens": 10, "text_preview": ""}
    kw = [("kw_only", 0.5, meta)]
    sem = []
    results = _merge(kw, sem, 0.5, 0.5)
    assert results[0].semantic_score == 0.0


def test_merge_semantic_only_chunk_has_zero_keyword():
    from services.hybrid_search_service import _merge
    meta = {"chunk_index": 0, "section_path": [], "content_type": "text",
            "estimated_tokens": 10, "text_preview": ""}
    kw = []
    sem = [("sem_only", 0.9, meta)]
    results = _merge(kw, sem, 0.5, 0.5)
    assert results[0].keyword_score == 0.0


def test_merge_combined_score_formula():
    from services.hybrid_search_service import _merge
    meta = {"chunk_index": 0, "section_path": [], "content_type": "text",
            "estimated_tokens": 10, "text_preview": ""}
    # With single items, normalization → 1.0 for both
    kw = [("c1", 0.5, meta)]
    sem = [("c1", 0.9, meta)]
    results = _merge(kw, sem, 0.3, 0.7)
    # combined = 0.3*1.0 + 0.7*1.0 = 1.0
    assert abs(results[0].combined_score - 1.0) < 1e-6


# ── hybrid endpoint — fallback to keyword when Qdrant unavailable ─────────────

def test_hybrid_fallback_returns_200(client):
    doc_id = full_pipeline(client, _MD.encode(), "doc.md")
    r = hybrid(client, doc_id, query="topic")
    assert r.status_code == 200


def test_hybrid_fallback_semantic_unavailable(client):
    doc_id = full_pipeline(client, _MD.encode(), "doc.md")
    r = hybrid(client, doc_id, query="topic")
    assert r.json()["semantic_available"] is False


def test_hybrid_fallback_returns_keyword_results(client):
    doc_id = full_pipeline(client, _MD.encode(), "doc.md")
    r = hybrid(client, doc_id, query="topic")
    assert len(r.json()["results"]) >= 1


def test_hybrid_results_all_have_zero_semantic_score_when_no_index(client):
    doc_id = full_pipeline(client, _MD.encode(), "doc.md")
    r = hybrid(client, doc_id, query="topic")
    for item in r.json()["results"]:
        assert item["semantic_score"] == 0.0


# ── hybrid endpoint — with mocked Qdrant ─────────────────────────────────────

def test_hybrid_with_semantic_results(client, monkeypatch):
    from core.config import settings
    monkeypatch.setattr(settings, "qdrant_url", "http://localhost:6333")

    doc_id = full_pipeline(client, _MD.encode(), "doc.md")

    # Write a fake index_manifest so hybrid knows it's indexed
    manifest = settings.chunks_dir / doc_id / "index_manifest.json"
    manifest.write_text('{"document_id":"x","collection":"c","indexed_chunks":2,'
                        '"embedding_dim":128,"embedding_provider":"mock",'
                        '"indexed_at":"now","qdrant_url":"http://localhost:6333"}')

    sem_hit = MagicMock()
    sem_hit.score = 0.9
    sem_hit.payload = {
        "chunk_id": "sem-chunk-1",
        "chunk_index": 99,
        "section_path": ["Semantic"],
        "content_type": "text",
        "text": "Semantically relevant content about the topic.",
        "estimated_tokens": 60,
    }

    with patch("services.vector_index_service.QdrantClient") as mock_cls:
        mock_cls.return_value.search.return_value = [sem_hit]
        r = hybrid(client, doc_id, query="topic", top_k=5)

    assert r.status_code == 200
    data = r.json()
    assert data["semantic_available"] is True
    # sem-chunk-1 came from semantic only and should appear in results
    sem_ids = [item["chunk_id"] for item in data["results"]]
    assert "sem-chunk-1" in sem_ids


def test_hybrid_merged_chunk_has_both_scores(client, monkeypatch):
    """A chunk found by both keyword and semantic should have non-zero scores for both."""
    from core.config import settings
    monkeypatch.setattr(settings, "qdrant_url", "http://localhost:6333")

    # Use content that keyword search will definitely find
    md = "# Python\n\nPython is a programming language.\n"
    doc_id = full_pipeline(client, md.encode(), "doc.md")

    # Get the real chunk_id from keyword search first
    kw_r = client.post(f"/api/files/{doc_id}/search", json={"query": "python"})
    kw_ids = [r["chunk_id"] for r in kw_r.json()["results"]]
    assert kw_ids, "Expected at least one keyword result"
    shared_chunk_id = kw_ids[0]

    manifest = settings.chunks_dir / doc_id / "index_manifest.json"
    manifest.write_text('{"document_id":"x","collection":"c","indexed_chunks":1,'
                        '"embedding_dim":128,"embedding_provider":"mock",'
                        '"indexed_at":"now","qdrant_url":"http://localhost:6333"}')

    sem_hit = MagicMock()
    sem_hit.score = 0.85
    sem_hit.payload = {
        "chunk_id": shared_chunk_id,
        "chunk_index": 0,
        "section_path": ["Python"],
        "content_type": "text",
        "text": "Python is a programming language.",
        "estimated_tokens": 30,
    }

    with patch("services.vector_index_service.QdrantClient") as mock_cls:
        mock_cls.return_value.search.return_value = [sem_hit]
        r = hybrid(client, doc_id, query="python", top_k=5)

    data = r.json()
    for item in data["results"]:
        if item["chunk_id"] == shared_chunk_id:
            assert item["keyword_score"] > 0.0
            assert item["semantic_score"] > 0.0
            break


# ── response shape ────────────────────────────────────────────────────────────

def test_hybrid_response_shape(client):
    doc_id = full_pipeline(client, _MD.encode(), "doc.md")
    r = hybrid(client, doc_id, query="topic")
    assert r.status_code == 200
    data = r.json()
    for field in ["document_id", "query", "top_k", "keyword_weight",
                  "semantic_weight", "semantic_available", "results", "search_mode"]:
        assert field in data, f"Missing: {field}"
    assert data["search_mode"] == "hybrid"


def test_hybrid_result_item_shape(client):
    doc_id = full_pipeline(client, _MD.encode(), "doc.md")
    r = hybrid(client, doc_id, query="topic")
    results = r.json()["results"]
    if results:
        item = results[0]
        for field in ["chunk_id", "chunk_index", "section_path", "content_type",
                      "combined_score", "keyword_score", "semantic_score",
                      "estimated_tokens", "text_preview"]:
            assert field in item, f"Missing item field: {field}"


def test_hybrid_top_k_respected(client):
    md = "\n\n".join(f"# Topic {i}\n\nContent about topic {i}.\n" for i in range(10))
    doc_id = full_pipeline(client, md.encode(), "doc.md")
    r = hybrid(client, doc_id, query="topic content", top_k=3)
    assert len(r.json()["results"]) <= 3


def test_hybrid_scores_descending(client):
    md = "\n\n".join(f"# Topic {i}\n\nContent about topic {i}.\n" for i in range(8))
    doc_id = full_pipeline(client, md.encode(), "doc.md")
    r = hybrid(client, doc_id, query="topic content", top_k=8)
    scores = [item["combined_score"] for item in r.json()["results"]]
    assert scores == sorted(scores, reverse=True)


def test_hybrid_weights_echoed(client):
    doc_id = full_pipeline(client, _MD.encode(), "doc.md")
    r = hybrid(client, doc_id, query="topic", kw=0.3, sem=0.7)
    data = r.json()
    assert abs(data["keyword_weight"] - 0.3) < 1e-6
    assert abs(data["semantic_weight"] - 0.7) < 1e-6


# ── payload retrieval_mode ────────────────────────────────────────────────────

def test_payload_hybrid_mode_by_default(client):
    doc_id = full_pipeline(client, _MD.encode(), "doc.md")
    r = client.post(
        f"/api/files/{doc_id}/prepare-llm-payload",
        json={"query": "topic"},
    )
    assert r.status_code == 200


def test_payload_keyword_mode_explicit(client):
    doc_id = full_pipeline(client, _MD.encode(), "doc.md")
    r = client.post(
        f"/api/files/{doc_id}/prepare-llm-payload",
        json={"query": "topic", "retrieval_mode": "keyword"},
    )
    assert r.status_code == 200
    assert r.json()["chunks_used"] >= 0


def test_payload_semantic_mode_falls_back_to_keyword(client):
    doc_id = full_pipeline(client, _MD.encode(), "doc.md")
    r = client.post(
        f"/api/files/{doc_id}/prepare-llm-payload",
        json={"query": "topic", "retrieval_mode": "semantic"},
    )
    assert r.status_code == 200


# ── validation ────────────────────────────────────────────────────────────────

def test_hybrid_empty_query_rejected(client):
    r = client.post("/api/files/x/hybrid-search", json={"query": ""})
    assert r.status_code == 422


def test_hybrid_negative_weight_rejected(client):
    r = client.post("/api/files/x/hybrid-search",
                    json={"query": "q", "keyword_weight": -0.1, "semantic_weight": 0.5})
    assert r.status_code == 422


def test_hybrid_both_weights_zero_rejected(client):
    r = client.post("/api/files/x/hybrid-search",
                    json={"query": "q", "keyword_weight": 0.0, "semantic_weight": 0.0})
    assert r.status_code == 422


def test_hybrid_requires_chunks(client):
    r = client.post("/api/files/nonexistent/hybrid-search", json={"query": "q"})
    assert r.status_code == 404
