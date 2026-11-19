import io
import json
import math
from types import SimpleNamespace
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


# ── MockEmbeddingService ──────────────────────────────────────────────────────

def test_mock_embedding_returns_correct_dim():
    from services.embedding.mock_embedding import MockEmbeddingService
    svc = MockEmbeddingService(dim=64)
    vec = svc.embed("hello world")
    assert len(vec) == 64
    assert svc.provider_name == "deterministic_demo"
    assert svc.model_name == "deterministic-demo-64"


def test_mock_embedding_deterministic():
    from services.embedding.mock_embedding import MockEmbeddingService
    svc = MockEmbeddingService()
    assert svc.embed("same text") == svc.embed("same text")


def test_mock_embedding_different_texts_differ():
    from services.embedding.mock_embedding import MockEmbeddingService
    svc = MockEmbeddingService()
    assert svc.embed("text A") != svc.embed("text B")


def test_mock_embedding_unit_vector():
    from services.embedding.mock_embedding import MockEmbeddingService
    svc = MockEmbeddingService(dim=64)
    vec = svc.embed("normalise me")
    magnitude = math.sqrt(sum(x * x for x in vec))
    assert abs(magnitude - 1.0) < 1e-6


def test_mock_embedding_all_finite():
    from services.embedding.mock_embedding import MockEmbeddingService
    svc = MockEmbeddingService()
    vec = svc.embed("edge case text")
    assert all(math.isfinite(v) for v in vec)


def test_mock_embedding_batch():
    from services.embedding.mock_embedding import MockEmbeddingService
    svc = MockEmbeddingService(dim=32)
    batch = svc.embed_batch(["a", "b", "c"])
    assert len(batch) == 3
    assert all(len(v) == 32 for v in batch)


def test_qdrant_collection_name_env_alias(monkeypatch):
    from core.config import Settings
    monkeypatch.setenv("QDRANT_COLLECTION_NAME", "custom_chunks")
    cfg = Settings()
    assert cfg.qdrant_collection == "custom_chunks"


# ── Qdrant not configured ─────────────────────────────────────────────────────

def test_index_qdrant_not_configured(client):
    md = b"# Test\n\nContent.\n"
    r = client.post("/api/files/upload", files={"file": ("doc.md", io.BytesIO(md), "text/plain")})
    doc_id = r.json()["document_id"]
    assert client.get(f"/api/files/{doc_id}/profile").status_code == 200
    assert client.get(f"/api/files/{doc_id}/pipeline").status_code == 200
    assert client.post(f"/api/files/{doc_id}/convert").status_code == 200
    assert client.post(f"/api/files/{doc_id}/chunk").status_code == 200
    r2 = client.post(f"/api/files/{doc_id}/index")
    assert r2.status_code == 503
    detail = r2.json()["detail"]
    assert isinstance(detail, dict)
    assert detail["qdrant_configured"] is False


def test_semantic_search_qdrant_not_configured(client):
    r = client.post(
        "/api/files/fake-id/semantic-search",
        json={"query": "test"},
    )
    assert r.status_code == 503
    detail = r.json()["detail"]
    assert isinstance(detail, dict)
    assert detail["qdrant_configured"] is False


# ── index endpoint ────────────────────────────────────────────────────────────

def test_index_requires_chunks(client, monkeypatch):
    from core.config import settings
    monkeypatch.setattr(settings, "qdrant_url", "http://localhost:6333")
    r = client.post("/api/files/nonexistent/index")
    assert r.status_code == 404


def test_index_response_shape(client, monkeypatch):
    from core.config import settings
    monkeypatch.setattr(settings, "qdrant_url", "http://localhost:6333")

    with patch("services.vector_index_service.QdrantClient") as mock_cls:
        mock_cls.return_value = _mock_qdrant_client()
        doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
        r = client.post(f"/api/files/{doc_id}/index")

    assert r.status_code == 200
    data = r.json()
    for field in [
        "document_id", "qdrant_configured", "collection_name", "indexed_chunks",
        "collection", "vector_size", "embedding_provider", "embedding_model",
        "status", "manifest_path",
    ]:
        assert field in data, f"Missing: {field}"
    assert data["document_id"] == doc_id
    assert data["qdrant_configured"] is True
    assert data["collection_name"] == "test_document_chunks"
    assert data["status"] == "indexed"
    assert data["vector_size"] == 128
    assert data["embedding_provider"] == "deterministic_demo"
    assert data["embedding_model"] == "deterministic-demo-128"
    assert data["indexed_chunks"] > 0


