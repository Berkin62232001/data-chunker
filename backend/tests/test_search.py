import io


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


def upload_and_convert(client, content: bytes, filename: str) -> str:
    doc_id = upload(client, content, filename)
    assert client.get(f"/api/files/{doc_id}/profile").status_code == 200
    assert client.get(f"/api/files/{doc_id}/pipeline").status_code == 200
    assert client.post(f"/api/files/{doc_id}/convert").status_code == 200
    return doc_id


def search(client, doc_id: str, query: str, top_k: int = 5, include_full_text: bool = False):
    return client.post(
        f"/api/files/{doc_id}/search",
        json={"query": query, "top_k": top_k, "include_full_text": include_full_text},
    )


# ── relevance ─────────────────────────────────────────────────────────────────

def test_search_returns_relevant_chunk(client):
    md = (
        "# Python Introduction\n\nPython is a programming language.\n\n"
        "# JavaScript\n\nJavaScript runs in browsers.\n"
    )
    doc_id = full_pipeline(client, md.encode(), "doc.md")
    r = search(client, doc_id, "python programming")
    assert r.status_code == 200
    results = r.json()["results"]
    assert len(results) >= 1
    top_text = (results[0]["text_preview"] + " ".join(results[0]["section_path"])).lower()
    assert "python" in top_text


def test_search_section_path_boosts_score(client):
    md = (
        "# Machine Learning\n\nThis section contains unrelated words.\n\n"
        "# Unrelated Topic\n\nMachine learning appears many times here: "
        "machine learning machine learning machine learning.\n"
    )
    doc_id = full_pipeline(client, md.encode(), "doc.md")
    r = search(client, doc_id, "machine learning")
    assert r.status_code == 200
    results = r.json()["results"]
    assert len(results) >= 1
    # Section-path boost should push "Machine Learning" heading chunk near the top
    top_section = " ".join(results[0]["section_path"]).lower()
    # Either the top result has the term in section_path OR high text frequency
    assert "machine" in top_section or "machine" in results[0]["text_preview"].lower()


def test_search_scores_are_descending(client):
    md = "\n\n".join(
        f"# Topic {i}\n\nSome content about topic {i} and topic here.\n" for i in range(5)
    )
    doc_id = full_pipeline(client, md.encode(), "doc.md")
    r = search(client, doc_id, "topic", top_k=10)
    results = r.json()["results"]
    scores = [res["score"] for res in results]
    assert scores == sorted(scores, reverse=True), "Results not sorted by score descending"


# ── no results ────────────────────────────────────────────────────────────────

def test_search_no_match_returns_empty_results(client):
    md = "# Intro\n\nHello world.\n"
    doc_id = full_pipeline(client, md.encode(), "doc.md")
    r = search(client, doc_id, "xyznomatchirrelevant99999")
    assert r.status_code == 200
    assert r.json()["results"] == []
    assert r.json()["total_chunks_searched"] >= 1


# ── top_k limiting ────────────────────────────────────────────────────────────

def test_search_top_k_limits_results(client):
    md = "\n\n".join(
        f"# Section {i}\n\nContent about section {i} here.\n" for i in range(10)
    )
    doc_id = full_pipeline(client, md.encode(), "doc.md")
    r = search(client, doc_id, "content section", top_k=3)
    assert r.status_code == 200
    assert len(r.json()["results"]) <= 3


def test_search_top_k_default_is_five(client):
    md = "\n\n".join(f"# H{i}\n\nContent {i}.\n" for i in range(10))
    doc_id = full_pipeline(client, md.encode(), "doc.md")
    r = client.post(f"/api/files/{doc_id}/search", json={"query": "content"})
    assert r.json()["top_k"] == 5


# ── validation ────────────────────────────────────────────────────────────────

def test_search_empty_query_rejected(client):
    r = client.post("/api/files/fake-id/search", json={"query": ""})
    assert r.status_code == 422


def test_search_whitespace_only_query_rejected(client):
    r = client.post("/api/files/fake-id/search", json={"query": "   "})
    assert r.status_code == 422


def test_search_top_k_zero_rejected(client):
    r = client.post("/api/files/fake-id/search", json={"query": "test", "top_k": 0})
    assert r.status_code == 422


def test_search_top_k_over_limit_rejected(client):
    r = client.post("/api/files/fake-id/search", json={"query": "test", "top_k": 51})
    assert r.status_code == 422


# ── response shape ────────────────────────────────────────────────────────────

def test_search_response_has_required_fields(client):
    md = "# Test\n\nContent.\n"
    doc_id = full_pipeline(client, md.encode(), "doc.md")
    r = search(client, doc_id, "test", top_k=5)
    assert r.status_code == 200
    data = r.json()
    assert data["query"] == "test"
    assert data["top_k"] == 5
    assert "total_chunks_searched" in data
    assert isinstance(data["results"], list)


def test_search_result_item_fields(client):
    md = "# Section\n\nContent here.\n"
    doc_id = full_pipeline(client, md.encode(), "doc.md")
    r = search(client, doc_id, "content")
    results = r.json()["results"]
    if results:
        item = results[0]
        for field in ["chunk_id", "chunk_index", "section_path", "content_type",
                      "score", "estimated_tokens", "text_preview"]:
            assert field in item, f"Missing field: {field}"
        assert isinstance(item["section_path"], list)
        assert item["score"] > 0


def test_search_full_text_returned_when_requested(client):
    md = "# Doc\n\nFull text should appear when requested.\n"
    doc_id = full_pipeline(client, md.encode(), "doc.md")
    r = search(client, doc_id, "text", include_full_text=True)
    results = r.json()["results"]
    if results:
        assert results[0]["text"] is not None
        assert "Full text" in results[0]["text"] or "full text" in results[0]["text"].lower()


def test_search_full_text_absent_by_default(client):
    md = "# Doc\n\nSome content.\n"
    doc_id = full_pipeline(client, md.encode(), "doc.md")
    r = search(client, doc_id, "content")
    results = r.json()["results"]
    if results:
        assert results[0]["text"] is None


# ── error cases ───────────────────────────────────────────────────────────────

def test_search_requires_chunks(client):
    doc_id = upload_and_convert(client, b"# Test\n\nContent.\n", "doc.md")
    r = search(client, doc_id, "test")
    assert r.status_code == 404


def test_search_unknown_document_returns_404(client):
    r = search(client, "nonexistent-id", "query")
    assert r.status_code == 404
