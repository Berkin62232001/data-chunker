"""Tests for Phase 20: export, CSV, and summary endpoints."""
import io

from core.config import settings


_SAMPLE = b"# Hello\n\nThis is a test document for export testing.\n"


def upload(client, content: bytes = _SAMPLE, filename: str = "testdoc.md") -> str:
    r = client.post(
        "/api/files/upload",
        files={"file": (filename, io.BytesIO(content), "text/plain")},
    )
    assert r.status_code == 200, r.text
    return r.json()["document_id"]


def full_pipeline(client, content: bytes = _SAMPLE, filename: str = "testdoc.md") -> str:
    doc_id = upload(client, content, filename)
    client.get(f"/api/files/{doc_id}/profile")
    client.get(f"/api/files/{doc_id}/pipeline")
    client.post(f"/api/files/{doc_id}/convert")
    return doc_id


def full_pipeline_with_chunks(client, content: bytes = _SAMPLE, filename: str = "testdoc.md") -> str:
    doc_id = full_pipeline(client, content, filename)
    client.post(f"/api/files/{doc_id}/chunk")
    return doc_id


# ── Export artifact tests ─────────────────────────────────────────────────────

def test_export_markdown_success(client):
    doc_id = full_pipeline(client)
    r = client.get(f"/api/files/{doc_id}/export?artifact=markdown")
    assert r.status_code == 200
    assert len(r.content) > 0
    assert "content-disposition" in r.headers
    disposition = r.headers["content-disposition"]
    assert "attachment" in disposition
    assert ".md" in disposition


def test_export_chunks_success(client):
    doc_id = full_pipeline_with_chunks(client)
    r = client.get(f"/api/files/{doc_id}/export?artifact=chunks")
    assert r.status_code == 200
    assert len(r.content) > 0
    disposition = r.headers.get("content-disposition", "")
    assert ".jsonl" in disposition


def test_export_profile_success(client):
    doc_id = upload(client)
    client.get(f"/api/files/{doc_id}/profile")
    r = client.get(f"/api/files/{doc_id}/export?artifact=profile")
    assert r.status_code == 200
    assert len(r.content) > 0
    disposition = r.headers.get("content-disposition", "")
    assert ".json" in disposition


def test_export_pipeline_success(client):
    doc_id = upload(client)
    client.get(f"/api/files/{doc_id}/profile")
    client.get(f"/api/files/{doc_id}/pipeline")
    r = client.get(f"/api/files/{doc_id}/export?artifact=pipeline")
    assert r.status_code == 200
    assert len(r.content) > 0


def test_export_metadata_success(client):
    doc_id = full_pipeline(client)
    r = client.get(f"/api/files/{doc_id}/export?artifact=metadata")
    assert r.status_code == 200
    assert len(r.content) > 0


def test_export_integrity_success(client):
    doc_id = upload(client)
    r = client.get(f"/api/files/{doc_id}/export?artifact=integrity")
    assert r.status_code == 200
    import json
    data = json.loads(r.content)
    assert "document_id" in data
    assert "status" in data
    assert "checks" in data
    disposition = r.headers.get("content-disposition", "")
    assert "_integrity.json" in disposition


def test_export_missing_artifact_returns_404(client):
    doc_id = upload(client)
    # markdown requires conversion — not done yet
    r = client.get(f"/api/files/{doc_id}/export?artifact=markdown")
    assert r.status_code == 404


def test_export_missing_chunks_returns_404(client):
    doc_id = full_pipeline(client)
    # converted but not chunked
    r = client.get(f"/api/files/{doc_id}/export?artifact=chunks")
    assert r.status_code == 404


def test_export_invalid_artifact_returns_400(client):
    doc_id = upload(client)
    r = client.get(f"/api/files/{doc_id}/export?artifact=INVALID")
    assert r.status_code == 400


def test_export_path_traversal_rejected(client):
    doc_id = upload(client)
    r = client.get(f"/api/files/{doc_id}/export?artifact=../../etc/passwd")
    assert r.status_code == 400


def test_export_document_not_found(client):
    r = client.get("/api/files/nonexistent-id/export?artifact=markdown")
    assert r.status_code == 404


def test_export_safe_filename_no_server_path(client):
    doc_id = full_pipeline(client, filename="my document (2024).md")
    r = client.get(f"/api/files/{doc_id}/export?artifact=markdown")
    assert r.status_code == 200
    disposition = r.headers.get("content-disposition", "")
    # Filename should not contain absolute server path
    assert "/" not in disposition.split("filename=")[-1].strip('"')
    # Should contain safe chars only
    assert "storage" not in disposition


def test_export_inline_mode(client):
    doc_id = full_pipeline(client)
    r = client.get(f"/api/files/{doc_id}/export?artifact=markdown&download=false")
    assert r.status_code == 200
    disposition = r.headers.get("content-disposition", "")
    assert "inline" in disposition


# ── CSV export tests ──────────────────────────────────────────────────────────

def test_export_csv_empty(client):
    r = client.get("/api/documents/export.csv")
    assert r.status_code == 200
    assert "text/csv" in r.headers.get("content-type", "")
    lines = r.text.strip().split("\n")
    # Only header row
    assert len(lines) == 1
    assert "document_id" in lines[0]


