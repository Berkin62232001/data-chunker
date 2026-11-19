import io


_DOC_A = (
    "# Introduction\n\nThis document covers Python programming basics.\n\n"
    "# Functions\n\nFunctions are reusable blocks of code in Python.\n"
)
_DOC_B = (
    "# Overview\n\nThis document covers JavaScript fundamentals.\n\n"
    "# Variables\n\nVariables store data values in JavaScript.\n"
)


def full_pipeline(client, content: bytes, filename: str) -> str:
    r = client.post("/api/files/upload", files={"file": (filename, io.BytesIO(content), "text/plain")})
    assert r.status_code == 200, r.text
    doc_id = r.json()["document_id"]
    assert client.get(f"/api/files/{doc_id}/profile").status_code == 200
    assert client.get(f"/api/files/{doc_id}/pipeline").status_code == 200
    assert client.post(f"/api/files/{doc_id}/convert").status_code == 200
    assert client.post(f"/api/files/{doc_id}/chunk").status_code == 200
    return doc_id


# ── project creation ──────────────────────────────────────────────────────────

def test_create_project(client):
    r = client.post("/api/projects", json={"name": "My Project"})
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "My Project"
    assert "project_id" in data
    assert data["document_ids"] == []
    assert "created_at" in data


def test_create_project_empty_name_rejected(client):
    r = client.post("/api/projects", json={"name": "   "})
    assert r.status_code == 422


def test_get_project(client):
    r = client.post("/api/projects", json={"name": "Test"})
    project_id = r.json()["project_id"]
    r2 = client.get(f"/api/projects/{project_id}")
    assert r2.status_code == 200
    assert r2.json()["project_id"] == project_id


def test_get_nonexistent_project_returns_404(client):
    r = client.get("/api/projects/does-not-exist")
    assert r.status_code == 404


# ── adding documents ──────────────────────────────────────────────────────────

def test_add_document(client):
    doc_id = full_pipeline(client, _DOC_A.encode(), "python.md")
    r = client.post("/api/projects", json={"name": "P"})
    project_id = r.json()["project_id"]

    r2 = client.post(f"/api/projects/{project_id}/add-document", json={"document_id": doc_id})
    assert r2.status_code == 200
    assert doc_id in r2.json()["document_ids"]


def test_add_document_idempotent(client):
    doc_id = full_pipeline(client, _DOC_A.encode(), "python.md")
    r = client.post("/api/projects", json={"name": "P"})
    project_id = r.json()["project_id"]

    client.post(f"/api/projects/{project_id}/add-document", json={"document_id": doc_id})
    r2 = client.post(f"/api/projects/{project_id}/add-document", json={"document_id": doc_id})
    assert r2.status_code == 200
    assert r2.json()["document_ids"].count(doc_id) == 1


def test_add_unchunked_document_rejected(client):
    # Upload but don't chunk
    r = client.post(
        "/api/files/upload",
        files={"file": ("x.md", io.BytesIO(b"# Hi\n\nContent.\n"), "text/plain")},
    )
    doc_id = r.json()["document_id"]
    proj_r = client.post("/api/projects", json={"name": "P"})
    project_id = proj_r.json()["project_id"]

    r2 = client.post(f"/api/projects/{project_id}/add-document", json={"document_id": doc_id})
    assert r2.status_code == 422


def test_add_document_to_nonexistent_project(client):
    doc_id = full_pipeline(client, _DOC_A.encode(), "python.md")
    r = client.post("/api/projects/ghost/add-document", json={"document_id": doc_id})
    assert r.status_code == 404


# ── multi-document search ─────────────────────────────────────────────────────

