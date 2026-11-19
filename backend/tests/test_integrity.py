import io
import json


# ── helpers ───────────────────────────────────────────────────────────────────

def upload(client, content: bytes, filename: str, ct: str = "application/octet-stream") -> str:
    r = client.post("/api/files/upload", files={"file": (filename, io.BytesIO(content), ct)})
    assert r.status_code == 200, r.text
    return r.json()["document_id"]


def full_pipeline(client, content: bytes, filename: str) -> str:
    doc_id = upload(client, content, filename)
    assert client.get(f"/api/files/{doc_id}/profile").status_code == 200
    assert client.get(f"/api/files/{doc_id}/pipeline").status_code == 200
    assert client.post(f"/api/files/{doc_id}/convert").status_code == 200
    assert client.post(f"/api/files/{doc_id}/chunk").status_code == 200
    return doc_id


def full_pipeline_no_chunks(client, content: bytes, filename: str) -> str:
    doc_id = upload(client, content, filename)
    assert client.get(f"/api/files/{doc_id}/profile").status_code == 200
    assert client.get(f"/api/files/{doc_id}/pipeline").status_code == 200
    assert client.post(f"/api/files/{doc_id}/convert").status_code == 200
    return doc_id


# ── happy path ────────────────────────────────────────────────────────────────

def test_integrity_passes_after_full_pipeline(client):
    doc_id = full_pipeline(client, b"# Title\n\nContent.\n", "doc.md")
    r = client.get(f"/api/files/{doc_id}/integrity")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "pass"
    assert data["errors"] == []


def test_integrity_passes_without_chunks(client):
    doc_id = full_pipeline_no_chunks(client, b"# Title\n\nContent.\n", "doc.md")
    r = client.get(f"/api/files/{doc_id}/integrity")
    assert r.status_code == 200
    data = r.json()
    # Chunks are optional — status should be pass (chunks are "skip")
    assert data["status"] == "pass"
    skip_checks = [c for c in data["checks"] if c["status"] == "skip"]
    assert any("chunks" in c["name"] for c in skip_checks)


def test_integrity_warns_after_upload_only(client):
    doc_id = upload(client, b"hello world", "notes.txt")
    r = client.get(f"/api/files/{doc_id}/integrity")
    assert r.status_code == 200
    data = r.json()
    # Profile and pipeline are missing → warn
    assert data["status"] == "warn"
    assert any("profile" in c["name"] and c["status"] == "warn" for c in data["checks"])


# ── chunk SHA-256 corruption ──────────────────────────────────────────────────

def test_integrity_fails_on_corrupted_chunk_text(client):
    from core.config import settings

    doc_id = full_pipeline(client, b"# Section\n\nOriginal text.\n", "doc.md")

    jsonl_path = settings.chunks_dir / doc_id / "chunks.jsonl"
    lines = jsonl_path.read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    first["text"] = "TAMPERED CONTENT"   # SHA-256 now wrong
    lines[0] = json.dumps(first)
    jsonl_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    r = client.get(f"/api/files/{doc_id}/integrity")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "fail"
    assert any("SHA-256 mismatch" in e for e in data["errors"])


def test_integrity_fails_on_corrupted_chunk_sha_field(client):
    from core.config import settings

    doc_id = full_pipeline(client, b"# Test\n\nContent here.\n", "doc.md")

    jsonl_path = settings.chunks_dir / doc_id / "chunks.jsonl"
    lines = jsonl_path.read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    first["sha256"] = "a" * 64   # valid format but wrong value
    lines[0] = json.dumps(first)
    jsonl_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    r = client.get(f"/api/files/{doc_id}/integrity")
    assert r.json()["status"] == "fail"


# ── missing files ─────────────────────────────────────────────────────────────

def test_integrity_fails_on_missing_raw_file(client):
    from core.config import settings

    doc_id = full_pipeline_no_chunks(client, b"test content", "notes.txt")

    # Delete the raw uploaded file
    meta = json.loads((settings.raw_uploads_dir / doc_id / "metadata.json").read_text())
    (settings.raw_uploads_dir / doc_id / meta["stored_filename"]).unlink()

    r = client.get(f"/api/files/{doc_id}/integrity")
    assert r.json()["status"] == "fail"
    assert any("raw_file" in c["name"] and c["status"] == "fail" for c in r.json()["checks"])


