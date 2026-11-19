import io
import json


def test_upload_txt_returns_expected_fields(client):
    content = b"Hello, world!"
    response = client.post(
        "/api/files/upload",
        files={"file": ("notes.txt", io.BytesIO(content), "text/plain")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "raw"
    assert data["original_filename"] == "notes.txt"
    assert data["stored_filename"] == "notes.txt"
    assert data["size_bytes"] == len(content)
    assert len(data["document_id"]) == 36  # UUID4


def test_upload_creates_raw_file_and_metadata(client, tmp_path, monkeypatch):
    from core.config import settings

    content = b"PDF content placeholder"
    response = client.post(
        "/api/files/upload",
        files={"file": ("report.pdf", io.BytesIO(content), "application/pdf")},
    )
    assert response.status_code == 200
    data = response.json()

    doc_dir = settings.raw_uploads_dir / data["document_id"]
    assert (doc_dir / data["stored_filename"]).exists()
    assert (doc_dir / data["stored_filename"]).read_bytes() == content

    metadata = json.loads((doc_dir / "metadata.json").read_text())
    assert metadata["document_id"] == data["document_id"]
    assert metadata["original_filename"] == "report.pdf"
    assert metadata["size_bytes"] == len(content)
    assert metadata["status"] == "raw"
    assert "uploaded_at" in metadata


def test_upload_empty_file_rejected(client):
    response = client.post(
        "/api/files/upload",
        files={"file": ("empty.txt", io.BytesIO(b""), "text/plain")},
    )
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


def test_upload_disallowed_extension_rejected(client):
    response = client.post(
        "/api/files/upload",
        files={"file": ("script.exe", io.BytesIO(b"data"), "application/octet-stream")},
    )
    assert response.status_code == 400
    assert "not allowed" in response.json()["detail"].lower()


def test_upload_no_extension_rejected(client):
    response = client.post(
        "/api/files/upload",
        files={"file": ("Makefile", io.BytesIO(b"all:"), "text/plain")},
    )
    assert response.status_code == 400


def test_safe_filename_path_traversal(client, tmp_path, monkeypatch):
    from core.config import settings

    content = b"sensitive content"
    response = client.post(
        "/api/files/upload",
        files={"file": ("../evil.txt", io.BytesIO(content), "text/plain")},
    )
    assert response.status_code == 200
    data = response.json()

    stored = data["stored_filename"]
    assert "/" not in stored
    assert "\\" not in stored
    assert stored == "evil.txt"

    # Confirm the file landed inside the document directory, not above it
    doc_dir = settings.raw_uploads_dir / data["document_id"]
    assert (doc_dir / stored).exists()


def test_health_still_works(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
