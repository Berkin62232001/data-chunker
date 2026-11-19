import hashlib
import io
import json


# ── helpers ───────────────────────────────────────────────────────────────────

def upload(client, content: bytes, filename: str, ct: str = "application/octet-stream") -> str:
    r = client.post("/api/files/upload", files={"file": (filename, io.BytesIO(content), ct)})
    assert r.status_code == 200, r.text
    return r.json()["document_id"]


def full_chain_and_convert(client, content: bytes, filename: str) -> str:
    doc_id = upload(client, content, filename)
    assert client.get(f"/api/files/{doc_id}/profile").status_code == 200
    assert client.get(f"/api/files/{doc_id}/pipeline").status_code == 200
    assert client.post(f"/api/files/{doc_id}/convert").status_code == 200
    return doc_id


def read_chunks(settings, doc_id: str):
    jsonl = (settings.chunks_dir / doc_id / "chunks.jsonl").read_text(encoding="utf-8")
    return [json.loads(l) for l in jsonl.strip().splitlines() if l.strip()]


# ── heading-aware splitting ───────────────────────────────────────────────────

def test_heading_boundaries_create_separate_chunks(client):
    md = (
        "# Introduction\n\nFirst section content here.\n\n"
        "# Methods\n\nSecond section content here.\n\n"
        "# Results\n\nThird section content here.\n"
    )
    doc_id = full_chain_and_convert(client, md.encode(), "doc.md")
    r = client.post(f"/api/files/{doc_id}/chunk")
    assert r.status_code == 200
    assert r.json()["manifest"]["total_chunks"] >= 3


def test_section_path_tracks_heading_hierarchy(client):
    md = (
        "# Title\n\nIntro paragraph.\n\n"
        "## Chapter One\n\nChapter content.\n\n"
        "### Section 1.1\n\nDeep content.\n"
    )
    doc_id = full_chain_and_convert(client, md.encode(), "doc.md")
    client.post(f"/api/files/{doc_id}/chunk")
    from core.config import settings
    chunks = read_chunks(settings, doc_id)

    # Find chunk that contains "Deep content"
    deep = [c for c in chunks if "Deep content" in c["text"]]
    assert deep, "No chunk found with deep content"
    assert "Title" in deep[0]["section_path"]
    assert "Chapter One" in deep[0]["section_path"]
    assert "Section 1.1" in deep[0]["section_path"]


# ── code block preservation ───────────────────────────────────────────────────

def test_code_block_not_split(client):
    md = (
        "# Code Example\n\n"
        "Some intro text.\n\n"
        "```python\n"
        "def hello():\n"
        "    print('hello world')\n"
        "    return True\n"
        "```\n\n"
        "Some text after the code block.\n"
    )
    doc_id = full_chain_and_convert(client, md.encode(), "code.md")
    client.post(f"/api/files/{doc_id}/chunk")
    from core.config import settings
    chunks = read_chunks(settings, doc_id)

    for chunk in chunks:
        text = chunk["text"]
        fence_count = text.count("```")
        assert fence_count % 2 == 0, (
            f"Chunk has unmatched code fence ({fence_count} backticks): {text[:120]!r}"
        )


def test_code_block_content_type(client):
    md = "# Snippet\n\n```python\nprint('hello')\n```\n"
    doc_id = full_chain_and_convert(client, md.encode(), "code.md")
    client.post(f"/api/files/{doc_id}/chunk")
    from core.config import settings
    chunks = read_chunks(settings, doc_id)
    code_chunks = [c for c in chunks if "```" in c["text"]]
    assert code_chunks, "No chunk with code found"
    # A chunk containing only a code block (plus heading) should be typed "code"
    assert any(c["content_type"] == "code" for c in code_chunks)


# ── table preservation ────────────────────────────────────────────────────────

def test_table_stays_in_single_chunk(client):
    table = (
        "| Name  | Score |\n"
        "|-------|-------|\n"
        "| Alice |   95  |\n"
        "| Bob   |   87  |\n"
        "| Carol |   92  |\n"
    )
    md = f"# Results\n\n{table}\n\nSummary follows.\n"
    doc_id = full_chain_and_convert(client, md.encode(), "table.md")
    client.post(f"/api/files/{doc_id}/chunk")
    from core.config import settings
    chunks = read_chunks(settings, doc_id)

    # Every row of the table must appear in the same chunk
    table_chunks = [
        c for c in chunks
        if "Alice" in c["text"] and "Bob" in c["text"] and "Carol" in c["text"]
    ]
    assert len(table_chunks) >= 1, "Table rows were split across chunks"


# ── SHA-256 integrity ─────────────────────────────────────────────────────────

def test_chunk_sha256_matches_text(client):
    md = "# Verify\n\nHash me correctly.\n\n## Sub\n\nAnd this too.\n"
    doc_id = full_chain_and_convert(client, md.encode(), "doc.md")
    client.post(f"/api/files/{doc_id}/chunk")
    from core.config import settings
    chunks = read_chunks(settings, doc_id)
    for chunk in chunks:
        expected = hashlib.sha256(chunk["text"].encode("utf-8")).hexdigest()
        assert chunk["sha256"] == expected, f"SHA-256 mismatch for chunk {chunk['chunk_index']}"


