import io
import json
from unittest.mock import MagicMock, patch

import anthropic as anthropic_module
import pytest

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


def ask_claude(client, doc_id: str, query: str = "topic", top_k: int = 3):
    return client.post(
        "/api/llm/ask",
        json={"document_id": doc_id, "query": query, "top_k": top_k, "provider": "claude"},
    )


_SAMPLE_MD = (
    "# Overview\n\nThis document explains the main topic in detail.\n\n"
    "# Implementation\n\nThe implementation covers all major cases.\n"
)

_FAKE_ANSWER = "Based on the document, the main topic is explained in the Overview section [chunk_id: abc123]."


def _mock_message(text: str = _FAKE_ANSWER) -> MagicMock:
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    msg.stop_reason = "end_turn"
    msg.model = "claude-sonnet-4-6"
    msg.usage = MagicMock(input_tokens=120, output_tokens=40)
    return msg


# ── missing API key ───────────────────────────────────────────────────────────

def test_missing_api_key_returns_200(client):
    doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
    r = ask_claude(client, doc_id)
    assert r.status_code == 200


def test_missing_api_key_message_mentions_env_var(client):
    doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
    r = ask_claude(client, doc_id)
    assert "ANTHROPIC_API_KEY" in r.json()["answer"]


def test_missing_api_key_no_api_call_made(client):
    doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
    with patch("services.llm_gateway.claude_adapter.anthropic.Anthropic") as mock_cls:
        ask_claude(client, doc_id)
        mock_cls.assert_not_called()


# ── successful call ───────────────────────────────────────────────────────────

def test_claude_returns_answer(client, monkeypatch):
    from core.config import settings
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test-key")

    with patch("services.llm_gateway.claude_adapter.anthropic.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.return_value = _mock_message()
        doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
        r = ask_claude(client, doc_id, query="main topic")

    assert r.status_code == 200
    assert r.json()["answer"] == _FAKE_ANSWER


def test_claude_answer_provider_field(client, monkeypatch):
    from core.config import settings
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test-key")

    with patch("services.llm_gateway.claude_adapter.anthropic.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.return_value = _mock_message()
        doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
        r = ask_claude(client, doc_id)

    assert r.json()["provider"] == "claude"


def test_claude_chunks_used_in_response(client, monkeypatch):
    from core.config import settings
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test-key")

    with patch("services.llm_gateway.claude_adapter.anthropic.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.return_value = _mock_message()
        doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
        r = ask_claude(client, doc_id, query="topic", top_k=2)

    assert r.json()["chunks_used"] <= 2


# ── request structure ─────────────────────────────────────────────────────────

def test_builds_request_with_system_prompt(client, monkeypatch):
    from core.config import settings
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test-key")

    with patch("services.llm_gateway.claude_adapter.anthropic.Anthropic") as mock_cls:
        mock_create = mock_cls.return_value.messages.create
        mock_create.return_value = _mock_message()
        doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
        ask_claude(client, doc_id, query="topic")

    call_kwargs = mock_create.call_args.kwargs
    system = call_kwargs["system"]
    assert "Answer ONLY from the provided document context" in system
    assert "untrusted source material" in system
    assert "chunk_id" in system


def test_builds_request_with_xml_context(client, monkeypatch):
    from core.config import settings
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test-key")

    with patch("services.llm_gateway.claude_adapter.anthropic.Anthropic") as mock_cls:
        mock_create = mock_cls.return_value.messages.create
        mock_create.return_value = _mock_message()
        doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
        ask_claude(client, doc_id, query="implementation")

    call_kwargs = mock_create.call_args.kwargs
    user_content = call_kwargs["messages"][0]["content"]
    # Claude provider uses XML-wrapped context
    assert "<document>" in user_content
    assert "<question>" in user_content
    assert "<safety_notice>" in user_content


def test_uses_configured_model(client, monkeypatch):
    from core.config import settings
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test-key")
    monkeypatch.setattr(settings, "claude_model", "claude-opus-4-8")

    with patch("services.llm_gateway.claude_adapter.anthropic.Anthropic") as mock_cls:
        mock_create = mock_cls.return_value.messages.create
        mock_create.return_value = _mock_message()
        doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
        ask_claude(client, doc_id)

    assert mock_create.call_args.kwargs["model"] == "claude-opus-4-8"


def test_api_key_passed_to_client(client, monkeypatch):
    from core.config import settings
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test-key")

    with patch("services.llm_gateway.claude_adapter.anthropic.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.return_value = _mock_message()
        doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
        ask_claude(client, doc_id)

    init_kwargs = mock_cls.call_args.kwargs
    assert init_kwargs["api_key"] == "sk-ant-test-key"


# ── response metadata saved ───────────────────────────────────────────────────

def test_response_metadata_saved_to_disk(client, monkeypatch):
    from core.config import settings
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test-key")

    with patch("services.llm_gateway.claude_adapter.anthropic.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.return_value = _mock_message()
        doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
        r = ask_claude(client, doc_id)

    payload_id = r.json()["payload_id"]
    meta_files = list((settings.llm_payloads_dir / doc_id).glob(f"{payload_id}_claude_meta.json"))
    assert len(meta_files) == 1

    meta = json.loads(meta_files[0].read_text())
    assert meta["type"] == "claude_response_metadata"
    assert meta["model"] == "claude-sonnet-4-6"
    assert meta["stop_reason"] == "end_turn"
    assert "input_tokens" in meta
    assert "output_tokens" in meta
    assert "api_key" not in meta
    assert "ANTHROPIC_API_KEY" not in str(meta)


# ── error handling ────────────────────────────────────────────────────────────

def test_authentication_error_returns_200_with_message(client, monkeypatch):
    from core.config import settings
    monkeypatch.setattr(settings, "anthropic_api_key", "bad-key")

    with patch("services.llm_gateway.claude_adapter.anthropic.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.side_effect = anthropic_module.AuthenticationError(
            message="invalid key", response=MagicMock(status_code=401), body={}
        )
        doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
        r = ask_claude(client, doc_id)

    assert r.status_code == 200
    assert "authentication failed" in r.json()["answer"].lower()


def test_timeout_error_returns_200_with_message(client, monkeypatch):
    from core.config import settings
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test-key")

    with patch("services.llm_gateway.claude_adapter.anthropic.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.side_effect = anthropic_module.APITimeoutError(
            request=MagicMock()
        )
        doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
        r = ask_claude(client, doc_id)

    assert r.status_code == 200
    assert "timed out" in r.json()["answer"].lower()


def test_rate_limit_error_returns_200_with_message(client, monkeypatch):
    from core.config import settings
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test-key")

    with patch("services.llm_gateway.claude_adapter.anthropic.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.side_effect = anthropic_module.RateLimitError(
            message="rate limit", response=MagicMock(status_code=429), body={}
        )
        doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
        r = ask_claude(client, doc_id)

    assert r.status_code == 200
    assert "rate limit" in r.json()["answer"].lower()


def test_generic_api_error_returns_200_with_message(client, monkeypatch):
    from core.config import settings
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test-key")

    with patch("services.llm_gateway.claude_adapter.anthropic.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.side_effect = anthropic_module.InternalServerError(
            message="server error", response=MagicMock(status_code=500), body={}
        )
        doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
        r = ask_claude(client, doc_id)

    assert r.status_code == 200
    assert "claude api error" in r.json()["answer"].lower()
