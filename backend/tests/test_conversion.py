import io
import json


# ── helpers ───────────────────────────────────────────────────────────────────

def upload(client, content: bytes, filename: str, content_type: str = "application/octet-stream") -> str:
    r = client.post(
        "/api/files/upload",
        files={"file": (filename, io.BytesIO(content), content_type)},
    )
    assert r.status_code == 200, r.text
    return r.json()["document_id"]


def full_chain(client, content: bytes, filename: str, content_type: str = "application/octet-stream") -> str:
    """Upload → profile → pipeline decision. Returns document_id ready for conversion."""
    doc_id = upload(client, content, filename, content_type)
    assert client.get(f"/api/files/{doc_id}/profile").status_code == 200
    assert client.get(f"/api/files/{doc_id}/pipeline").status_code == 200
    return doc_id


def make_blank_pdf() -> bytes:
    import io as _io
    import pypdf
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=612, height=792)
    buf = _io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


# ── TXT conversion ────────────────────────────────────────────────────────────

def test_convert_txt_success(client):
    doc_id = full_chain(client, b"Hello World\r\nSecond line.", "doc.txt")
    r = client.post(f"/api/files/{doc_id}/convert")
    assert r.status_code == 200
    p = r.json()
    assert p["conversion_status"] == "success"
    assert "Hello World" in p["markdown_preview"]
    assert "Second line" in p["markdown_preview"]
    assert p["report"]["success"] is True
    assert p["report"]["converter_used"] == "txt_normalizer"
    assert p["report"]["fallback_used"] is False


def test_convert_txt_normalizes_line_endings(client):
    doc_id = full_chain(client, b"line1\r\nline2\r\nline3", "file.txt")
    r = client.post(f"/api/files/{doc_id}/convert")
    assert r.status_code == 200
    assert "\r" not in r.json()["markdown_preview"]


# ── Markdown conversion ───────────────────────────────────────────────────────

def test_convert_markdown_passthrough(client):
    content = b"# Title\n\nSome **bold** text.\n\n- item one\n- item two\n"
    doc_id = full_chain(client, content, "notes.md")
    r = client.post(f"/api/files/{doc_id}/convert")
    assert r.status_code == 200
    p = r.json()
    assert p["conversion_status"] == "success"
    assert "# Title" in p["markdown_preview"]
    assert p["report"]["converter_used"] == "markdown_passthrough"
    assert p["report"]["fallback_used"] is False


# ── CSV conversion ────────────────────────────────────────────────────────────

def test_convert_csv_produces_table(client):
    csv_content = b"name,age,city\nAlice,30,London\nBob,25,Paris\n"
    doc_id = full_chain(client, csv_content, "people.csv", "text/csv")
    r = client.post(f"/api/files/{doc_id}/convert")
    assert r.status_code == 200
    p = r.json()
    assert p["conversion_status"] == "success"
    preview = p["markdown_preview"]
    assert "name" in preview
    assert "Alice" in preview
    assert "|" in preview  # Markdown table
    assert p["report"]["converter_used"] == "csv_converter"


def test_convert_csv_metadata_fields(client):
    doc_id = full_chain(client, b"a,b\n1,2\n3,4\n", "data.csv", "text/csv")
    r = client.post(f"/api/files/{doc_id}/convert")
    assert r.status_code == 200
    meta = r.json()["metadata"]
    assert meta["document_id"] == doc_id
    assert meta["original_filename"] == "data.csv"
    assert meta["selected_pipeline"] == "tabular_to_structured_json_summary"
    assert meta["estimated_character_count"] > 0
    assert meta["estimated_token_count"] == meta["estimated_character_count"] // 4
    assert "document.md" in meta["output_files"]
    assert "metadata.json" in meta["output_files"]
    assert "extraction_report.json" in meta["output_files"]


def test_convert_csv_extraction_report_fields(client):
    doc_id = full_chain(client, b"x,y\n1,2\n", "data.csv", "text/csv")
    r = client.post(f"/api/files/{doc_id}/convert")
    assert r.status_code == 200
    report = r.json()["report"]
    assert "success" in report
    assert "converter_used" in report
    assert "warnings" in report
    assert "errors" in report
    assert "fallback_used" in report


# ── PDF conversion ────────────────────────────────────────────────────────────

def test_convert_pdf_blank_uses_pypdf_fallback(client):
    doc_id = full_chain(client, make_blank_pdf(), "doc.pdf", "application/pdf")
    r = client.post(f"/api/files/{doc_id}/convert")
    assert r.status_code == 200
    p = r.json()
    # Blank PDF has no text → warnings, partial status
    assert p["conversion_status"] in ("partial", "success")
    assert p["report"]["fallback_used"] is True
    assert "pypdf" in p["report"]["converter_used"]


def test_convert_warns_when_ocr_needed_but_disabled(client):
    doc_id = full_chain(client, make_blank_pdf(), "scan.pdf", "application/pdf")
    r = client.post(f"/api/files/{doc_id}/convert")

    assert r.status_code == 200
    report = r.json()["report"]
    assert report["ocr_used"] is False
    assert report["ocr_succeeded"] is None
    assert any("Enable OCR" in warning for warning in report["warnings"])


