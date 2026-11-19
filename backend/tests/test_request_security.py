import asyncio

import pytest

from core.config import settings
from core.request_security import RequestSecurityMiddleware
from utils.storage_paths import UnsafeStoragePath, storage_path


def test_missing_and_incorrect_keys_are_rejected(client):
    client.headers.pop("Authorization")
    assert client.get("/api/documents").status_code == 401
    assert client.get("/docs").status_code == 401
    assert client.get("/health").status_code == 200
    assert client.get("/api/documents", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_unconfigured_key_fails_closed(client, monkeypatch):
    monkeypatch.setattr(settings, "api_access_key", None)
    assert client.get("/api/documents").status_code == 503


def test_valid_key_and_cors_preflight(client):
    assert client.get("/api/documents").status_code == 200
    response = client.options("/api/documents", headers={
        "Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "authorization",
    })
    assert response.status_code == 200


@pytest.mark.parametrize("identifier", ["../outside", "/tmp/outside", "..", "a/b", "a\\b", "%2e%2e", "a\x00b"])
def test_paths_reject_unsafe_identifiers(tmp_path, identifier):
    with pytest.raises(UnsafeStoragePath):
        storage_path(tmp_path, identifier)


def test_paths_reject_directory_and_file_symlink_escape(tmp_path):
    root = tmp_path / "chunks"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "escape").symlink_to(outside, target_is_directory=True)
    with pytest.raises(UnsafeStoragePath):
        storage_path(root, "escape", "chunks.jsonl")
    (root / "valid").mkdir()
    (root / "valid" / "chunks.jsonl").symlink_to(outside / "secret")
    with pytest.raises(UnsafeStoragePath):
        storage_path(root, "valid", "chunks.jsonl")


def test_original_traversal_probe_cannot_write_payload(client, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "chunks.jsonl").write_text("")
    response = client.post("/api/llm/ask", json={
        "document_id": "../outside", "query": "probe", "provider": "mock",
        "retrieval_mode": "keyword",
    })
    assert response.status_code == 422
    assert list(outside.iterdir()) == [outside / "chunks.jsonl"]


def test_oversized_request_rejected_before_upload(client, monkeypatch):
    monkeypatch.setattr(settings, "max_request_size_mb", 1)
    response = client.post("/api/files/upload", files={"file": ("large.txt", b"x" * (1024 * 1024 + 1))})
    assert response.status_code == 413
    assert not list(settings.raw_uploads_dir.iterdir())


def test_chunked_body_limit_and_rate_limit(monkeypatch):
    from pydantic import SecretStr
    monkeypatch.setattr(settings, "api_access_key", SecretStr("k" * 32))
    monkeypatch.setattr(settings, "max_request_size_mb", 1)
    monkeypatch.setattr(settings, "requests_per_minute", 1)

    async def run():
        called = []
        async def downstream(scope, receive, send):
            called.append(True)
        middleware = RequestSecurityMiddleware(downstream)
        scope = {"type": "http", "path": "/api/files/upload", "headers": [
            (b"authorization", b"Bearer " + b"k" * 32),
        ]}
        messages = iter([
            {"type": "http.request", "body": b"x" * (1024 * 1024), "more_body": True},
            {"type": "http.request", "body": b"x", "more_body": False},
        ])
        async def receive():
            return next(messages)
        sent = []
        async def send(message):
            sent.append(message)
        await middleware(scope, receive, send)
        assert sent[0]["status"] == 413
        assert not called
        sent.clear()
        await middleware(scope, receive, send)
        assert sent[0]["status"] == 429
    asyncio.run(run())


def test_local_only_rejects_remote_embedding_host(monkeypatch):
    from services.embedding.base import EmbeddingConfigurationError
    from services.embedding.factory import create_embedding_service
    monkeypatch.setattr(settings, "local_only_mode", True)
    monkeypatch.setattr(settings, "embedding_provider", "lm_studio")
    monkeypatch.setattr(settings, "lm_studio_base_url", "https://example.com/v1")
    with pytest.raises(EmbeddingConfigurationError):
        create_embedding_service()
