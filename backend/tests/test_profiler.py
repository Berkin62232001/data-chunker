import io
import json

import pytest


# ── helpers ──────────────────────────────────────────────────────────────────

def upload(client, content: bytes, filename: str, content_type: str = "application/octet-stream") -> str:
    response = client.post(
        "/api/files/upload",
        files={"file": (filename, io.BytesIO(content), content_type)},
    )
    assert response.status_code == 200, response.text
    return response.json()["document_id"]


def make_blank_pdf() -> bytes:
    """Creates a valid single-page blank PDF using pypdf."""
    import io as _io
    import pypdf
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=612, height=792)
    buf = _io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


# ── profile field coverage ────────────────────────────────────────────────────

def test_profile_contains_required_fields(client):
    doc_id = upload(client, b"hello world", "notes.txt")
    r = client.get(f"/api/files/{doc_id}/profile")
    assert r.status_code == 200
    data = r.json()
    for field in [
        "document_id", "original_filename", "stored_filename", "extension",
        "size_bytes", "category", "requires_ocr", "recommended_pipeline", "profiled_at",
        "has_text_layer", "scanned_like", "extracted_text_char_count",
        "ocr_supported", "ocr_reason",
    ]:
        assert field in data, f"Missing field: {field}"


# ── category + pipeline routing ───────────────────────────────────────────────

def test_profile_csv(client):
    doc_id = upload(client, b"col1,col2\nval1,val2\n", "data.csv", "text/csv")
    r = client.get(f"/api/files/{doc_id}/profile")
    assert r.status_code == 200
    p = r.json()
    assert p["category"] == "csv"
    assert p["content_type"] == "tabular"
    assert p["requires_ocr"] is False
    assert p["recommended_pipeline"] == "tabular_parser"


def test_profile_xlsx(client):
    doc_id = upload(client, b"fake xlsx content", "sheet.xlsx")
    r = client.get(f"/api/files/{doc_id}/profile")
    assert r.status_code == 200
    p = r.json()
    assert p["category"] == "xlsx"
    assert p["content_type"] == "tabular"
    assert p["recommended_pipeline"] == "tabular_parser"


def test_profile_txt(client):
    doc_id = upload(client, b"Hello world\n", "notes.txt", "text/plain")
    r = client.get(f"/api/files/{doc_id}/profile")
    assert r.status_code == 200
    p = r.json()
    assert p["category"] == "txt"
    assert p["requires_ocr"] is False
    assert p["recommended_pipeline"] == "plaintext_passthrough"
    assert p["page_count"] is None


def test_profile_markdown(client):
    doc_id = upload(client, b"# Title\nBody text\n", "readme.md", "text/markdown")
    r = client.get(f"/api/files/{doc_id}/profile")
    assert r.status_code == 200
    p = r.json()
    assert p["category"] == "markdown"
    assert p["recommended_pipeline"] == "plaintext_passthrough"


def test_profile_image_requires_ocr(client):
    doc_id = upload(client, b"fake png bytes for test", "photo.png", "image/png")
    r = client.get(f"/api/files/{doc_id}/profile")
    assert r.status_code == 200
    p = r.json()
    assert p["category"] == "image"
    assert p["requires_ocr"] is True
    assert p["recommended_pipeline"] == "ocr_pipeline"


# ── PDF-specific profiling ────────────────────────────────────────────────────

def test_profile_pdf_blank_page(client):
    pdf_bytes = make_blank_pdf()
    doc_id = upload(client, pdf_bytes, "blank.pdf", "application/pdf")
    r = client.get(f"/api/files/{doc_id}/profile")
    assert r.status_code == 200
    p = r.json()
    assert p["category"] == "pdf"
    assert p["page_count"] == 1
    assert p["text_extractable"] is False
    assert p["requires_ocr"] is True
    assert p["has_text_layer"] is False
    assert p["scanned_like"] is True
    assert p["extracted_text_char_count"] == 0
    assert p["ocr_supported"] is True
    assert p["recommended_pipeline"] == "ocr_pdf"


def test_profile_pdf_text_layer_does_not_require_ocr(client, monkeypatch):
    from services import document_profiler

    monkeypatch.setattr(
        document_profiler,
        "_profile_pdf",
        lambda path: {
            "page_count": 2,
            "text_extractable": True,
            "has_text_layer": True,
            "scanned_like": False,
            "extracted_text_char_count": 500,
            "requires_ocr": False,
            "ocr_reason": None,
        },
    )

    doc_id = upload(client, b"%PDF fake", "text-layer.pdf", "application/pdf")
    r = client.get(f"/api/files/{doc_id}/profile")

    assert r.status_code == 200
    p = r.json()
    assert p["requires_ocr"] is False
    assert p["has_text_layer"] is True
    assert p["scanned_like"] is False
    assert p["extracted_text_char_count"] == 500


def test_profile_pdf_low_text_marks_scanned_like(client, monkeypatch):
    from services import document_profiler

    monkeypatch.setattr(
        document_profiler,
        "_profile_pdf",
        lambda path: {
            "page_count": 3,
            "text_extractable": False,
            "has_text_layer": True,
            "scanned_like": True,
            "extracted_text_char_count": 30,
            "requires_ocr": True,
            "ocr_reason": "PDF has very little extractable text per page and appears scanned or image-heavy.",
        },
    )

    doc_id = upload(client, b"%PDF fake", "low-text.pdf", "application/pdf")
    r = client.get(f"/api/files/{doc_id}/profile")

    assert r.status_code == 200
    p = r.json()
    assert p["requires_ocr"] is True
    assert p["has_text_layer"] is True
    assert p["scanned_like"] is True
    assert "very little" in p["ocr_reason"]


# ── edge cases ────────────────────────────────────────────────────────────────

def test_profile_not_found(client):
    r = client.get("/api/files/does-not-exist-id/profile")
    assert r.status_code == 404


def test_profile_is_cached(client):
    from core.config import settings

    doc_id = upload(client, b"a,b\n1,2\n", "test.csv", "text/csv")

    r1 = client.get(f"/api/files/{doc_id}/profile")
    assert r1.status_code == 200

    profile_path = settings.raw_uploads_dir / doc_id / "profile.json"
    assert profile_path.exists()

    r2 = client.get(f"/api/files/{doc_id}/profile")
    assert r2.status_code == 200
    # Cached: profiled_at is identical across calls
    assert r1.json()["profiled_at"] == r2.json()["profiled_at"]