def test_index_creates_manifest(client, monkeypatch):
    from core.config import settings
    monkeypatch.setattr(settings, "qdrant_url", "http://localhost:6333")

    with patch("services.vector_index_service.QdrantClient") as mock_cls:
        mock_cls.return_value = _mock_qdrant_client()
        doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
        client.post(f"/api/files/{doc_id}/index")

    manifest_path = settings.chunks_dir / doc_id / "index_manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text())
    assert manifest["document_id"] == doc_id
    assert manifest["indexed_chunks"] > 0
    assert manifest["embedding_provider"] == "deterministic_demo"
    assert manifest["embedding_model"] == "deterministic-demo-128"
    assert "collection" in manifest
    assert "indexed_at" in manifest


def test_index_calls_upsert(client, monkeypatch):
    from core.config import settings
    monkeypatch.setattr(settings, "qdrant_url", "http://localhost:6333")

    with patch("services.vector_index_service.QdrantClient") as mock_cls:
        mock_client = _mock_qdrant_client()
        mock_cls.return_value = mock_client
        doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
        client.post(f"/api/files/{doc_id}/index")

    mock_client.upsert.assert_called_once()
    call_kwargs = mock_client.upsert.call_args.kwargs
    assert call_kwargs["collection_name"] == "test_document_chunks"
    assert len(call_kwargs["points"]) > 0
    payload = call_kwargs["points"][0].payload
    assert "text" not in payload
    assert "text_preview" in payload
    assert "raw_path" not in payload
    assert "file_path" not in payload
    assert "absolute_path" not in payload


def test_index_creates_collection_when_missing(client, monkeypatch):
    from core.config import settings
    monkeypatch.setattr(settings, "qdrant_url", "http://localhost:6333")

    with patch("services.vector_index_service.QdrantClient") as mock_cls:
        mock_client = _mock_qdrant_client()
        mock_cls.return_value = mock_client
        doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
        client.post(f"/api/files/{doc_id}/index")

    mock_client.create_collection.assert_called_once()


def test_index_skips_collection_creation_when_exists(client, monkeypatch):
    from core.config import settings
    monkeypatch.setattr(settings, "qdrant_url", "http://localhost:6333")

    with patch("services.vector_index_service.QdrantClient") as mock_cls:
        mock_client = _mock_qdrant_client()
        existing = MagicMock()
        existing.name = "test_document_chunks"
        mock_client.get_collections.return_value.collections = [existing]
        mock_cls.return_value = mock_client
        doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
        client.post(f"/api/files/{doc_id}/index")

    mock_client.create_collection.assert_not_called()


def test_index_rejects_existing_collection_dimension_mismatch(client, monkeypatch):
    from core.config import settings
    monkeypatch.setattr(settings, "qdrant_url", "http://localhost:6333")

    with patch("services.vector_index_service.QdrantClient") as mock_cls:
        mock_client = _mock_qdrant_client()
        existing = MagicMock()
        existing.name = "test_document_chunks"
        mock_client.get_collections.return_value.collections = [existing]
        mock_client.get_collection.return_value = SimpleNamespace(
            config=SimpleNamespace(
                params=SimpleNamespace(vectors=SimpleNamespace(size=256))
            )
        )
        mock_cls.return_value = mock_client
        doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
        r = client.post(f"/api/files/{doc_id}/index")

    assert r.status_code == 503
    assert "vector size does not match" in r.json()["detail"]["message"]
    mock_client.upsert.assert_not_called()


def test_index_returns_structured_lm_studio_unavailable_error(client, monkeypatch):
    from core.config import settings
    from services.embedding.base import EmbeddingProviderUnavailableError
    from services.embedding.lm_studio_embedding import LM_STUDIO_UNAVAILABLE_MESSAGE

    class UnavailableLMStudioEmbedding:
        provider_name = "lm_studio"
        model_name = "test-embed-model"
        vector_size = None

        def embed_texts(self, texts):
            raise EmbeddingProviderUnavailableError(LM_STUDIO_UNAVAILABLE_MESSAGE)

    monkeypatch.setattr(settings, "qdrant_url", "http://localhost:6333")
    monkeypatch.setattr(settings, "embedding_provider", "lm_studio")
    monkeypatch.setattr(
        "services.vector_index_service.get_configured_embedding_service",
        lambda: UnavailableLMStudioEmbedding(),
    )

    doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
    r = client.post(f"/api/files/{doc_id}/index")

    assert r.status_code == 503
    detail = r.json()["detail"]
    assert detail["message"] == LM_STUDIO_UNAVAILABLE_MESSAGE
    assert detail["embedding_provider"] == "lm_studio"
    assert detail["error_type"] == "embedding_provider"
    assert detail["qdrant_available"] is True


