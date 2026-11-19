import hashlib
import io
import json
from datetime import datetime, timezone

import pytest


def upload(client, content: bytes, filename: str, ct: str = "text/plain") -> str:
    response = client.post("/api/files/upload", files={"file": (filename, io.BytesIO(content), ct)})
    assert response.status_code == 200, response.text
    return response.json()["document_id"]


def full_pipeline(client, content: bytes, filename: str = "doc.md") -> str:
    doc_id = upload(client, content, filename)
    assert client.get(f"/api/files/{doc_id}/profile").status_code == 200
    assert client.get(f"/api/files/{doc_id}/pipeline").status_code == 200
    assert client.post(f"/api/files/{doc_id}/convert").status_code == 200
    assert client.post(f"/api/files/{doc_id}/chunk").status_code == 200
    return doc_id


def _chunk(
    document_id: str,
    chunk_index: int,
    text: str,
    estimated_tokens: int,
    section_path=None,
) -> dict:
    section_path = section_path or ["Section"]
    return {
        "chunk_id": f"{document_id}-chunk-{chunk_index}",
        "document_id": document_id,
        "document_version": "1",
        "section_path": section_path,
        "chunk_index": chunk_index,
        "content_type": "text",
        "text": text,
        "char_count": len(text),
        "estimated_tokens": estimated_tokens,
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


def write_chunks(settings, document_id: str, chunks: list[dict]) -> None:
    out_dir = settings.chunks_dir / document_id
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "chunks.jsonl").write_text(
        "\n".join(json.dumps(chunk) for chunk in chunks) + "\n",
        encoding="utf-8",
    )
    total_tokens = sum(chunk.get("estimated_tokens", 0) for chunk in chunks)
    manifest = {
        "document_id": document_id,
        "total_chunks": len(chunks),
        "total_estimated_tokens": total_tokens,
        "average_chunk_tokens": total_tokens // len(chunks) if chunks else 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "chunking_strategy": "test",
        "source_document_md_sha256": "a" * 64,
    }
    (out_dir / "chunk_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def evaluation(client, doc_id: str, query: str, **extra):
    payload = {"query": query, "retrieval_mode": "keyword", "top_k": 5}
    payload.update(extra)
    return client.post(f"/api/files/{doc_id}/retrieval-evaluation", json=payload)


def test_chunk_quality_valid_chunks(client):
    from core.config import settings

    doc_id = "quality-valid"
    chunks = [
        _chunk(doc_id, 0, "Alpha " * 1400, 360, ["Intro"]),
        _chunk(doc_id, 1, "Beta " * 1400, 420, ["Details"]),
    ]
    write_chunks(settings, doc_id, chunks)

    response = client.get(f"/api/files/{doc_id}/chunk-quality")

    assert response.status_code == 200
    data = response.json()
    assert data["total_chunks"] == 2
    assert data["quality_score"] >= 95
    assert data["oversized_chunks_count"] == 0
    assert data["undersized_chunks_count"] == 0
    assert data["section_path_coverage_percent"] == 100.0


def test_chunk_quality_missing_chunks(client):
    response = client.get("/api/files/not-chunked/chunk-quality")

    assert response.status_code == 200
    data = response.json()
    assert data["total_chunks"] == 0
    assert data["quality_score"] == 0
    assert data["warnings"]


def test_chunk_quality_oversized_and_undersized_warnings(client):
    from core.config import settings

    doc_id = "quality-size-warnings"
    chunks = [
        _chunk(doc_id, 0, "Tiny chunk text", 40, ["Tiny"]),
        _chunk(doc_id, 1, "Large chunk text " * 2000, 1200, ["Large"]),
    ]
    write_chunks(settings, doc_id, chunks)

    response = client.get(f"/api/files/{doc_id}/chunk-quality")

    assert response.status_code == 200
    data = response.json()
    assert data["undersized_chunks_count"] == 1
    assert data["oversized_chunks_count"] == 1
    assert any("below" in warning for warning in data["warnings"])
    assert any("exceed" in warning for warning in data["warnings"])


def test_token_efficiency_calculation(client):
    md = (
        "# Retrieval\n\n"
        + ("Python retrieval quality uses focused context and compact chunks. " * 80)
        + "\n\n# Other\n\n"
        + ("Unrelated background content. " * 80)
    )
    doc_id = full_pipeline(client, md.encode())

    baseline = client.get(f"/api/files/{doc_id}/token-efficiency")
    assert baseline.status_code == 200
    assert baseline.json()["converted_estimated_tokens"] is not None

    response = evaluation(client, doc_id, "Python retrieval quality")

    assert response.status_code == 200
    data = response.json()
    summary = data["token_efficiency_estimate"]
    selected = data["total_context_tokens"]
    converted = summary["converted_estimated_tokens"]
    assert summary["selected_context_tokens"] == selected
    assert summary["token_reduction_percent_vs_converted"] == round((1 - selected / converted) * 100, 2)


def test_token_efficiency_missing_tokens(client):
    doc_id = upload(client, b"# Only uploaded\n\nNo conversion yet.", "doc.md")

    response = client.get(f"/api/files/{doc_id}/token-efficiency")

    assert response.status_code == 200
    data = response.json()
    assert data["converted_estimated_tokens"] is None
    assert data["total_chunk_tokens"] is None
    assert data["warnings"]


def test_retrieval_evaluation_keyword(client):
    md = (
        "# Python\n\nPython is a programming language with readable syntax.\n\n"
        "# JavaScript\n\nJavaScript runs in browsers.\n"
    )
    doc_id = full_pipeline(client, md.encode())

    response = evaluation(client, doc_id, "python programming")

    assert response.status_code == 200
    data = response.json()
    assert data["returned_chunks_count"] >= 1
    top = data["selected_results"][0]
    searchable = (top["text_preview"] + " " + " ".join(top["section_path"])).lower()
    assert "python" in searchable
    assert "text" not in top


@pytest.mark.parametrize("retrieval_mode", ["keyword", "hybrid"])
def test_evaluation_skips_absolute_threshold_for_bm25(client, retrieval_mode):
    doc_id = full_pipeline(client, b"# Match\n\nRetrieval calibration.\n")

    response = evaluation(client, doc_id, "calibration", retrieval_mode=retrieval_mode)

    assert response.status_code == 200
    data = response.json()
    assert data["returned_chunks_count"] == 1
    assert data["low_score_results_count"] == 0
    assert any("absolute low-score thresholds are not applied" in warning for warning in data["warnings"])


def test_retrieval_evaluation_expected_terms(client):
    md = (
        "# Mission\n\n"
        "The Mars mission needs propellant planning, delta-v budgets, and transfer windows.\n\n"
        "# Ground Ops\n\nGround support handles communications.\n"
    )
    doc_id = full_pipeline(client, md.encode())

    response = evaluation(
        client,
        doc_id,
        "mars mission propellant",
        expected_terms=["propellant", "delta-v", "not-present"],
        expected_section="Mission",
    )

    assert response.status_code == 200
    data = response.json()
    assert set(data["expected_terms_found"]) >= {"propellant", "delta-v"}
    assert data["expected_terms_missing"] == ["not-present"]
    assert data["expected_section_hit"] is True
    assert data["retrieval_score_estimate"] > 50


def test_retrieval_evaluation_no_results(client):
    doc_id = full_pipeline(client, b"# Intro\n\nHello world.\n")

    response = evaluation(client, doc_id, "xyznomatchirrelevant99999")

    assert response.status_code == 200
    data = response.json()
    assert data["returned_chunks_count"] == 0
    assert data["selected_results"] == []
    assert data["warnings"]


def test_evaluation_apis_do_not_expose_absolute_paths(client):
    from core.config import settings

    doc_id = full_pipeline(client, b"# Paths\n\nThis content mentions no filesystem paths.\n")
    responses = [
        client.get(f"/api/files/{doc_id}/chunk-quality"),
        evaluation(client, doc_id, "paths"),
        client.get(f"/api/files/{doc_id}/token-efficiency"),
        client.post(
            f"/api/files/{doc_id}/retrieval-evaluation-set",
            json={
                "retrieval_mode": "keyword",
                "top_k": 3,
                "queries": [{"query": "paths", "expected_terms": ["content"]}],
            },
        ),
    ]

    for response in responses:
        assert response.status_code == 200, response.text
        payload = json.dumps(response.json())
        assert str(settings.raw_uploads_dir) not in payload
        assert str(settings.converted_dir) not in payload
        assert str(settings.chunks_dir) not in payload


def test_retrieval_evaluation_set_aggregate(client):
    md = (
        "# Alpha\n\nAlpha topic includes apples and analysis.\n\n"
        "# Beta\n\nBeta topic includes bananas and baselines.\n"
    )
    doc_id = full_pipeline(client, md.encode())

    response = client.post(
        f"/api/files/{doc_id}/retrieval-evaluation-set",
        json={
            "retrieval_mode": "keyword",
            "top_k": 3,
            "queries": [
                {"query": "alpha apples", "expected_terms": ["apples"], "expected_section": "Alpha"},
                {"query": "beta bananas", "expected_terms": ["bananas"], "expected_section": "Beta"},
            ],
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total_queries"] == 2
    assert len(data["queries"]) == 2
    assert data["average_retrieval_score_estimate"] > 0
    assert data["average_context_tokens"] > 0
