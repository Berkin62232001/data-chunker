import io


_SAMPLE_MD = (
    "# Introduction\n\nThis document covers Python programming.\n\n"
    "# Functions\n\nFunctions are reusable blocks of code.\n"
)


def upload(client, content: bytes = _SAMPLE_MD.encode(), filename: str = "doc.md") -> str:
    r = client.post(
        "/api/files/upload",
        files={"file": (filename, io.BytesIO(content), "text/plain")},
    )
    assert r.status_code == 200, r.text
    return r.json()["document_id"]


def full_pipeline(client, content: bytes = _SAMPLE_MD.encode(), filename: str = "doc.md") -> str:
    doc_id = upload(client, content, filename)
    assert client.get(f"/api/files/{doc_id}/profile").status_code == 200
    assert client.get(f"/api/files/{doc_id}/pipeline").status_code == 200
    assert client.post(f"/api/files/{doc_id}/convert").status_code == 200
    assert client.post(f"/api/files/{doc_id}/chunk").status_code == 200
    return doc_id


# ── DB initialisation ─────────────────────────────────────────────────────────

def test_db_tables_created(client):
    """DB tables must exist after the test fixture initialises."""
    from db.session import get_session
    from db.models import Document, DocumentProfile, PipelineDecision
    with get_session() as session:
        # These queries would fail if the tables don't exist
        assert session.query(Document).count() >= 0
        assert session.query(DocumentProfile).count() >= 0
        assert session.query(PipelineDecision).count() >= 0


# ── Upload creates document row ───────────────────────────────────────────────

def test_upload_creates_document_row(client):
    doc_id = upload(client)
    from db import repository
    from db.session import get_session
    with get_session() as session:
        doc = repository.get_document(session, doc_id)
        assert doc is not None
        doc_id_v = doc.document_id
        fname = doc.original_filename
        status = doc.status
        phase = doc.current_phase
    assert doc_id_v == doc_id
    assert fname == "doc.md"
    assert status == "raw"
    assert phase == "upload"


def test_upload_sets_file_size(client):
    content = b"Hello " * 100
    doc_id = upload(client, content, "notes.txt")
    from db import repository
    from db.session import get_session
    with get_session() as session:
        doc = repository.get_document(session, doc_id)
        size = doc.file_size_bytes
    assert size == len(content)


# ── Profile creates profile row ───────────────────────────────────────────────

def test_profile_creates_db_row(client):
    doc_id = upload(client)
    client.get(f"/api/files/{doc_id}/profile")

    from db import repository
    from db.session import get_session
    with get_session() as session:
        prof = repository.get_latest_profile(session, doc_id)
        assert prof is not None
        doc_id_v = prof.document_id
    assert doc_id_v == doc_id


def test_profile_updates_document_phase(client):
    doc_id = upload(client)
    client.get(f"/api/files/{doc_id}/profile")

    from db import repository
    from db.session import get_session
    with get_session() as session:
        doc = repository.get_document(session, doc_id)
        phase = doc.current_phase
    assert phase == "profiled"


# ── Pipeline creates decision row ─────────────────────────────────────────────

def test_pipeline_creates_db_row(client):
    doc_id = upload(client)
    client.get(f"/api/files/{doc_id}/profile")
    client.get(f"/api/files/{doc_id}/pipeline")

    from db import repository
    from db.session import get_session
    with get_session() as session:
        pipe = repository.get_latest_pipeline_decision(session, doc_id)
        assert pipe is not None
        pipeline_name = pipe.selected_pipeline
    assert pipeline_name != ""


# ── Document list endpoint ────────────────────────────────────────────────────

def test_document_list_endpoint(client):
    upload(client, filename="a.txt")
    upload(client, filename="b.txt")

    r = client.get("/api/documents")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 2
    assert len(data["documents"]) >= 2
    item = data["documents"][0]
    for field in ["document_id", "original_filename", "status", "current_phase", "created_at"]:
        assert field in item, f"missing field: {field}"


def test_document_list_empty(client):
    r = client.get("/api/documents")
    assert r.status_code == 200
    assert r.json()["total"] == 0


# ── Document detail endpoint ──────────────────────────────────────────────────

def test_document_detail_endpoint(client):
    doc_id = full_pipeline(client)
    r = client.get(f"/api/documents/{doc_id}")
    assert r.status_code == 200
    data = r.json()
    assert data["document_id"] == doc_id
    assert data["profile"] is not None
    assert data["pipeline"] is not None
    assert data["conversion"] is not None
    assert data["chunks"] is not None
    assert "recent_payloads" in data
    assert "recent_llm_calls" in data


def test_document_detail_not_found(client):
    r = client.get("/api/documents/nonexistent-id")
    assert r.status_code == 404


def test_document_detail_phases_correct(client):
    doc_id = full_pipeline(client)
    r = client.get(f"/api/documents/{doc_id}")
    assert r.json()["current_phase"] == "chunked"


# ── Project list endpoint ─────────────────────────────────────────────────────

def test_project_list_endpoint(client):
    client.post("/api/projects", json={"name": "Alpha"})
    client.post("/api/projects", json={"name": "Beta"})

    r = client.get("/api/projects")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 2
    assert len(data["projects"]) >= 2
    proj = data["projects"][0]
    for field in ["project_id", "name", "document_count", "created_at"]:
        assert field in proj, f"missing field: {field}"


def test_project_list_document_count(client):
    doc_id = full_pipeline(client)
    r = client.post("/api/projects", json={"name": "P"})
    project_id = r.json()["project_id"]
    client.post(f"/api/projects/{project_id}/add-document", json={"document_id": doc_id})

    r2 = client.get("/api/projects")
    projects = {p["project_id"]: p for p in r2.json()["projects"]}
    assert projects[project_id]["document_count"] == 1


# ── Audit recent endpoint ─────────────────────────────────────────────────────

def test_audit_recent_endpoint(client):
    full_pipeline(client)
    r = client.get("/api/audit/recent")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] > 0
    event = data["events"][0]
    for field in ["id", "event_type", "created_at"]:
        assert field in event, f"missing field: {field}"


def test_audit_recent_limit(client):
    for _ in range(3):
        upload(client)
    r = client.get("/api/audit/recent?limit=2")
    assert r.status_code == 200
    assert len(r.json()["events"]) <= 2


def test_audit_recent_has_upload_event(client):
    doc_id = upload(client)
    r = client.get("/api/audit/recent")
    events = r.json()["events"]
    upload_events = [e for e in events if e["event_type"] == "upload" and e["document_id"] == doc_id]
    assert len(upload_events) == 1
