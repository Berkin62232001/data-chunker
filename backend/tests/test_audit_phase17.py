"""Phase 17 tests: Alembic, timezone-aware timestamps, and audit filtering."""
import io
import os
from datetime import datetime, timezone


# ── Helpers ───────────────────────────────────────────────────────────────────

_SAMPLE = b"# Test\n\nHello world.\n"


def upload(client, filename: str = "doc.md") -> str:
    r = client.post(
        "/api/files/upload",
        files={"file": (filename, io.BytesIO(_SAMPLE), "text/plain")},
    )
    assert r.status_code == 200, r.text
    return r.json()["document_id"]


def full_pipeline(client, filename: str = "doc.md") -> str:
    doc_id = upload(client, filename)
    client.get(f"/api/files/{doc_id}/profile")
    client.get(f"/api/files/{doc_id}/pipeline")
    client.post(f"/api/files/{doc_id}/convert")
    client.post(f"/api/files/{doc_id}/chunk")
    return doc_id


# ── Alembic configuration ─────────────────────────────────────────────────────

def test_alembic_ini_exists():
    base = os.path.dirname(os.path.dirname(__file__))
    assert os.path.isfile(os.path.join(base, "alembic.ini"))


def test_alembic_env_exists():
    base = os.path.dirname(os.path.dirname(__file__))
    assert os.path.isfile(os.path.join(base, "alembic", "env.py"))


def test_alembic_versions_directory_exists():
    base = os.path.dirname(os.path.dirname(__file__))
    assert os.path.isdir(os.path.join(base, "alembic", "versions"))


def test_alembic_has_at_least_one_migration():
    base = os.path.dirname(os.path.dirname(__file__))
    versions_dir = os.path.join(base, "alembic", "versions")
    migration_files = [
        f for f in os.listdir(versions_dir)
        if f.endswith(".py") and not f.startswith("__")
    ]
    assert len(migration_files) >= 1, "Expected at least one migration file"


def test_alembic_env_connects_base_metadata():
    base = os.path.dirname(os.path.dirname(__file__))
    env_path = os.path.join(base, "alembic", "env.py")
    with open(env_path) as f:
        source = f.read()
    assert "target_metadata = Base.metadata" in source
    assert "from db.models import Base" in source


# ── Timezone-aware timestamps ─────────────────────────────────────────────────

def test_utc_now_is_timezone_aware():
    from db.models import utc_now
    ts = utc_now()
    assert ts.tzinfo is not None
    assert ts.tzinfo == timezone.utc or ts.utcoffset().total_seconds() == 0


def test_document_created_at_stored_as_utc(client):
    doc_id = upload(client)
    from db import repository
    from db.session import get_session
    with get_session() as session:
        doc = repository.get_document(session, doc_id)
        ts = doc.created_at
    # SQLite with DateTime(timezone=True) returns aware datetime
    assert ts is not None
    if ts.tzinfo is not None:
        assert ts.utcoffset().total_seconds() == 0


def test_api_created_at_is_iso_string(client):
    upload(client)
    r = client.get("/api/documents")
    assert r.status_code == 200
    item = r.json()["documents"][0]
    # Must be a valid ISO string
    parsed = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    assert isinstance(parsed, datetime)


# ── Audit /recent filter: document_id ─────────────────────────────────────────

def test_audit_filter_by_document_id(client):
    doc_a = upload(client, "a.md")
    doc_b = upload(client, "b.md")

    r = client.get(f"/api/audit/recent?document_id={doc_a}")
    assert r.status_code == 200
    events = r.json()["events"]
    assert len(events) > 0
    for e in events:
        assert e["document_id"] == doc_a, f"Expected doc_a, got {e['document_id']}"


def test_audit_filter_document_id_excludes_others(client):
    doc_a = upload(client, "a.md")
    doc_b = upload(client, "b.md")

    r = client.get(f"/api/audit/recent?document_id={doc_a}")
    for e in r.json()["events"]:
        assert e["document_id"] != doc_b


def test_audit_filter_document_id_no_results(client):
    r = client.get("/api/audit/recent?document_id=nonexistent-id")
    assert r.status_code == 200
    assert r.json()["total"] == 0
    assert r.json()["events"] == []


# ── Audit /recent filter: project_id ──────────────────────────────────────────

def test_audit_filter_by_project_id(client):
    r = client.post("/api/projects", json={"name": "TestProj"})
    assert r.status_code == 200
    project_id = r.json()["project_id"]

    r2 = client.get(f"/api/audit/recent?project_id={project_id}")
    assert r2.status_code == 200
    events = r2.json()["events"]
    for e in events:
        assert e["project_id"] == project_id


# ── Audit /recent filter: event_type ──────────────────────────────────────────

def test_audit_filter_by_event_type(client):
    full_pipeline(client)
    # At minimum "upload" events exist
    r = client.get("/api/audit/recent?event_type=upload")
    assert r.status_code == 200
    events = r.json()["events"]
    assert len(events) > 0
    for e in events:
        assert e["event_type"] == "upload"


def test_audit_filter_event_type_nonexistent(client):
    upload(client)
    r = client.get("/api/audit/recent?event_type=nonexistent_event_type_xyz")
    assert r.status_code == 200
    assert r.json()["total"] == 0


# ── Audit /recent max limit ────────────────────────────────────────────────────

def test_audit_enforces_max_limit(client):
    for _ in range(5):
        upload(client)
    # Request more than max (200); response should cap at available events, not crash
    r = client.get("/api/audit/recent?limit=9999")
    assert r.status_code == 200
    assert len(r.json()["events"]) <= 200


def test_audit_limit_respected(client):
    for _ in range(5):
        upload(client)
    r = client.get("/api/audit/recent?limit=2")
    assert r.status_code == 200
    assert len(r.json()["events"]) <= 2


# ── GET /api/documents/{document_id}/audit ────────────────────────────────────

def test_document_audit_endpoint_exists(client):
    doc_id = upload(client)
    r = client.get(f"/api/documents/{doc_id}/audit")
    assert r.status_code == 200


def test_document_audit_returns_only_this_document(client):
    doc_a = upload(client, "a.md")
    doc_b = upload(client, "b.md")

    r = client.get(f"/api/documents/{doc_a}/audit")
    assert r.status_code == 200
    events = r.json()["events"]
    assert len(events) > 0
    for e in events:
        assert e["document_id"] == doc_a


def test_document_audit_not_found(client):
    r = client.get("/api/documents/no-such-doc/audit")
    assert r.status_code == 404


def test_document_audit_response_schema(client):
    doc_id = upload(client)
    r = client.get(f"/api/documents/{doc_id}/audit")
    data = r.json()
    assert "total" in data
    assert "events" in data
    event = data["events"][0]
    for field in ["id", "event_type", "document_id", "created_at"]:
        assert field in event, f"Missing field: {field}"


def test_document_audit_after_full_pipeline(client):
    doc_id = full_pipeline(client)
    r = client.get(f"/api/documents/{doc_id}/audit")
    assert r.status_code == 200
    assert r.json()["total"] > 1  # multiple pipeline stages emit events


# ── payload_id field in AuditEventItem ───────────────────────────────────────

def test_audit_event_item_has_payload_id_field(client):
    upload(client)
    r = client.get("/api/audit/recent")
    assert r.status_code == 200
    event = r.json()["events"][0]
    assert "payload_id" in event
