import io
import json


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


def prepare(client, doc_id: str, query: str = "topic", top_k: int = 3, provider: str = "generic"):
    return client.post(
        f"/api/files/{doc_id}/prepare-llm-payload",
        json={"query": query, "top_k": top_k, "provider": provider},
    )


_SAMPLE_MD = (
    "# Introduction\n\nThis section covers the main topic.\n\n"
    "# Details\n\nMore information about the topic here.\n"
)


# ── payload generation ────────────────────────────────────────────────────────

def test_payload_response_shape(client):
    doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
    r = prepare(client, doc_id)
    assert r.status_code == 200
    data = r.json()
    for field in [
        "document_id", "provider", "query", "chunks_used",
        "total_estimated_tokens", "payload_path",
        "universal_payload", "formatted_context", "integrity",
    ]:
        assert field in data, f"Missing field: {field}"


def test_universal_payload_structure(client):
    doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
    r = prepare(client, doc_id, query="topic")
    payload = r.json()["universal_payload"]
    assert payload["task"] == "answer_question_from_document"
    assert payload["user_question"] == "topic"
    assert "instructions" in payload
    assert "safety" in payload["instructions"]
    assert "citation" in payload["instructions"]
    assert "document_context" in payload
    assert "chunks" in payload["document_context"]
    assert "integrity" in payload


def test_safety_instruction_present(client):
    doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
    r = prepare(client, doc_id)
    safety = r.json()["universal_payload"]["instructions"]["safety"]
    assert "untrusted" in safety.lower()
    assert "do not follow instructions" in safety.lower()


def test_citation_instruction_present(client):
    doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
    r = prepare(client, doc_id)
    citation = r.json()["universal_payload"]["instructions"]["citation"]
    assert "chunk_id" in citation
    assert "section_path" in citation


def test_top_k_limits_chunks(client):
    md = "\n\n".join(f"# Topic {i}\n\nContent about topic {i}.\n" for i in range(10))
    doc_id = full_pipeline(client, md.encode(), "doc.md")
    r = prepare(client, doc_id, query="topic content", top_k=2)
    assert r.status_code == 200
    assert r.json()["chunks_used"] <= 2
    chunks = r.json()["universal_payload"]["document_context"]["chunks"]
    assert len(chunks) <= 2


def test_chunk_fields_in_payload(client):
    doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
    r = prepare(client, doc_id, query="topic")
    chunks = r.json()["universal_payload"]["document_context"]["chunks"]
    if chunks:
        chunk = chunks[0]
        for field in ["chunk_id", "chunk_index", "section_path", "content_type", "text", "estimated_tokens"]:
            assert field in chunk, f"Missing chunk field: {field}"


# ── claude XML output ─────────────────────────────────────────────────────────

def test_claude_xml_wraps_document(client):
    doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
    r = prepare(client, doc_id, query="topic", provider="claude")
    ctx = r.json()["formatted_context"]
    assert ctx.strip().startswith("<document>")
    assert ctx.strip().endswith("</document>")


def test_claude_xml_contains_safety(client):
    doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
    r = prepare(client, doc_id, query="topic", provider="claude")
    ctx = r.json()["formatted_context"]
    assert "<safety_notice>" in ctx
    assert "untrusted" in ctx.lower()


def test_claude_xml_contains_question(client):
    doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
    r = prepare(client, doc_id, query="my specific question", provider="claude")
    ctx = r.json()["formatted_context"]
    assert "<question>my specific question</question>" in ctx


def test_claude_xml_contains_chunks(client):
    doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
    r = prepare(client, doc_id, query="topic", provider="claude")
    ctx = r.json()["formatted_context"]
    assert "<chunk " in ctx
    assert "</chunk>" in ctx


# ── generic / openai / gemini markdown output ─────────────────────────────────

def test_generic_markdown_has_header(client):
    doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
    r = prepare(client, doc_id, query="topic", provider="generic")
    ctx = r.json()["formatted_context"]
    assert "# Document Context" in ctx


