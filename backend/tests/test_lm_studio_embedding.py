import json

import httpx
import pytest

from core.config import Settings, settings
from services.embedding.base import (
    EmbeddingConfigurationError,
    EmbeddingProviderError,
    EmbeddingProviderUnavailableError,
)
from services.embedding.factory import create_embedding_service
from services.embedding.lm_studio_embedding import (
    LM_STUDIO_MODEL_NOT_EMBEDDING_CAPABLE_TEMPLATE,
    LM_STUDIO_MODEL_UNAVAILABLE_TEMPLATE,
    LM_STUDIO_NO_MODEL_LOADED_MESSAGE,
    LM_STUDIO_UNAVAILABLE_MESSAGE,
    LMStudioEmbeddingService,
)


def _service_with_transport(transport: httpx.MockTransport, batch_size: int = 16):
    return LMStudioEmbeddingService(
        base_url="http://lm-studio.test/v1",
        model_name="test-embed-model",
        api_key="",
        timeout_seconds=5,
        batch_size=batch_size,
        http_client=httpx.Client(transport=transport),
    )


def test_embedding_provider_default_is_deterministic_demo(monkeypatch):
    monkeypatch.delenv("EMBEDDING_PROVIDER", raising=False)
    cfg = Settings()
    assert cfg.embedding_provider == "deterministic_demo"


def test_unsupported_embedding_provider_returns_clear_error(monkeypatch):
    monkeypatch.setattr(settings, "embedding_provider", "unknown_provider")
    with pytest.raises(EmbeddingConfigurationError) as exc:
        create_embedding_service()
    assert "Unsupported EMBEDDING_PROVIDER 'unknown_provider'" in str(exc.value)
    assert "deterministic_demo" in str(exc.value)
    assert "lm_studio" in str(exc.value)


def test_lm_studio_provider_builds_openai_compatible_request():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["payload"] = json.loads(request.content.decode())
        return httpx.Response(
            200,
            json={"data": [{"embedding": [0.1, 0.2, 0.3]}]},
        )

    svc = _service_with_transport(httpx.MockTransport(handler))
    vector = svc.embed_text("hello")

    assert vector == [0.1, 0.2, 0.3]
    assert seen["method"] == "POST"
    assert seen["path"] == "/v1/embeddings"
    assert seen["payload"] == {"model": "test-embed-model", "input": ["hello"]}


def test_lm_studio_provider_parses_embedding_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": [{"embedding": [1, "2.5", 3]}]},
        )

    svc = _service_with_transport(httpx.MockTransport(handler))
    assert svc.embed_text("hello") == [1.0, 2.5, 3.0]
    assert svc.vector_size == 3


def test_lm_studio_unavailable_returns_clear_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    svc = _service_with_transport(httpx.MockTransport(handler))
    with pytest.raises(EmbeddingProviderUnavailableError) as exc:
        svc.embed_text("hello")
    assert str(exc.value) == LM_STUDIO_UNAVAILABLE_MESSAGE


def test_lm_studio_no_models_loaded_returns_clear_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "error": "No models loaded. Please load a model in the developer page or use the 'lms load' command."
            },
        )

    svc = _service_with_transport(httpx.MockTransport(handler))
    with pytest.raises(EmbeddingProviderError) as exc:
        svc.embed_text("hello")
    assert str(exc.value) == LM_STUDIO_NO_MODEL_LOADED_MESSAGE


def test_lm_studio_selected_model_unavailable_returns_clear_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": {"message": "Model not found"}})

    svc = _service_with_transport(httpx.MockTransport(handler))
    with pytest.raises(EmbeddingProviderError) as exc:
        svc.embed_text("hello")
    assert str(exc.value) == LM_STUDIO_MODEL_UNAVAILABLE_TEMPLATE.format(
        model="test-embed-model"
    )


def test_lm_studio_non_embedding_model_returns_clear_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"text": "not an embedding"}]})

    svc = _service_with_transport(httpx.MockTransport(handler))
    with pytest.raises(EmbeddingProviderError) as exc:
        svc.embed_text("hello")
    assert str(exc.value) == LM_STUDIO_MODEL_NOT_EMBEDDING_CAPABLE_TEMPLATE.format(
        model="test-embed-model"
    )


def test_lm_studio_batch_embedding_uses_configured_batch_size():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        requests.append(payload)
        data = [
            {"embedding": [float(index), float(index + 1)]}
            for index, _text in enumerate(payload["input"])
        ]
        return httpx.Response(200, json={"data": data})

    svc = _service_with_transport(httpx.MockTransport(handler), batch_size=2)
    vectors = svc.embed_texts(["a", "b", "c"])

    assert vectors == [[0.0, 1.0], [1.0, 2.0], [0.0, 1.0]]
    assert [payload["input"] for payload in requests] == [["a", "b"], ["c"]]
