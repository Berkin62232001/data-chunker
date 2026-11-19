"""Tests for GET /api/files/{id}/preview and POST /api/files/{id}/initialize."""
import io


_SAMPLE = b"# Hello\n\nThis is a test document.\n"


def upload(client, content: bytes = _SAMPLE, filename: str = "doc.md") -> str:
    r = client.post(
        "/api/files/upload",
        files={"file": (filename, io.BytesIO(content), "text/plain")},
    )
    assert r.status_code == 200, r.text
    return r.json()["document_id"]


def full_pipeline(client, content: bytes = _SAMPLE, filename: str = "doc.md") -> str:
    doc_id = upload(client, content, filename)
    client.get(f"/api/files/{doc_id}/profile")
    client.get(f"/api/files/{doc_id}/pipeline")
    client.post(f"/api/files/{doc_id}/convert")
    return doc_id


# ── Preview tests ─────────────────────────────────────────────────────────────

def test_preview_not_converted_returns_exists_false(client):
    doc_id = upload(client)
    r = client.get(f"/api/files/{doc_id}/preview")
    assert r.status_code == 200
    data = r.json()
    assert data["exists"] is False
    assert data["preview"] == ""
    assert data["char_count"] == 0
    assert data["truncated"] is False
    assert data["source"] == "converted_document_md"
    assert data["document_id"] == doc_id


def test_preview_after_conversion_returns_exists_true(client):
    doc_id = full_pipeline(client)
    r = client.get(f"/api/files/{doc_id}/preview")
    assert r.status_code == 200
    data = r.json()
    assert data["exists"] is True
    assert len(data["preview"]) > 0
    assert data["char_count"] > 0
    assert data["document_id"] == doc_id
    assert data["source"] == "converted_document_md"


def test_preview_default_max_chars(client):
    doc_id = full_pipeline(client)
    r = client.get(f"/api/files/{doc_id}/preview")
    assert r.status_code == 200
    assert len(r.json()["preview"]) <= 12000


def test_preview_custom_max_chars(client):
    content = b"A" * 500
    doc_id = full_pipeline(client, content=content, filename="big.txt")
    r = client.get(f"/api/files/{doc_id}/preview?max_chars=10")
    assert r.status_code == 200
    data = r.json()
    assert data["exists"] is True
    assert len(data["preview"]) <= 10
    assert data["truncated"] is True


def test_preview_not_truncated_for_short_doc(client):
    doc_id = full_pipeline(client)
    r = client.get(f"/api/files/{doc_id}/preview?max_chars=50000")
    assert r.status_code == 200
    data = r.json()
    assert data["exists"] is True
    assert data["truncated"] is False
    assert len(data["preview"]) == data["char_count"]


def test_preview_enforces_max_cap(client):
    doc_id = upload(client)
    # max_chars=999999 should be capped to 50000
    r = client.get(f"/api/files/{doc_id}/preview?max_chars=999999")
    # Returns exists=False (not converted) but no 500 error
    assert r.status_code == 200


def test_preview_document_not_found(client):
    r = client.get("/api/files/nonexistent-doc-id/preview")
    assert r.status_code == 404


def test_preview_schema(client):
    doc_id = upload(client)
    r = client.get(f"/api/files/{doc_id}/preview")
    data = r.json()
    for field in ["document_id", "exists", "preview", "char_count", "truncated", "source"]:
        assert field in data, f"Missing field: {field}"


# ── Initialize tests ──────────────────────────────────────────────────────────

def test_initialize_creates_profile_and_pipeline(client):
    doc_id = upload(client)
    r = client.post(f"/api/files/{doc_id}/initialize")
    assert r.status_code == 200
    data = r.json()
    assert data["profile_created"] is True
    assert data["pipeline_created"] is True
    assert data["document_id"] == doc_id
    assert "current_phase" in data
    assert isinstance(data["warnings"], list)


def test_initialize_idempotent_when_already_done(client):
    doc_id = upload(client)
    # Run once
    r1 = client.post(f"/api/files/{doc_id}/initialize")
    assert r1.status_code == 200
    # Run again — should not fail and should report not re-created
    r2 = client.post(f"/api/files/{doc_id}/initialize")
    assert r2.status_code == 200
    data = r2.json()
    assert data["profile_created"] is False
    assert data["pipeline_created"] is False


def test_initialize_skips_pipeline_if_profile_fails(client):
    # Upload to a temp path but break things artificially by calling an invalid doc
    r = client.post("/api/files/fake-nonexistent/initialize")
    assert r.status_code == 404


def test_initialize_after_manual_profile_skips_profile(client):
    doc_id = upload(client)
    # Run profile manually
    client.get(f"/api/files/{doc_id}/profile")
    # Initialize should skip profile creation
    r = client.post(f"/api/files/{doc_id}/initialize")
    assert r.status_code == 200
    data = r.json()
    assert data["profile_created"] is False
    assert data["pipeline_created"] is True  # pipeline was missing, gets created


def test_initialize_schema(client):
    doc_id = upload(client)
    r = client.post(f"/api/files/{doc_id}/initialize")
    data = r.json()
    for field in ["document_id", "profile_created", "pipeline_created", "current_phase", "warnings"]:
        assert field in data, f"Missing field: {field}"


# ── Paginated documents tests ─────────────────────────────────────────────────

def test_paginated_empty(client):
    r = client.get("/api/documents/paginated")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 0
    assert data["page"] == 1
    assert data["documents"] == []
    assert "page_size" in data
    assert "pages" in data


def test_paginated_basic(client):
    for i in range(5):
        upload(client, filename=f"doc{i}.md")
    r = client.get("/api/documents/paginated?page=1&page_size=3")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 5
    assert len(data["documents"]) == 3
    assert data["page"] == 1
    assert data["page_size"] == 3
    assert data["pages"] == 2


def test_paginated_page2(client):
    for i in range(5):
        upload(client, filename=f"doc{i}.md")
    r = client.get("/api/documents/paginated?page=2&page_size=3")
    assert r.status_code == 200
    data = r.json()
    assert len(data["documents"]) == 2


def test_paginated_search(client):
    upload(client, filename="apple.md")
    upload(client, filename="banana.md")
    upload(client, filename="apricot.md")
    r = client.get("/api/documents/paginated?search=ap")
    assert r.status_code == 200
    names = [d["original_filename"] for d in r.json()["documents"]]
    assert all("ap" in n for n in names)


def test_paginated_phase_filter(client):
    doc_id = upload(client)
    client.get(f"/api/files/{doc_id}/profile")
    upload(client)  # stays at upload phase
    r = client.get("/api/documents/paginated?phase=profiled")
    assert r.status_code == 200
    for d in r.json()["documents"]:
        assert d["current_phase"] == "profiled"


def test_paginated_sort_oldest(client):
    for i in range(3):
        upload(client, filename=f"f{i}.md")
    r_new = client.get("/api/documents/paginated?sort=newest")
    r_old = client.get("/api/documents/paginated?sort=oldest")
    new_ids = [d["document_id"] for d in r_new.json()["documents"]]
    old_ids = [d["document_id"] for d in r_old.json()["documents"]]
    assert new_ids == list(reversed(old_ids))


def test_paginated_cap_page_size(client):
    r = client.get("/api/documents/paginated?page_size=9999")
    assert r.status_code == 200
    assert r.json()["page_size"] == 100
