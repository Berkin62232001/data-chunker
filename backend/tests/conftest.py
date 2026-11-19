import pytest
from fastapi.testclient import TestClient

from core.config import settings
from main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    from pydantic import SecretStr
    monkeypatch.setattr(settings, "api_access_key", SecretStr("test-access-key-not-a-secret-12345"))
    monkeypatch.setattr(settings, "requests_per_minute", 100000)
    monkeypatch.setattr(settings, "raw_uploads_dir", tmp_path / "raw")
    monkeypatch.setattr(settings, "converted_dir", tmp_path / "converted")
    monkeypatch.setattr(settings, "chunks_dir", tmp_path / "chunks")
    monkeypatch.setattr(settings, "llm_payloads_dir", tmp_path / "llm_payloads")
    monkeypatch.setattr(settings, "projects_dir", tmp_path / "projects")
    monkeypatch.setattr(settings, "audit_log_dir", tmp_path / "audit")
    monkeypatch.setattr(settings, "local_only_mode", False)
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path}/test.db")
    # Ensure API keys are absent in tests so placeholder adapters behave consistently
    monkeypatch.setattr(settings, "anthropic_api_key", None)
    monkeypatch.setattr(settings, "openai_api_key", None)
    monkeypatch.setattr(settings, "gemini_api_key", None)
    # Qdrant disabled by default — tests that need it enable it explicitly
    monkeypatch.setattr(settings, "qdrant_url", None)
    monkeypatch.setattr(settings, "qdrant_api_key", None)
    monkeypatch.setattr(settings, "qdrant_collection", "test_document_chunks")
    monkeypatch.setattr(settings, "embedding_provider", "deterministic_demo")
    monkeypatch.setattr(settings, "lm_studio_base_url", "http://localhost:1234/v1")
    monkeypatch.setattr(settings, "lm_studio_embedding_model", "nomic-embed-text")
    monkeypatch.setattr(settings, "lm_studio_api_key", "lm-studio")
    monkeypatch.setattr(settings, "lm_studio_timeout_seconds", 30)
    monkeypatch.setattr(settings, "lm_studio_batch_size", 16)
    monkeypatch.setattr(settings, "ocr_enabled", False)
    monkeypatch.setattr(settings, "ocr_provider", "ocrmypdf")
    monkeypatch.setattr(settings, "ocr_language", "eng")
    monkeypatch.setattr(settings, "ocr_timeout_seconds", 120)
    monkeypatch.setattr(settings, "ocr_max_pages", 50)
    monkeypatch.setattr(settings, "ocr_dpi", 300)
    monkeypatch.setattr(settings, "ocr_output_mode", "text")
    monkeypatch.setattr(settings, "ocr_fail_open", True)

    from services.embedding.factory import reset_embedding_service_cache
    reset_embedding_service_cache()

    # Reset DB engine so the new database_url takes effect, then create tables
    from db.session import reset_engine
    reset_engine()
    from db.init_db import init_db
    init_db()

    with TestClient(app) as c:
        c.headers["Authorization"] = "Bearer test-access-key-not-a-secret-12345"
        yield c

    reset_embedding_service_cache()
    reset_engine()