def test_index_returns_structured_lm_studio_no_model_error(client, monkeypatch):
    from core.config import settings
    from services.embedding.base import EmbeddingProviderError
    from services.embedding.lm_studio_embedding import LM_STUDIO_NO_MODEL_LOADED_MESSAGE

    class NoModelLMStudioEmbedding:
        provider_name = "lm_studio"
        model_name = "test-embed-model"
        vector_size = None

        def embed_texts(self, texts):
            raise EmbeddingProviderError(LM_STUDIO_NO_MODEL_LOADED_MESSAGE)

    monkeypatch.setattr(settings, "qdrant_url", "http://localhost:6333")
    monkeypatch.setattr(settings, "embedding_provider", "lm_studio")
    monkeypatch.setattr(
        "services.vector_index_service.get_configured_embedding_service",
        lambda: NoModelLMStudioEmbedding(),
    )

    doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
    r = client.post(f"/api/files/{doc_id}/index")

    assert r.status_code == 503
    detail = r.json()["detail"]
    assert detail["message"] == LM_STUDIO_NO_MODEL_LOADED_MESSAGE
    assert detail["error_type"] == "embedding_provider"
    assert detail["qdrant_available"] is True


# ── semantic-search endpoint ──────────────────────────────────────────────────

def test_semantic_search_requires_index_manifest(client, monkeypatch):
    from core.config import settings
    monkeypatch.setattr(settings, "qdrant_url", "http://localhost:6333")
    doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
    r = client.post(f"/api/files/{doc_id}/semantic-search", json={"query": "topic"})
    assert r.status_code == 404
    detail = r.json()["detail"]
    assert isinstance(detail, dict)
    assert detail["indexed"] is False
    assert "not indexed" in detail["message"].lower()


def test_semantic_search_response_shape(client, monkeypatch):
    from core.config import settings
    monkeypatch.setattr(settings, "qdrant_url", "http://localhost:6333")

    hit = MagicMock()
    hit.score = 0.92
    hit.payload = {
        "chunk_id": "abc123", "chunk_index": 0,
        "section_path": ["Overview"], "content_type": "text",
        "text": "This document covers the main topic.", "estimated_tokens": 40,
    }

    with patch("services.vector_index_service.QdrantClient") as mock_cls:
        mock_cls.return_value = _mock_qdrant_client()
        doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
        client.post(f"/api/files/{doc_id}/index")

    with patch("services.vector_index_service.QdrantClient") as mock_cls:
        mock_cls.return_value.search.return_value = [hit]
        r = client.post(
            f"/api/files/{doc_id}/semantic-search",
            json={"query": "main topic", "top_k": 3},
        )

    assert r.status_code == 200
    data = r.json()
    assert data["search_mode"] == "semantic"
    assert data["query"] == "main topic"
    assert data["top_k"] == 3
    assert len(data["results"]) == 1
    item = data["results"][0]
    for field in ["chunk_id", "chunk_index", "section_path", "content_type",
                  "score", "estimated_tokens", "text_preview", "retrieval_mode"]:
        assert field in item, f"Missing result field: {field}"
    assert item["score"] == 0.92
    assert item["retrieval_mode"] == "semantic"


def test_semantic_search_empty_results(client, monkeypatch):
    from core.config import settings
    monkeypatch.setattr(settings, "qdrant_url", "http://localhost:6333")

    with patch("services.vector_index_service.QdrantClient") as mock_cls:
        mock_cls.return_value = _mock_qdrant_client()
        doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
        client.post(f"/api/files/{doc_id}/index")

    with patch("services.vector_index_service.QdrantClient") as mock_cls:
        mock_cls.return_value.search.return_value = []
        r = client.post(
            f"/api/files/{doc_id}/semantic-search",
            json={"query": "xyzirrelevant"},
        )

    assert r.status_code == 200
    assert r.json()["results"] == []


# ── validation ────────────────────────────────────────────────────────────────

def test_semantic_search_empty_query_rejected(client, monkeypatch):
    from core.config import settings
    monkeypatch.setattr(settings, "qdrant_url", "http://localhost:6333")
    r = client.post("/api/files/x/semantic-search", json={"query": ""})
    assert r.status_code == 422


def test_semantic_search_top_k_over_limit_rejected(client, monkeypatch):
    from core.config import settings
    monkeypatch.setattr(settings, "qdrant_url", "http://localhost:6333")
    r = client.post("/api/files/x/semantic-search", json={"query": "q", "top_k": 51})
    assert r.status_code == 422