def test_integrity_unknown_document_returns_404(client):
    r = client.get("/api/files/does-not-exist/integrity")
    assert r.status_code == 404


# ── invalid JSON / schema ─────────────────────────────────────────────────────

def test_integrity_fails_on_invalid_json_in_profile(client):
    from core.config import settings

    doc_id = full_pipeline_no_chunks(client, b"# Doc\n\nContent.\n", "doc.md")
    (settings.raw_uploads_dir / doc_id / "profile.json").write_text("{not valid json}")

    r = client.get(f"/api/files/{doc_id}/integrity")
    assert r.json()["status"] == "fail"
    assert any("profile" in c["name"] and c["status"] == "fail" for c in r.json()["checks"])


def test_integrity_fails_on_invalid_schema_in_profile(client):
    from core.config import settings

    doc_id = full_pipeline_no_chunks(client, b"# Doc\n\nContent.\n", "doc.md")

    # Write valid JSON but with an invalid category value
    profile = json.loads((settings.raw_uploads_dir / doc_id / "profile.json").read_text())
    profile["category"] = "not_a_real_category"
    (settings.raw_uploads_dir / doc_id / "profile.json").write_text(json.dumps(profile))

    r = client.get(f"/api/files/{doc_id}/integrity")
    assert r.json()["status"] == "fail"


def test_integrity_fails_on_invalid_jsonl_line(client):
    from core.config import settings

    doc_id = full_pipeline(client, b"# Test\n\nContent.\n", "doc.md")

    jsonl_path = settings.chunks_dir / doc_id / "chunks.jsonl"
    original = jsonl_path.read_text(encoding="utf-8")
    jsonl_path.write_text(original + "{broken json\n", encoding="utf-8")

    r = client.get(f"/api/files/{doc_id}/integrity")
    assert r.json()["status"] == "fail"


# ── report structure ──────────────────────────────────────────────────────────

def test_integrity_report_has_required_fields(client):
    doc_id = full_pipeline(client, b"# Doc\n\nContent.\n", "doc.md")
    r = client.get(f"/api/files/{doc_id}/integrity")
    assert r.status_code == 200
    data = r.json()
    assert "document_id" in data
    assert "status" in data
    assert "checks" in data
    assert "warnings" in data
    assert "errors" in data
    assert isinstance(data["checks"], list)
    assert all("name" in c and "status" in c and "message" in c for c in data["checks"])


def test_integrity_all_check_names_present(client):
    doc_id = full_pipeline(client, b"# Doc\n\nContent.\n", "doc.md")
    r = client.get(f"/api/files/{doc_id}/integrity")
    check_names = {c["name"] for c in r.json()["checks"]}
    for expected in ["raw_metadata", "raw_file", "profile", "pipeline_decision",
                     "document_md", "conversion_metadata", "chunks_jsonl", "chunk_manifest"]:
        assert expected in check_names, f"Missing check: {expected}"


# ── unit: verify_chunk ────────────────────────────────────────────────────────

def test_verify_chunk_passes_for_valid_sha(client):
    import hashlib
    from services.integrity_service import IntegrityService
    from models.chunk_models import Chunk

    text = "Hello, integrity world."
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    chunk = Chunk(
        chunk_id="aaaabbbb-0000-0000-0000-000000000000",
        document_id="ddddeeee-0000-0000-0000-000000000000",
        document_version="1",
        section_path=["Root"],
        chunk_index=0,
        content_type="text",
        text=text,
        char_count=len(text),
        estimated_tokens=max(1, len(text) // 4),
        sha256=sha,
    )
    assert IntegrityService.verify_chunk(chunk) is True


def test_verify_chunk_fails_for_wrong_sha(client):
    from services.integrity_service import IntegrityService
    from models.chunk_models import Chunk

    chunk = Chunk(
        chunk_id="aaaabbbb-0000-0000-0000-000000000000",
        document_id="ddddeeee-0000-0000-0000-000000000000",
        document_version="1",
        section_path=[],
        chunk_index=0,
        content_type="text",
        text="original text",
        char_count=13,
        estimated_tokens=3,
        sha256="a" * 64,   # wrong hash
    )
    assert IntegrityService.verify_chunk(chunk) is False