def test_convert_uses_ocr_text_when_enabled(client, monkeypatch):
    from core.config import settings
    from models.ocr_models import OCRResult

    class FakeOCRService:
        def ocr_pdf_to_text(self, input_pdf_path, document_id, language, max_pages, timeout):
            return OCRResult(
                text="# OCR Text\n\nRecognized scanned document text.",
                provider="ocrmypdf",
                language=language,
                pages_processed=1,
                succeeded=True,
            )

    monkeypatch.setattr(settings, "ocr_enabled", True)
    monkeypatch.setattr("services.conversion_service.LocalOCRService", lambda: FakeOCRService())

    doc_id = full_chain(client, make_blank_pdf(), "scan.pdf", "application/pdf")
    r = client.post(f"/api/files/{doc_id}/convert")

    assert r.status_code == 200
    p = r.json()
    assert p["conversion_status"] == "success"
    assert "Recognized scanned document text" in p["markdown_preview"]
    assert p["report"]["converter_used"] == "ocrmypdf_ocr"
    assert p["report"]["ocr_used"] is True
    assert p["report"]["ocr_succeeded"] is True
    assert p["report"]["ocr_provider"] == "ocrmypdf"
    assert p["report"]["ocr_pages_processed"] == 1
    assert p["report"]["ocr_text_char_count"] > 0

    report_path = settings.converted_dir / doc_id / "extraction_report.json"
    report = json.loads(report_path.read_text())
    assert report["ocr_used"] is True
    assert report["ocr_provider"] == "ocrmypdf"


def test_convert_handles_ocr_failure_gracefully(client, monkeypatch):
    from core.config import settings
    from models.ocr_models import OCRResult

    class FailingOCRService:
        def ocr_pdf_to_text(self, input_pdf_path, document_id, language, max_pages, timeout):
            return OCRResult(
                provider="ocrmypdf",
                language=language,
                pages_processed=0,
                succeeded=False,
                error="OCR unavailable. Missing local command(s): ocrmypdf.",
            )

    monkeypatch.setattr(settings, "ocr_enabled", True)
    monkeypatch.setattr("services.conversion_service.LocalOCRService", lambda: FailingOCRService())

    doc_id = full_chain(client, make_blank_pdf(), "scan.pdf", "application/pdf")
    r = client.post(f"/api/files/{doc_id}/convert")

    assert r.status_code == 200
    p = r.json()
    assert p["conversion_status"] == "partial"
    assert p["report"]["ocr_used"] is False
    assert p["report"]["ocr_succeeded"] is False
    assert p["report"]["ocr_error"] == "OCR unavailable. Missing local command(s): ocrmypdf."
    assert any("OCR unavailable" in warning for warning in p["report"]["warnings"])


def test_ocr_status_endpoint_reports_disabled_and_unavailable(client, monkeypatch):
    monkeypatch.setattr("services.ocr_service.shutil.which", lambda binary: None)

    doc_id = full_chain(client, make_blank_pdf(), "scan.pdf", "application/pdf")
    r = client.get(f"/api/files/{doc_id}/ocr-status")

    assert r.status_code == 200
    data = r.json()
    assert data["document_id"] == doc_id
    assert data["ocr_enabled"] is False
    assert data["ocr_available"] is False
    assert data["requires_ocr"] is True
    assert data["ocr_supported"] is True
    assert data["provider"] == "ocrmypdf"
    assert any("OCR is disabled" in warning for warning in data["warnings"])
    assert "Missing local command" in data["error"]


# ── Image — graceful fallback ─────────────────────────────────────────────────

def test_convert_image_graceful_fallback(client):
    doc_id = full_chain(client, b"fake png bytes", "photo.png", "image/png")
    r = client.post(f"/api/files/{doc_id}/convert")
    assert r.status_code == 200
    p = r.json()
    assert p["report"]["fallback_used"] is True
    assert p["report"]["converter_used"] == "fallback_unsupported"
    # Status is partial (warning only, no error)
    assert p["conversion_status"] == "partial"


# ── Output files written to disk ──────────────────────────────────────────────

def test_convert_writes_output_files(client):
    from core.config import settings

    doc_id = full_chain(client, b"hello world", "note.txt")
    client.post(f"/api/files/{doc_id}/convert")

    out_dir = settings.converted_dir / doc_id
    assert (out_dir / "document.md").exists()
    assert (out_dir / "metadata.json").exists()
    assert (out_dir / "extraction_report.json").exists()


def test_convert_does_not_overwrite_raw(client):
    from core.config import settings

    content = b"original raw content"
    doc_id = full_chain(client, content, "note.txt")
    client.post(f"/api/files/{doc_id}/convert")

    raw_meta = json.loads(
        (settings.raw_uploads_dir / doc_id / "metadata.json").read_text()
    )
    raw_file = settings.raw_uploads_dir / doc_id / raw_meta["stored_filename"]
    assert raw_file.read_bytes() == content


# ── GET /converted endpoint ───────────────────────────────────────────────────

def test_get_converted_before_conversion_returns_404(client):
    doc_id = full_chain(client, b"hello", "note.txt")
    r = client.get(f"/api/files/{doc_id}/converted")
    assert r.status_code == 404


def test_get_converted_after_conversion_returns_result(client):
    doc_id = full_chain(client, b"# Doc\n\nContent here.", "doc.md")
    client.post(f"/api/files/{doc_id}/convert")
    r = client.get(f"/api/files/{doc_id}/converted")
    assert r.status_code == 200
    assert r.json()["document_id"] == doc_id
    assert "# Doc" in r.json()["markdown_preview"]


# ── Error cases ───────────────────────────────────────────────────────────────

def test_convert_requires_pipeline_decision(client):
    doc_id = upload(client, b"hello", "note.txt")
    # Skip profile + pipeline
    r = client.post(f"/api/files/{doc_id}/convert")
    assert r.status_code == 404


def test_convert_unknown_document_returns_404(client):
    r = client.post("/api/files/nonexistent-id/convert")
    assert r.status_code == 404
