"""Tests for GET /api/dashboard/stats"""
import io


_SAMPLE = b"# Test\n\nHello.\n"


def upload(client, filename: str = "doc.md") -> str:
    r = client.post(
        "/api/files/upload",
        files={"file": (filename, io.BytesIO(_SAMPLE), "text/plain")},
    )
    assert r.status_code == 200, r.text
    return r.json()["document_id"]


def test_dashboard_stats_empty(client):
    r = client.get("/api/dashboard/stats")
    assert r.status_code == 200
    data = r.json()
    assert data["total_documents"] == 0
    assert data["total_projects"] == 0
    assert data["completed_documents"] == 0
    assert data["documents_in_progress"] == 0


def test_dashboard_stats_counts_documents(client):
    upload(client, "a.md")
    upload(client, "b.md")
    r = client.get("/api/dashboard/stats")
    assert r.status_code == 200
    assert r.json()["total_documents"] == 2


def test_dashboard_stats_counts_projects(client):
    client.post("/api/projects", json={"name": "P1"})
    client.post("/api/projects", json={"name": "P2"})
    r = client.get("/api/dashboard/stats")
    assert r.json()["total_projects"] == 2


def test_dashboard_stats_completed_documents(client):
    doc_id = upload(client)
    client.get(f"/api/files/{doc_id}/profile")
    client.get(f"/api/files/{doc_id}/pipeline")
    client.post(f"/api/files/{doc_id}/convert")
    client.post(f"/api/files/{doc_id}/chunk")

    r = client.get("/api/dashboard/stats")
    assert r.json()["completed_documents"] == 1


def test_dashboard_stats_schema(client):
    r = client.get("/api/dashboard/stats")
    data = r.json()
    for field in ["total_documents", "total_projects", "completed_documents", "documents_in_progress"]:
        assert field in data, f"Missing field: {field}"
        assert isinstance(data[field], int)
