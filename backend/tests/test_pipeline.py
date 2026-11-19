import io


# ── helpers ──────────────────────────────────────────────────────────────────

def upload(client, content: bytes, filename: str, content_type: str = "application/octet-stream") -> str:
    r = client.post(
        "/api/files/upload",
        files={"file": (filename, io.BytesIO(content), content_type)},
    )
    assert r.status_code == 200, r.text
    return r.json()["document_id"]


def profile_then_pipeline(client, doc_id: str):
    client.get(f"/api/files/{doc_id}/profile")
    return client.get(f"/api/files/{doc_id}/pipeline")


def make_blank_pdf() -> bytes:
    import io as _io
    import pypdf
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=612, height=792)
    buf = _io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


# ── required fields ───────────────────────────────────────────────────────────

def test_pipeline_contains_required_fields(client):
    doc_id = upload(client, b"hello world", "notes.txt")
    r = profile_then_pipeline(client, doc_id)
    assert r.status_code == 200
    p = r.json()
    for field in [
        "document_id", "selected_pipeline", "output_format", "output_artifacts",
        "llm_send_format_claude", "llm_send_format_openai_gemini",
        "reasons", "warnings", "decided_at",
    ]:
        assert field in p, f"Missing field: {field}"


# ── pipeline routing by category ──────────────────────────────────────────────

def test_pipeline_txt(client):
    doc_id = upload(client, b"Hello world", "notes.txt")
    r = profile_then_pipeline(client, doc_id)
    assert r.status_code == 200
    assert r.json()["selected_pipeline"] == "text_to_markdown_jsonl"


def test_pipeline_markdown(client):
    doc_id = upload(client, b"# Title\nBody\n", "readme.md")
    r = profile_then_pipeline(client, doc_id)
    assert r.status_code == 200
    assert r.json()["selected_pipeline"] == "text_to_markdown_jsonl"


def test_pipeline_csv(client):
    doc_id = upload(client, b"col1,col2\nval1,val2\n", "data.csv", "text/csv")
    r = profile_then_pipeline(client, doc_id)
    assert r.status_code == 200
    p = r.json()
    assert p["selected_pipeline"] == "tabular_to_structured_json_summary"
    assert p["output_format"] == "structured_json_summary"


def test_pipeline_xlsx(client):
    doc_id = upload(client, b"fake xlsx content", "sheet.xlsx")
    r = profile_then_pipeline(client, doc_id)
    assert r.status_code == 200
    assert r.json()["selected_pipeline"] == "tabular_to_structured_json_summary"


def test_pipeline_html(client):
    doc_id = upload(client, b"<html><body>Hello</body></html>", "page.html")
    r = profile_then_pipeline(client, doc_id)
    assert r.status_code == 200
    assert r.json()["selected_pipeline"] == "html_to_clean_markdown_jsonl"


def test_pipeline_image_ocr(client):
    doc_id = upload(client, b"fake png bytes", "photo.png", "image/png")
    r = profile_then_pipeline(client, doc_id)
    assert r.status_code == 200
    p = r.json()
    assert p["selected_pipeline"] == "image_ocr_to_markdown_jsonl"
    assert len(p["reasons"]) > 0


def test_pipeline_pdf_blank_routes_to_ocr(client):
    doc_id = upload(client, make_blank_pdf(), "scan.pdf", "application/pdf")
    r = profile_then_pipeline(client, doc_id)
    assert r.status_code == 200
    p = r.json()
    assert p["selected_pipeline"] == "ocr_pdf_to_markdown_jsonl"
    assert p["output_format"] == "markdown_jsonl"
    assert len(p["reasons"]) > 0


# ── reasons and warnings content ─────────────────────────────────────────────

def test_pipeline_csv_reason_mentions_tabular(client):
    doc_id = upload(client, b"a,b\n1,2\n", "data.csv", "text/csv")
    r = profile_then_pipeline(client, doc_id)
    reasons_text = " ".join(r.json()["reasons"]).lower()
    assert "tabular" in reasons_text or "csv" in reasons_text


def test_pipeline_image_reason_mentions_ocr(client):
    doc_id = upload(client, b"fake image bytes", "photo.jpg", "image/jpeg")
    r = profile_then_pipeline(client, doc_id)
    assert "ocr" in " ".join(r.json()["reasons"]).lower()


# ── default output artifacts ──────────────────────────────────────────────────

def test_pipeline_default_artifacts(client):
    doc_id = upload(client, b"hello", "notes.txt")
    r = profile_then_pipeline(client, doc_id)
    artifacts = r.json()["output_artifacts"]
    assert "document.md" in artifacts
    assert "chunks.jsonl" in artifacts
    assert "metadata.json" in artifacts
    assert "extraction_report.json" in artifacts


# ── LLM send formats ──────────────────────────────────────────────────────────

def test_pipeline_llm_formats(client):
    doc_id = upload(client, b"hello", "notes.txt")
    r = profile_then_pipeline(client, doc_id)
    p = r.json()
    assert p["llm_send_format_claude"] == "xml_wrapped_markdown"
    assert p["llm_send_format_openai_gemini"] == "markdown_with_json_metadata"


# ── caching ───────────────────────────────────────────────────────────────────

def test_pipeline_is_cached(client):
    from core.config import settings

    doc_id = upload(client, b"a,b\n1,2\n", "data.csv", "text/csv")
    client.get(f"/api/files/{doc_id}/profile")

    r1 = client.get(f"/api/files/{doc_id}/pipeline")
    assert r1.status_code == 200

    assert (settings.raw_uploads_dir / doc_id / "pipeline_decision.json").exists()

    r2 = client.get(f"/api/files/{doc_id}/pipeline")
    assert r2.json()["decided_at"] == r1.json()["decided_at"]


# ── error cases ───────────────────────────────────────────────────────────────

def test_pipeline_without_profile_returns_404(client):
    doc_id = upload(client, b"hello", "notes.txt")
    # Deliberately skip profile call
    r = client.get(f"/api/files/{doc_id}/pipeline")
    assert r.status_code == 404


def test_pipeline_unknown_document_returns_404(client):
    r = client.get("/api/files/does-not-exist/pipeline")
    assert r.status_code == 404