# ── JSONL validity ────────────────────────────────────────────────────────────

def test_jsonl_every_line_valid_json(client):
    md = "# A\n\nOne.\n\n## B\n\nTwo.\n\n## C\n\nThree.\n"
    doc_id = full_chain_and_convert(client, md.encode(), "doc.md")
    client.post(f"/api/files/{doc_id}/chunk")
    from core.config import settings
    jsonl_path = settings.chunks_dir / doc_id / "chunks.jsonl"
    for i, line in enumerate(jsonl_path.read_text().splitlines()):
        if not line.strip():
            continue
        obj = json.loads(line)  # raises if invalid
        for field in [
            "chunk_id", "document_id", "document_version", "section_path",
            "chunk_index", "content_type", "text",
            "char_count", "estimated_tokens", "sha256",
        ]:
            assert field in obj, f"Line {i} missing field: {field}"


def test_jsonl_chunk_indices_are_sequential(client):
    md = "# A\n\nFirst.\n\n# B\n\nSecond.\n\n# C\n\nThird.\n"
    doc_id = full_chain_and_convert(client, md.encode(), "doc.md")
    client.post(f"/api/files/{doc_id}/chunk")
    from core.config import settings
    chunks = read_chunks(settings, doc_id)
    indices = [c["chunk_index"] for c in chunks]
    assert indices == list(range(len(chunks))), f"Indices not sequential: {indices}"


# ── manifest ──────────────────────────────────────────────────────────────────

def test_manifest_fields_correct(client):
    md = "# Title\n\nSome content here.\n"
    doc_id = full_chain_and_convert(client, md.encode(), "doc.md")
    r = client.post(f"/api/files/{doc_id}/chunk")
    assert r.status_code == 200
    m = r.json()["manifest"]
    assert m["document_id"] == doc_id
    assert m["total_chunks"] >= 1
    assert m["total_estimated_tokens"] > 0
    assert m["average_chunk_tokens"] > 0
    assert m["chunking_strategy"] == "heading_aware"
    assert len(m["source_document_md_sha256"]) == 64


def test_manifest_source_sha256_matches_document_md(client):
    md = "# Doc\n\nContent to hash.\n"
    doc_id = full_chain_and_convert(client, md.encode(), "doc.md")
    client.post(f"/api/files/{doc_id}/chunk")
    from core.config import settings
    doc_text = (settings.converted_dir / doc_id / "document.md").read_text(encoding="utf-8")
    expected_sha = hashlib.sha256(doc_text.encode("utf-8")).hexdigest()
    from core.config import settings as s
    manifest = json.loads((s.chunks_dir / doc_id / "chunk_manifest.json").read_text())
    assert manifest["source_document_md_sha256"] == expected_sha


# ── document.md is not modified ───────────────────────────────────────────────

def test_chunking_does_not_modify_document_md(client):
    md = "# Title\n\nOriginal content.\n"
    doc_id = full_chain_and_convert(client, md.encode(), "doc.md")
    from core.config import settings
    original = (settings.converted_dir / doc_id / "document.md").read_text(encoding="utf-8")
    client.post(f"/api/files/{doc_id}/chunk")
    after = (settings.converted_dir / doc_id / "document.md").read_text(encoding="utf-8")
    assert original == after


# ── endpoints ─────────────────────────────────────────────────────────────────

def test_chunk_requires_conversion_first(client):
    doc_id = upload(client, b"hello world", "doc.md")
    r = client.post(f"/api/files/{doc_id}/chunk")
    assert r.status_code == 404


def test_get_chunks_before_chunking_returns_404(client):
    doc_id = full_chain_and_convert(client, b"# Test\n\nContent.\n", "doc.md")
    r = client.get(f"/api/files/{doc_id}/chunks")
    assert r.status_code == 404


def test_get_chunks_after_chunking(client):
    doc_id = full_chain_and_convert(client, b"# Test\n\nContent.\n", "doc.md")
    client.post(f"/api/files/{doc_id}/chunk")
    r = client.get(f"/api/files/{doc_id}/chunks")
    assert r.status_code == 200
    data = r.json()
    assert data["document_id"] == doc_id
    assert data["manifest"]["total_chunks"] >= 1
    assert isinstance(data["chunks_preview"], list)


def test_chunk_response_includes_preview(client):
    md = "# Section\n\nPreview text here.\n"
    doc_id = full_chain_and_convert(client, md.encode(), "doc.md")
    r = client.post(f"/api/files/{doc_id}/chunk")
    assert r.status_code == 200
    previews = r.json()["chunks_preview"]
    assert len(previews) >= 1
    assert "text_preview" in previews[0]
    assert previews[0]["text_preview"]  # non-empty
