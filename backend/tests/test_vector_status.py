import io
import json
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


def _mock_qdrant_client():
    mock = MagicMock()
    mock.get_collections.return_value.collections = []
    mock.create_collection.return_value = None
    mock.upsert.return_value = None
    mock.search.return_value = []
    return mock


_SAMPLE_MD = (
    "# Overview\n\nThis document covers the main topic in detail.\n\n"
    "# Implementation\n\nImplementation details are described here.\n"
)


# ── GET /api/vector/status ────────────────────────────────────────────────────

def test_vector_status_qdrant_not_configured(client):
    """QDRANT_URL is None by default in test conftest → configured=false."""
    r = client.get("/api/vector/status")
    assert r.status_code == 200
    data = r.json()
    assert data["qdrant_configured"] is False
    assert data["qdrant_available"] is False
    assert data["collection_name"] == "test_document_chunks"
    assert data["embedding_provider"] == "deterministic_demo"
    assert data["embedding_model"] == "deterministic-demo-128"
    assert data["vector_size"] == 128
    assert data["error"] is not None


def test_vector_status_qdrant_unavailable(client, monkeypatch):
    """QDRANT_URL set but connection fails → configured=true, available=false."""
    from core.config import settings
    monkeypatch.setattr(settings, "qdrant_url", "http://localhost:6333")

    with patch("services.vector_index_service.QdrantClient") as mock_cls:
        mock_cls.return_value.get_collections.side_effect = Exception("Connection refused")
        r = client.get("/api/vector/status")

    assert r.status_code == 200
    data = r.json()
    assert data["qdrant_configured"] is True
    assert data["qdrant_available"] is False
    assert data["embedding_provider"] == "deterministic_demo"
    assert data["error"] is not None
    assert "Connection refused" in data["error"]


def test_vector_status_qdrant_available(client, monkeypatch):
    """QDRANT_URL set and connection works → configured=true, available=true."""
    from core.config import settings
    monkeypatch.setattr(settings, "qdrant_url", "http://localhost:6333")

    with patch("services.vector_index_service.QdrantClient") as mock_cls:
        mock_cls.return_value = _mock_qdrant_client()
        r = client.get("/api/vector/status")

    assert r.status_code == 200
    data = r.json()
    assert data["qdrant_configured"] is True
    assert data["qdrant_available"] is True
    assert data["embedding_provider"] == "deterministic_demo"
    assert data["embedding_model"] == "deterministic-demo-128"
    assert data["vector_size"] == 128
    assert data["error"] is None


def test_vector_status_lm_studio_does_not_expose_api_key(client, monkeypatch):
    from core.config import settings
    monkeypatch.setattr(settings, "embedding_provider", "lm_studio")
    monkeypatch.setattr(settings, "lm_studio_base_url", "http://localhost:1234/v1")
    monkeypatch.setattr(settings, "lm_studio_embedding_model", "local-embed")
    monkeypatch.setattr(settings, "lm_studio_api_key", "super-secret-key")

    r = client.get("/api/vector/status")

    assert r.status_code == 200
    body = r.text
    data = r.json()
    assert data["embedding_provider"] == "lm_studio"
    assert data["embedding_model"] == "local-embed"
    assert data["lm_studio_base_url"] == "http://localhost:1234/v1"
    assert "super-secret-key" not in body


# ── GET /api/files/{document_id}/index-status ─────────────────────────────────

def test_index_status_not_indexed(client):
    """Document exists, not indexed → indexed=false."""
    doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
    r = client.get(f"/api/files/{doc_id}/index-status")
    assert r.status_code == 200
    data = r.json()
    assert data["document_id"] == doc_id
    assert data["indexed"] is False
    assert data["indexed_chunks"] == 0
    assert data["total_chunks"] is not None
    assert data["total_chunks"] > 0
    assert data["embedding_provider"] == "deterministic_demo"
    assert data["embedding_model"] == "deterministic-demo-128"


def test_index_status_indexed(client, monkeypatch):
    """Document indexed → indexed=true with chunk count."""
    from core.config import settings
    monkeypatch.setattr(settings, "qdrant_url", "http://localhost:6333")

    with patch("services.vector_index_service.QdrantClient") as mock_cls:
        mock_cls.return_value = _mock_qdrant_client()
        doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
        idx_resp = client.post(f"/api/files/{doc_id}/index")
        assert idx_resp.status_code == 200

    r = client.get(f"/api/files/{doc_id}/index-status")
    assert r.status_code == 200
    data = r.json()
    assert data["document_id"] == doc_id
    assert data["indexed"] is True
    assert data["indexed_chunks"] > 0
    assert data["total_chunks"] is not None
    assert data["indexed_embedding_provider"] == "deterministic_demo"
    assert data["indexed_embedding_model"] == "deterministic-demo-128"
    assert data["indexed_vector_size"] == 128


def test_index_status_nonexistent_document(client):
    """Non-existent document → indexed=false, total_chunks=null."""
    r = client.get("/api/files/nonexistent-doc/index-status")
    assert r.status_code == 200
    data = r.json()
    assert data["indexed"] is False
    assert data["indexed_chunks"] == 0
    assert data["total_chunks"] is None


# ── Structured error responses ────────────────────────────────────────────────

def test_index_structured_error_not_configured(client):
    """POST /index when QDRANT_URL not set → structured detail dict."""
    doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
    r = client.post(f"/api/files/{doc_id}/index")
    assert r.status_code == 503
    data = r.json()
    detail = data["detail"]
    assert isinstance(detail, dict)
    assert detail["qdrant_configured"] is False
    assert detail["qdrant_available"] is False
    assert "message" in detail


def test_semantic_search_structured_error_not_configured(client):
    """POST /semantic-search when QDRANT_URL not set → structured detail dict."""
    r = client.post("/api/files/fake/semantic-search", json={"query": "test"})
    assert r.status_code == 503
    data = r.json()
    detail = data["detail"]
    assert isinstance(detail, dict)
    assert detail["qdrant_configured"] is False
    assert detail["qdrant_available"] is False


def test_semantic_search_structured_error_not_indexed(client, monkeypatch):
    """POST /semantic-search when document not indexed → structured detail with indexed=false."""
    from core.config import settings
    monkeypatch.setattr(settings, "qdrant_url", "http://localhost:6333")

    doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
    r = client.post(f"/api/files/{doc_id}/semantic-search", json={"query": "topic"})
    assert r.status_code == 404
    data = r.json()
    detail = data["detail"]
    assert isinstance(detail, dict)
    assert detail["qdrant_configured"] is True
    assert detail["indexed"] is False
    assert "not indexed" in detail["message"].lower()