def test_search_across_documents(client):
    doc_a = full_pipeline(client, _DOC_A.encode(), "python.md")
    doc_b = full_pipeline(client, _DOC_B.encode(), "javascript.md")

    r = client.post("/api/projects", json={"name": "Multi"})
    project_id = r.json()["project_id"]
    client.post(f"/api/projects/{project_id}/add-document", json={"document_id": doc_a})
    client.post(f"/api/projects/{project_id}/add-document", json={"document_id": doc_b})

    r2 = client.post(f"/api/projects/{project_id}/search", json={"query": "programming"})
    assert r2.status_code == 200
    data = r2.json()
    assert data["documents_searched"] == 2
    assert "results" in data
    assert data["total_chunks_searched"] > 0


def test_search_result_has_source_fields(client):
    doc_a = full_pipeline(client, _DOC_A.encode(), "python.md")
    r = client.post("/api/projects", json={"name": "P"})
    project_id = r.json()["project_id"]
    client.post(f"/api/projects/{project_id}/add-document", json={"document_id": doc_a})

    r2 = client.post(f"/api/projects/{project_id}/search", json={"query": "Python"})
    assert r2.status_code == 200
    results = r2.json()["results"]
    if results:
        item = results[0]
        assert "document_id" in item
        assert "source_filename" in item
        assert item["source_filename"] == "python.md"
        assert item["document_id"] == doc_a


def test_search_results_ranked_by_score(client):
    doc_a = full_pipeline(client, _DOC_A.encode(), "python.md")
    doc_b = full_pipeline(client, _DOC_B.encode(), "javascript.md")
    r = client.post("/api/projects", json={"name": "P"})
    project_id = r.json()["project_id"]
    client.post(f"/api/projects/{project_id}/add-document", json={"document_id": doc_a})
    client.post(f"/api/projects/{project_id}/add-document", json={"document_id": doc_b})

    r2 = client.post(f"/api/projects/{project_id}/search", json={"query": "Python functions"})
    results = r2.json()["results"]
    scores = [item["score"] for item in results]
    assert scores == sorted(scores, reverse=True)


def test_search_empty_project_returns_empty(client):
    r = client.post("/api/projects", json={"name": "Empty"})
    project_id = r.json()["project_id"]
    r2 = client.post(f"/api/projects/{project_id}/search", json={"query": "anything"})
    assert r2.status_code == 200
    assert r2.json()["results"] == []
    assert r2.json()["documents_searched"] == 0


# ── project-level payload / ask ───────────────────────────────────────────────

def test_project_ask_returns_answer(client):
    doc_a = full_pipeline(client, _DOC_A.encode(), "python.md")
    doc_b = full_pipeline(client, _DOC_B.encode(), "javascript.md")
    r = client.post("/api/projects", json={"name": "P"})
    project_id = r.json()["project_id"]
    client.post(f"/api/projects/{project_id}/add-document", json={"document_id": doc_a})
    client.post(f"/api/projects/{project_id}/add-document", json={"document_id": doc_b})

    r2 = client.post(f"/api/projects/{project_id}/ask", json={"query": "programming"})
    assert r2.status_code == 200
    data = r2.json()
    for field in ["answer", "provider", "project_id", "chunks_used", "document_count", "estimated_context_tokens"]:
        assert field in data, f"Missing field: {field}"
    assert data["project_id"] == project_id
    assert data["provider"] == "mock"


def test_project_ask_empty_project_rejected(client):
    r = client.post("/api/projects", json={"name": "Empty"})
    project_id = r.json()["project_id"]
    r2 = client.post(f"/api/projects/{project_id}/ask", json={"query": "anything"})
    assert r2.status_code == 422


def test_project_ask_document_count(client):
    doc_a = full_pipeline(client, _DOC_A.encode(), "python.md")
    doc_b = full_pipeline(client, _DOC_B.encode(), "javascript.md")
    r = client.post("/api/projects", json={"name": "P"})
    project_id = r.json()["project_id"]
    client.post(f"/api/projects/{project_id}/add-document", json={"document_id": doc_a})
    client.post(f"/api/projects/{project_id}/add-document", json={"document_id": doc_b})

    r2 = client.post(f"/api/projects/{project_id}/ask", json={"query": "programming language"})
    assert r2.status_code == 200
    assert r2.json()["document_count"] >= 1
