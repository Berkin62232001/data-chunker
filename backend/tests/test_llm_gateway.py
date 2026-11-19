import io


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


def ask(client, doc_id: str, query: str = "topic", top_k: int = 5, provider: str = "mock"):
    return client.post(
        "/api/llm/ask",
        json={"document_id": doc_id, "query": query, "top_k": top_k, "provider": provider},
    )


_SAMPLE_MD = (
    "# Introduction\n\nThis section covers the main topic in detail.\n\n"
    "# Details\n\nMore information about the topic and its implementation.\n"
)


# ── response shape ────────────────────────────────────────────────────────────

def test_ask_response_shape(client):
    doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
    r = ask(client, doc_id)
    assert r.status_code == 200
    data = r.json()
    for field in ["answer", "provider", "chunks_used", "estimated_context_tokens", "payload_id"]:
        assert field in data, f"Missing field: {field}"


def test_provider_echoed_back(client):
    doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
    r = ask(client, doc_id, provider="mock")
    assert r.json()["provider"] == "mock"


# ── mock provider ─────────────────────────────────────────────────────────────

def test_mock_answer_contains_mock_label(client):
    doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
    r = ask(client, doc_id, query="topic")
    assert "[Mock]" in r.json()["answer"]


def test_mock_answer_references_chunk_content(client):
    doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
    r = ask(client, doc_id, query="introduction topic")
    answer = r.json()["answer"].lower()
    # The answer should reference actual document content
    assert "topic" in answer or "introduction" in answer or "section" in answer


def test_mock_answer_no_real_api_called(client):
    doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
    r = ask(client, doc_id)
    assert "No real LLM was called" in r.json()["answer"]


# ── unconfigured providers ────────────────────────────────────────────────────

def test_claude_not_configured_returns_200(client):
    doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
    r = ask(client, doc_id, provider="claude")
    assert r.status_code == 200


def test_claude_not_configured_message(client):
    doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
    r = ask(client, doc_id, provider="claude")
    assert "ANTHROPIC_API_KEY" in r.json()["answer"]


def test_openai_not_configured_message(client):
    doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
    r = ask(client, doc_id, provider="openai")
    assert r.status_code == 200
    assert "not configured" in r.json()["answer"].lower()
    assert "OPENAI_API_KEY" in r.json()["answer"]


def test_gemini_not_configured_message(client):
    doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
    r = ask(client, doc_id, provider="gemini")
    assert r.status_code == 200
    assert "not configured" in r.json()["answer"].lower()
    assert "GEMINI_API_KEY" in r.json()["answer"]


# ── no matching chunks ────────────────────────────────────────────────────────

def test_mock_no_matching_chunks(client):
    doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
    r = ask(client, doc_id, query="xyznomatchirrelevant99999")
    assert r.status_code == 200
    data = r.json()
    assert data["chunks_used"] == 0
    assert "No relevant content" in data["answer"]


def test_chunks_used_zero_when_no_match(client):
    doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
    r = ask(client, doc_id, query="qqqzzzxxx999irrelevant")
    assert r.json()["chunks_used"] == 0


# ── top_k behaviour ───────────────────────────────────────────────────────────

def test_top_k_limits_chunks_used(client):
    md = "\n\n".join(f"# Topic {i}\n\nContent about topic {i}.\n" for i in range(10))
    doc_id = full_pipeline(client, md.encode(), "doc.md")
    r = ask(client, doc_id, query="topic content", top_k=2)
    assert r.status_code == 200
    assert r.json()["chunks_used"] <= 2


def test_top_k_default_is_five(client):
    md = "\n\n".join(f"# Section {i}\n\nContent {i}.\n" for i in range(10))
    doc_id = full_pipeline(client, md.encode(), "doc.md")
    r = client.post("/api/llm/ask", json={"document_id": doc_id, "query": "content"})
    assert r.status_code == 200
    assert r.json()["chunks_used"] <= 5


# ── payload_id ────────────────────────────────────────────────────────────────

def test_payload_id_is_non_empty_string(client):
    doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
    r = ask(client, doc_id)
    payload_id = r.json()["payload_id"]
    assert isinstance(payload_id, str)
    assert len(payload_id) > 0


def test_payload_id_starts_with_payload_prefix(client):
    doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
    r = ask(client, doc_id)
    assert r.json()["payload_id"].startswith("payload_")


# ── token estimate ────────────────────────────────────────────────────────────

def test_estimated_tokens_is_non_negative(client):
    doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
    r = ask(client, doc_id)
    assert r.json()["estimated_context_tokens"] >= 0


# ── validation / error cases ──────────────────────────────────────────────────

def test_empty_query_rejected(client):
    r = client.post("/api/llm/ask", json={"document_id": "x", "query": ""})
    assert r.status_code == 422


def test_invalid_provider_rejected(client):
    r = client.post("/api/llm/ask", json={"document_id": "x", "query": "q", "provider": "mistral"})
    assert r.status_code == 422


def test_top_k_zero_rejected(client):
    r = client.post("/api/llm/ask", json={"document_id": "x", "query": "q", "top_k": 0})
    assert r.status_code == 422


def test_no_chunks_returns_404(client):
    # Upload only, no chunk step
    r = client.post(
        "/api/files/upload",
        files={"file": ("doc.md", io.BytesIO(b"# Test\n\nContent.\n"), "text/plain")},
    )
    doc_id = r.json()["document_id"]
    r2 = ask(client, doc_id)
    assert r2.status_code == 404


def test_unknown_document_returns_404(client):
    r = ask(client, "nonexistent-id")
    assert r.status_code == 404