def test_export_csv_includes_documents(client):
    doc_id1 = upload(client, filename="file1.md")
    doc_id2 = upload(client, filename="file2.md")
    r = client.get("/api/documents/export.csv")
    assert r.status_code == 200
    assert doc_id1 in r.text
    assert doc_id2 in r.text
    assert "file1.md" in r.text
    assert "file2.md" in r.text


def test_export_csv_header_fields(client):
    upload(client)
    r = client.get("/api/documents/export.csv")
    assert r.status_code == 200
    header = r.text.split("\n")[0]
    for field in ["document_id", "original_filename", "mime_type", "file_size_bytes",
                  "status", "current_phase", "created_at", "updated_at"]:
        assert field in header, f"Missing CSV field: {field}"


def test_export_csv_content_disposition(client):
    r = client.get("/api/documents/export.csv")
    disposition = r.headers.get("content-disposition", "")
    assert "attachment" in disposition
    assert "documents_export.csv" in disposition


def test_export_csv_with_search_filter(client):
    upload(client, filename="apple.md")
    upload(client, filename="banana.md")
    r = client.get("/api/documents/export.csv?search=apple")
    assert r.status_code == 200
    assert "apple.md" in r.text
    assert "banana.md" not in r.text


def test_export_csv_with_phase_filter(client):
    doc_id = upload(client)
    client.get(f"/api/files/{doc_id}/profile")
    upload(client)  # remains at upload phase
    r = client.get("/api/documents/export.csv?phase=profiled")
    assert r.status_code == 200
    # Count data rows
    lines = [ln for ln in r.text.strip().split("\n") if ln.strip()]
    assert len(lines) == 2  # header + 1 profiled doc


# ── Summary endpoint tests ────────────────────────────────────────────────────

def test_summary_document_not_found(client):
    r = client.get("/api/documents/nonexistent-id/summary")
    assert r.status_code == 404


def test_summary_basic_fields(client):
    doc_id = upload(client, filename="sample.md")
    r = client.get(f"/api/documents/{doc_id}/summary")
    assert r.status_code == 200
    data = r.json()
    assert data["document_id"] == doc_id
    assert data["original_filename"] == "sample.md"
    assert "status" in data
    assert "current_phase" in data
    assert "file_size_bytes" in data
    assert "created_at" in data


def test_summary_schema_completeness(client):
    doc_id = upload(client)
    r = client.get(f"/api/documents/{doc_id}/summary")
    assert r.status_code == 200
    data = r.json()
    for field in [
        "document_id", "original_filename", "mime_type", "file_size_bytes",
        "status", "current_phase", "created_at",
        "profile", "pipeline", "conversion", "chunks",
        "integrity_status", "security_warnings_count", "preview_excerpt",
    ]:
        assert field in data, f"Missing field: {field}"


def test_summary_no_profile_before_profiling(client):
    doc_id = upload(client)
    r = client.get(f"/api/documents/{doc_id}/summary")
    assert r.status_code == 200
    data = r.json()
    assert data["profile"] is None
    assert data["pipeline"] is None
    assert data["preview_excerpt"] is None


def test_summary_includes_profile_after_profiling(client):
    doc_id = upload(client)
    client.get(f"/api/files/{doc_id}/profile")
    r = client.get(f"/api/documents/{doc_id}/summary")
    assert r.status_code == 200
    data = r.json()
    assert data["profile"] is not None
    assert "detected_type" in data["profile"]


def test_summary_includes_preview_after_conversion(client):
    doc_id = full_pipeline(client)
    r = client.get(f"/api/documents/{doc_id}/summary")
    assert r.status_code == 200
    data = r.json()
    assert data["preview_excerpt"] is not None
    assert len(data["preview_excerpt"]) > 0


def test_summary_preview_truncated_to_3000_chars(client):
    long_content = b"A " * 2000  # ~4000 bytes
    doc_id = full_pipeline(client, content=long_content, filename="long.txt")
    r = client.get(f"/api/documents/{doc_id}/summary")
    assert r.status_code == 200
    data = r.json()
    if data["preview_excerpt"] is not None:
        assert len(data["preview_excerpt"]) <= 3000


def test_summary_does_not_expose_raw_paths(client):
    doc_id = full_pipeline(client)
    r = client.get(f"/api/documents/{doc_id}/summary")
    assert r.status_code == 200
    text = r.text
    # Response should not contain absolute storage directory paths
    assert str(settings.raw_uploads_dir.resolve()) not in text
    assert str(settings.converted_dir.resolve()) not in text
    assert str(settings.chunks_dir.resolve()) not in text


def test_summary_no_payload_content(client):
    doc_id = full_pipeline_with_chunks(client)
    r = client.get(f"/api/documents/{doc_id}/summary")
    assert r.status_code == 200
    data = r.json()
    # Summary should not include raw payload data (only chunk counts are fine)
    assert "chunks_used" not in data
    assert "formatted_context" not in data
    assert "universal_payload" not in data


def test_summary_full_pipeline_populated(client):
    doc_id = full_pipeline_with_chunks(client)
    r = client.get(f"/api/documents/{doc_id}/summary")
    assert r.status_code == 200
    data = r.json()
    assert data["profile"] is not None
    assert data["pipeline"] is not None
    assert data["conversion"] is not None
    assert data["chunks"] is not None
    assert data["preview_excerpt"] is not None