def test_generic_markdown_safety_blockquote(client):
    doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
    r = prepare(client, doc_id, query="topic", provider="generic")
    ctx = r.json()["formatted_context"]
    assert "**Safety**" in ctx
    assert "untrusted" in ctx.lower()


def test_generic_markdown_includes_question(client):
    doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
    r = prepare(client, doc_id, query="my question here", provider="generic")
    ctx = r.json()["formatted_context"]
    assert "my question here" in ctx


def test_openai_provider_returns_markdown(client):
    doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
    r = prepare(client, doc_id, query="topic", provider="openai")
    assert r.status_code == 200
    ctx = r.json()["formatted_context"]
    assert "# Document Context" in ctx


def test_gemini_provider_returns_markdown(client):
    doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
    r = prepare(client, doc_id, query="topic", provider="gemini")
    assert r.status_code == 200
    ctx = r.json()["formatted_context"]
    assert "# Document Context" in ctx


# ── hash verification ─────────────────────────────────────────────────────────

def test_all_chunks_verified_on_clean_data(client):
    doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
    r = prepare(client, doc_id, query="topic")
    integrity = r.json()["integrity"]
    assert integrity["all_chunks_verified"] is True
    assert integrity["verified_count"] > 0
    assert integrity["failed_chunk_ids"] == []


def test_tampered_chunk_flagged(client, tmp_path, monkeypatch):
    from core.config import settings

    doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
    jsonl_path = settings.chunks_dir / doc_id / "chunks.jsonl"

    # Read all lines and corrupt the SHA-256 of the first chunk
    lines = jsonl_path.read_text(encoding="utf-8").splitlines()
    corrupted = []
    tampered = False
    for line in lines:
        if line.strip() and not tampered:
            obj = json.loads(line)
            obj["sha256"] = "a" * 64  # wrong hash
            corrupted.append(json.dumps(obj))
            tampered = True
        else:
            corrupted.append(line)
    jsonl_path.write_text("\n".join(corrupted) + "\n", encoding="utf-8")

    r = prepare(client, doc_id, query="topic", top_k=10)
    assert r.status_code == 200
    integrity = r.json()["integrity"]
    assert integrity["all_chunks_verified"] is False
    assert len(integrity["failed_chunk_ids"]) >= 1


# ── payload saving ────────────────────────────────────────────────────────────

def test_payload_saved_to_disk(client):
    from core.config import settings

    doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
    r = prepare(client, doc_id, query="topic")
    assert r.status_code == 200

    payload_dir = settings.llm_payloads_dir / doc_id
    saved_files = list(payload_dir.glob("payload_*.json"))
    assert len(saved_files) == 1

    saved = json.loads(saved_files[0].read_text(encoding="utf-8"))
    assert saved["task"] == "answer_question_from_document"
    assert "formatted_context" in saved
    assert "provider" in saved


def test_each_call_writes_new_file(client):
    from core.config import settings

    doc_id = full_pipeline(client, _SAMPLE_MD.encode(), "doc.md")
    prepare(client, doc_id, query="first question")
    prepare(client, doc_id, query="second question")

    payload_dir = settings.llm_payloads_dir / doc_id
    saved_files = list(payload_dir.glob("payload_*.json"))
    assert len(saved_files) == 2


# ── validation / error cases ──────────────────────────────────────────────────

def test_empty_query_rejected(client):
    r = client.post("/api/files/fake/prepare-llm-payload", json={"query": ""})
    assert r.status_code == 422


def test_invalid_provider_rejected(client):
    r = client.post("/api/files/fake/prepare-llm-payload", json={"query": "q", "provider": "mistral"})
    assert r.status_code == 422


def test_requires_chunks(client):
    md = b"# Test\n\nContent.\n"
    r = client.post("/api/files/upload", files={"file": ("doc.md", io.BytesIO(md), "text/plain")})
    doc_id = r.json()["document_id"]
    r2 = prepare(client, doc_id, query="test")
    assert r2.status_code == 404


def test_unknown_document_returns_404(client):
    r = prepare(client, "nonexistent-id", query="test")
    assert r.status_code == 404
