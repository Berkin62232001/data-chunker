import io


_LARGE_MD = "\n\n".join(
    f"# Topic {i}\n\nThis section covers topic {i} in great detail with extensive content about the subject matter.\n"
    for i in range(20)
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


def test_budget_limit(client):
    """Budget prevents total tokens from exceeding DEFAULT_CONTEXT_TOKEN_BUDGET."""
    doc_id = full_pipeline(client, _LARGE_MD.encode(), "doc.md")
    r = client.post(
        f"/api/files/{doc_id}/prepare-llm-payload",
        json={"query": "topic", "top_k": 20},
    )
    assert r.status_code == 200
    data = r.json()
    assert "token_budget" in data
    budget_info = data["token_budget"]
    assert budget_info["estimated_context_tokens"] <= 8000
    assert data["chunks_used"] == budget_info["selected_chunk_count"]
    assert data["total_estimated_tokens"] == budget_info["estimated_context_tokens"]


def test_skipped_chunks(client):
    """estimate-context reports skipped chunks when budget is tight."""
    doc_id = full_pipeline(client, _LARGE_MD.encode(), "doc.md")
    r = client.post(
        f"/api/files/{doc_id}/estimate-context",
        json={"query": "topic", "top_k": 20, "budget": 50},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["selected_chunk_count"] + data["skipped_chunks_due_to_budget"] <= 20
    assert data["skipped_chunks_due_to_budget"] >= 0
    assert data["estimated_context_tokens"] <= 50


def test_provider_specific_budget(client):
    """A larger custom budget selects at least as many chunks as a smaller one."""
    doc_id = full_pipeline(client, _LARGE_MD.encode(), "doc.md")
    r_small = client.post(
        f"/api/files/{doc_id}/estimate-context",
        json={"query": "topic", "top_k": 10, "budget": 100},
    )
    r_large = client.post(
        f"/api/files/{doc_id}/estimate-context",
        json={"query": "topic", "top_k": 10, "budget": 10000},
    )
    assert r_small.status_code == 200
    assert r_large.status_code == 200
    assert r_small.json()["selected_chunk_count"] <= r_large.json()["selected_chunk_count"]
    assert r_small.json()["budget_used"] == 100
    assert r_large.json()["budget_used"] == 10000


def test_no_chunks_selected(client):
    """A budget smaller than any single chunk results in zero selected chunks."""
    doc_id = full_pipeline(client, _LARGE_MD.encode(), "doc.md")
    r = client.post(
        f"/api/files/{doc_id}/estimate-context",
        json={"query": "topic", "top_k": 5, "budget": 1},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["selected_chunk_count"] == 0
    assert data["estimated_context_tokens"] == 0
    assert data["skipped_chunks_due_to_budget"] >= 0
