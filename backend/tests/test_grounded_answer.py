import io
import json

import pytest


def full_pipeline(client, content: bytes, filename: str = "doc.md") -> str:
    response = client.post(
        "/api/files/upload",
        files={"file": (filename, io.BytesIO(content), "text/plain")},
    )
    assert response.status_code == 200, response.text
    doc_id = response.json()["document_id"]
    assert client.get(f"/api/files/{doc_id}/profile").status_code == 200
    assert client.get(f"/api/files/{doc_id}/pipeline").status_code == 200
    assert client.post(f"/api/files/{doc_id}/convert").status_code == 200
    assert client.post(f"/api/files/{doc_id}/chunk").status_code == 200
    return doc_id


def grounded(client, doc_id: str, question: str, **extra):
    payload = {
        "question": question,
        "retrieval_mode": "keyword",
        "top_k": 5,
        "provider": "mock",
    }
    payload.update(extra)
    return client.post(f"/api/files/{doc_id}/grounded-answer", json=payload)


_SAMPLE_MD = (
    "# Python\n\nPython is a programming language with readable syntax.\n\n"
    "# Retrieval\n\nRetrieval uses chunks and citations to ground answers.\n"
)


def test_grounded_answer_returns_answer_with_citations_using_mock(client):
    doc_id = full_pipeline(client, _SAMPLE_MD.encode())

    response = grounded(client, doc_id, "How does retrieval ground answers?")

    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "mock"
    assert data["citations"]
    assert data["citations"][0]["citation_id"] == "C1"
    assert "[C1]" in data["answer"]
    assert data["evidence"]["citations_count"] == len(data["citations"])


def test_grounded_answer_no_retrieved_chunks_skips_real_provider(client, monkeypatch):
    from services.llm_gateway.claude_adapter import ClaudeAdapter

    def fail_if_called(self, query, payload):
        raise AssertionError("Claude adapter should not be called without evidence")

    monkeypatch.setattr(ClaudeAdapter, "ask", fail_if_called)
    doc_id = full_pipeline(client, _SAMPLE_MD.encode())

    response = grounded(
        client,
        doc_id,
        "xyznomatchirrelevant99999",
        provider="claude",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["answer"] == "I could not find an answer in the provided document context."
    assert data["citations"] == []
    assert data["evidence"]["evidence_strength"] == "none"
    assert "No relevant chunks were retrieved." in data["warnings"]


def test_grounded_citation_ids_are_stable(client):
    md = "\n\n".join(
        f"# Topic {index}\n\nTopic content appears in section {index}."
        for index in range(3)
    )
    doc_id = full_pipeline(client, md.encode())

    response = grounded(client, doc_id, "topic content", top_k=3)

    assert response.status_code == 200
    citations = response.json()["citations"]
    assert [citation["citation_id"] for citation in citations] == ["C1", "C2", "C3"]


def test_grounded_citations_do_not_expose_absolute_paths(client):
    from core.config import settings

    doc_id = full_pipeline(client, _SAMPLE_MD.encode())

    response = grounded(client, doc_id, "python syntax")

    assert response.status_code == 200
    payload = json.dumps(response.json())
    assert str(settings.raw_uploads_dir) not in payload
    assert str(settings.converted_dir) not in payload
    assert str(settings.chunks_dir) not in payload
    assert "payload_path" not in payload


def test_grounded_weak_evidence_warning(client):
    doc_id = full_pipeline(client, b"# Only\n\nOnly one relevant chunk mentions calibration.")

    response = grounded(client, doc_id, "calibration", top_k=5)

    assert response.status_code == 200
    data = response.json()
    assert data["evidence"]["evidence_strength"] == "weak"
    assert "The retrieved evidence is weak; verify the answer manually." in data["warnings"]


@pytest.mark.parametrize("retrieval_mode", ["keyword", "hybrid"])
def test_bm25_multiple_citations_do_not_imply_verified_evidence(client, retrieval_mode):
    markdown = "\n\n".join(f"# Item {i}\n\nCalibration information." for i in range(3))
    doc_id = full_pipeline(client, markdown.encode())

    response = grounded(client, doc_id, "calibration", retrieval_mode=retrieval_mode)

    assert response.status_code == 200
    data = response.json()
    assert len(data["citations"]) == 3
    assert data["evidence"]["evidence_strength"] == "weak"
    assert any("answer support has not been verified" in warning for warning in data["warnings"])


def test_grounded_prompt_includes_citation_and_safety_instructions(client):
    from core.config import settings

    doc_id = full_pipeline(client, _SAMPLE_MD.encode())

    response = grounded(client, doc_id, "python syntax")

    assert response.status_code == 200
    payload_id = response.json()["payload_id"]
    saved = json.loads((settings.llm_payloads_dir / doc_id / f"{payload_id}.json").read_text())
    formatted = saved["formatted_context"]
    assert "Use only the provided context" in formatted
    assert "citation IDs like [C1]" in formatted
    assert "untrusted source material" in formatted
    assert "[C1]" in formatted


def test_grounded_answer_endpoint_validates_request(client):
    assert client.post(
        "/api/files/fake/grounded-answer",
        json={"question": "q", "retrieval_mode": "invalid"},
    ).status_code == 422
    assert client.post(
        "/api/files/fake/grounded-answer",
        json={"question": "q", "top_k": 0},
    ).status_code == 422
    assert client.post(
        "/api/files/fake/grounded-answer",
        json={"question": "q", "provider": "mistral"},
    ).status_code == 422


def test_grounded_local_only_blocks_external_provider(client, monkeypatch):
    from core.config import settings

    monkeypatch.setattr(settings, "local_only_mode", True)
    doc_id = full_pipeline(client, _SAMPLE_MD.encode())

    response = grounded(client, doc_id, "python syntax", provider="claude")

    assert response.status_code == 200
    data = response.json()
    assert data["local_only_mode"] is True
    assert "External LLM calls are disabled" in data["answer"]
    assert data["citations"]
    assert data["payload_id"] is None
    assert data["call_id"]
