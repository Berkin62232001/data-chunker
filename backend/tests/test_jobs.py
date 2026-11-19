import io
import json
from datetime import datetime, timedelta, timezone


def upload(client, content: bytes = b"# Test\n\nContent.", filename: str = "doc.md") -> str:
    response = client.post(
        "/api/files/upload",
        files={"file": (filename, io.BytesIO(content), "text/plain")},
    )
    assert response.status_code == 200, response.text
    return response.json()["document_id"]


def upload_profile_pipeline(client, content: bytes = b"# Test\n\nContent.") -> str:
    doc_id = upload(client, content)
    assert client.get(f"/api/files/{doc_id}/profile").status_code == 200
    assert client.get(f"/api/files/{doc_id}/pipeline").status_code == 200
    return doc_id


def full_pipeline(client, content: bytes = b"# Test\n\nContent.") -> str:
    doc_id = upload_profile_pipeline(client, content)
    assert client.post(f"/api/files/{doc_id}/convert").status_code == 200
    assert client.post(f"/api/files/{doc_id}/chunk").status_code == 200
    return doc_id


def test_create_job(client):
    from services.job_service import JobService

    job = JobService().create_job(job_type="convert", document_id="doc-1")

    assert job.job_id
    assert job.job_type == "convert"
    assert job.document_id == "doc-1"
    assert job.status == "queued"
    assert job.progress_percent == 0


def test_get_job(client):
    from services.job_service import JobService

    service = JobService()
    job = service.create_job(job_type="chunk", document_id="doc-2")

    fetched = service.get_job(job.job_id)

    assert fetched.job_id == job.job_id
    assert fetched.job_type == "chunk"


def test_list_jobs(client):
    from services.job_service import JobService

    service = JobService()
    service.create_job(job_type="convert", document_id="doc-list")
    service.create_job(job_type="chunk", document_id="doc-list")

    jobs = service.list_jobs(document_id="doc-list")

    assert len(jobs) == 2
    assert {job.job_type for job in jobs} == {"convert", "chunk"}


def test_status_transitions_queued_running_succeeded(client):
    from services.job_service import JobService

    service = JobService()
    job = service.create_job(job_type="convert", document_id="doc-state")

    running = service.start_job(job.job_id, step="loading_document")
    succeeded = service.succeed_job(job.job_id, result={"ok": True})

    assert running.status == "running"
    assert succeeded.status == "succeeded"
    assert succeeded.progress_percent == 100
    assert succeeded.result == {"ok": True}


def test_failed_job_stores_safe_error(client):
    from core.config import settings
    from services.job_service import JobService

    service = JobService()
    job = service.create_job(job_type="index", document_id="doc-fail")

    failed = service.fail_job(job.job_id, error=RuntimeError(f"failed at {settings.chunks_dir}/secret"))

    assert failed.status == "failed"
    assert "failed at" in failed.error
    assert str(settings.chunks_dir) not in failed.error


def test_cancel_queued_and_running_job_best_effort(client):
    from services.job_service import JobService

    service = JobService()
    queued = service.create_job(job_type="convert", document_id="doc-cancel-queued")
    canceled_queued = service.cancel_job(queued.job_id)

    running = service.create_job(job_type="chunk", document_id="doc-cancel-running")
    service.start_job(running.job_id, step="generating_chunks")
    canceled_running = service.cancel_job(running.job_id)

    assert canceled_queued.status == "canceled"
    assert canceled_running.status == "canceled"


def test_document_convert_job_endpoint_creates_job(client):
    doc_id = upload_profile_pipeline(client)

    response = client.post(f"/api/files/{doc_id}/convert/job")

    assert response.status_code == 200
    data = response.json()
    assert data["job_id"]
    assert data["document_id"] == doc_id
    assert data["job_type"] == "convert"


def test_chunk_job_endpoint_creates_job(client):
    doc_id = upload_profile_pipeline(client)
    assert client.post(f"/api/files/{doc_id}/convert").status_code == 200

    response = client.post(f"/api/files/{doc_id}/chunk/job")

    assert response.status_code == 200
    assert response.json()["job_type"] == "chunk"


def test_index_job_endpoint_creates_job(client):
    doc_id = full_pipeline(client)

    response = client.post(f"/api/files/{doc_id}/index/job")

    assert response.status_code == 200
    assert response.json()["job_type"] == "index"


def test_retrieval_evaluation_job_endpoint_creates_job(client):
    doc_id = full_pipeline(client, b"# Retrieval\n\nRetrieval uses chunks.")

    response = client.post(
        f"/api/files/{doc_id}/retrieval-evaluation/job",
        json={"query": "retrieval", "retrieval_mode": "keyword", "top_k": 3},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["job_type"] == "retrieval_evaluation"
    assert data["job_id"]


def test_grounded_answer_job_endpoint_creates_job(client):
    doc_id = full_pipeline(client, b"# Grounding\n\nGrounded answers use citations.")

    response = client.post(
        f"/api/files/{doc_id}/grounded-answer/job",
        json={"question": "What uses citations?", "retrieval_mode": "keyword", "top_k": 3, "provider": "mock"},
    )

    assert response.status_code == 200
    assert response.json()["job_type"] == "grounded_answer"


def test_job_result_json_stored_on_success(client):
    from services.job_service import JobService

    service = JobService()
    job = service.create_job(job_type="retrieval_evaluation", document_id="doc-result")

    service.succeed_job(job.job_id, result={"answer": "ok", "nested": {"count": 1}})
    fetched = service.get_job(job.job_id)

    assert fetched.result == {"answer": "ok", "nested": {"count": 1}}


def test_jobs_do_not_expose_absolute_paths(client):
    from core.config import settings
    from services.job_service import JobService

    service = JobService()
    job = service.create_job(
        job_type="convert",
        document_id="doc-paths",
        request={"path": str(settings.raw_uploads_dir / "doc-paths" / "secret.txt")},
    )

    service.succeed_job(
        job.job_id,
        result={
            "markdown_path": str(settings.converted_dir / "doc-paths" / "document.md"),
            "safe": "value",
        },
    )
    response = client.get(f"/api/jobs/{job.job_id}")

    assert response.status_code == 200
    payload = json.dumps(response.json())
    assert str(settings.raw_uploads_dir) not in payload
    assert str(settings.converted_dir) not in payload
    assert "markdown_path" not in payload
    assert response.json()["result"] == {"safe": "value"}


def test_list_jobs_with_status_filter(client):
    from services.job_service import JobService

    service = JobService()
    service.create_job(job_type="convert", document_id="doc-filter-status")
    failed = service.create_job(job_type="chunk", document_id="doc-filter-status")
    service.fail_job(failed.job_id, error="boom")

    response = client.get("/api/jobs?status=failed&limit=20")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert all(job["status"] == "failed" for job in data["jobs"])


def test_list_jobs_with_job_type_filter(client):
    from services.job_service import JobService

    service = JobService()
    service.create_job(job_type="convert", document_id="doc-filter-type")
    service.create_job(job_type="chunk", document_id="doc-filter-type")

    response = client.get("/api/jobs?job_type=convert&limit=20")

    assert response.status_code == 200
    assert response.json()["jobs"]
    assert all(job["job_type"] == "convert" for job in response.json()["jobs"])


def test_job_pagination_works(client):
    from services.job_service import JobService

    service = JobService()
    for index in range(5):
        service.create_job(job_type="convert", document_id=f"doc-page-{index}")

    first = client.get("/api/jobs?limit=2&offset=0")
    second = client.get("/api/jobs?limit=2&offset=2")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["limit"] == 2
    assert second.json()["offset"] == 2
    assert len(first.json()["jobs"]) == 2
    assert len(second.json()["jobs"]) == 2
    assert {job["job_id"] for job in first.json()["jobs"]}.isdisjoint(
        {job["job_id"] for job in second.json()["jobs"]}
    )


def test_job_detail_includes_can_retry_and_can_cancel(client):
    from services.job_service import JobService

    service = JobService()
    queued = service.create_job(job_type="convert", document_id="doc-flags", request={"operation": "convert"})
    failed = service.create_job(job_type="convert", document_id="doc-flags", request={"operation": "convert"})
    service.fail_job(failed.job_id, error="failed")

    queued_detail = client.get(f"/api/jobs/{queued.job_id}").json()
    failed_detail = client.get(f"/api/jobs/{failed.job_id}").json()

    assert queued_detail["can_cancel"] is True
    assert queued_detail["can_retry"] is False
    assert failed_detail["can_cancel"] is False
    assert failed_detail["can_retry"] is True


def test_retry_failed_convert_job_creates_new_queued_job(client):
    from services.job_service import JobService

    service = JobService()
    original = service.create_job(job_type="convert", document_id="doc-retry-failed", request={"operation": "convert"})
    service.fail_job(original.job_id, error="failed")

    response = client.post(f"/api/jobs/{original.job_id}/retry")

    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] != original.job_id
    assert data["retry_of_job_id"] == original.job_id
    assert data["status"] == "queued"
    assert data["job_type"] == "convert"


def test_retry_canceled_job_creates_new_job(client):
    from services.job_service import JobService

    service = JobService()
    original = service.create_job(job_type="chunk", document_id="doc-retry-canceled", request={"operation": "chunk"})
    service.cancel_job(original.job_id)

    response = client.post(f"/api/jobs/{original.job_id}/retry")

    assert response.status_code == 200
    assert response.json()["retry_of_job_id"] == original.job_id


def test_retry_running_and_succeeded_jobs_rejected(client):
    from services.job_service import JobService

    service = JobService()
    running = service.create_job(job_type="convert", document_id="doc-retry-running", request={"operation": "convert"})
    service.start_job(running.job_id, step="running")
    succeeded = service.create_job(job_type="convert", document_id="doc-retry-succeeded", request={"operation": "convert"})
    service.succeed_job(succeeded.job_id, result={"ok": True})

    assert client.post(f"/api/jobs/{running.job_id}/retry").status_code == 409
    assert client.post(f"/api/jobs/{succeeded.job_id}/retry").status_code == 409


def test_retry_fails_when_request_json_missing(client):
    from db import repository
    from db.session import get_session
    from services.job_service import JobService

    service = JobService()
    original = service.create_job(job_type="convert", document_id="doc-retry-missing", request={"operation": "convert"})
    service.fail_job(original.job_id, error="failed")
    with get_session() as session:
        repository.update_job(session, original.job_id, request_json=None)

    response = client.post(f"/api/jobs/{original.job_id}/retry")

    assert response.status_code == 422
    assert "missing" in response.json()["detail"].lower()


def test_cleanup_deletes_only_selected_old_jobs(client):
    from db import repository
    from db.session import get_session
    from services.job_service import JobService

    service = JobService()
    old_failed = service.create_job(job_type="convert", document_id="doc-cleanup", request={"operation": "convert"})
    service.fail_job(old_failed.job_id, error="old")
    old_succeeded = service.create_job(job_type="chunk", document_id="doc-cleanup", request={"operation": "chunk"})
    service.succeed_job(old_succeeded.job_id, result={"ok": True})
    recent_failed = service.create_job(job_type="index", document_id="doc-cleanup", request={"operation": "index"})
    service.fail_job(recent_failed.job_id, error="recent")
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=40)
    with get_session() as session:
        repository.update_job(session, old_failed.job_id, created_at=cutoff_date)
        repository.update_job(session, old_succeeded.job_id, created_at=cutoff_date)

    response = client.post(
        "/api/jobs/cleanup",
        json={"older_than_days": 30, "statuses": ["failed"]},
    )

    assert response.status_code == 200
    assert response.json()["deleted_count"] == 1
    assert client.get(f"/api/jobs/{old_failed.job_id}").status_code == 404
    assert client.get(f"/api/jobs/{old_succeeded.job_id}").status_code == 200
    assert client.get(f"/api/jobs/{recent_failed.job_id}").status_code == 200


def test_cleanup_does_not_delete_documents_or_artifacts(client):
    from core.config import settings
    from db import repository
    from db.session import get_session
    from services.job_service import JobService

    doc_id = upload(client, b"# Cleanup\n\nKeep this document.")
    raw_meta = settings.raw_uploads_dir / doc_id / "metadata.json"
    assert raw_meta.exists()

    service = JobService()
    old_job = service.create_job(job_type="convert", document_id=doc_id, request={"operation": "convert"})
    service.succeed_job(old_job.job_id, result={"ok": True})
    with get_session() as session:
        repository.update_job(
            session,
            old_job.job_id,
            created_at=datetime.now(timezone.utc) - timedelta(days=40),
        )

    response = client.post(
        "/api/jobs/cleanup",
        json={"older_than_days": 30, "statuses": ["succeeded"]},
    )

    assert response.status_code == 200
    assert response.json()["deleted_count"] == 1
    assert raw_meta.exists()


# ── Path-redaction tests ──────────────────────────────────────────────────────

def test_safe_text_redacts_docker_app_storage_path(client):
    """Errors containing Docker-style /app/storage/... paths must be stripped."""
    from services.job_service import JobService

    service = JobService()
    job = service.create_job(job_type="convert", document_id="doc-docker-path")
    failed = service.fail_job(
        job.job_id,
        error=RuntimeError("open /app/storage/raw/abc123/file.pdf: no such file or directory"),
    )

    assert failed.status == "failed"
    assert "/app/storage" not in (failed.error or "")
    assert "[redacted-path]" in (failed.error or "")


def test_safe_text_redacts_resolved_settings_path(client):
    """Errors containing the resolved absolute path of a settings dir must be stripped."""
    from core.config import settings
    from services.job_service import JobService

    resolved = str(settings.chunks_dir.resolve())
    service = JobService()
    job = service.create_job(job_type="chunk", document_id="doc-resolved-path")
    failed = service.fail_job(
        job.job_id,
        error=RuntimeError(f"FileNotFoundError: {resolved}/doc-id/chunks.jsonl"),
    )

    assert failed.status == "failed"
    assert resolved not in (failed.error or "")


def test_safe_text_redacts_linux_home_path(client):
    """Errors containing /home/... paths (Linux dev environments) must be stripped."""
    from services.job_service import JobService

    service = JobService()
    job = service.create_job(job_type="index", document_id="doc-linux-path")
    failed = service.fail_job(
        job.job_id,
        error=RuntimeError("read /home/user/project/storage/chunks/abc/chunks.jsonl: permission denied"),
    )

    assert failed.status == "failed"
    assert "/home/user" not in (failed.error or "")
    assert "[redacted-path]" in (failed.error or "")


def test_vector_error_detail_redacts_absolute_path():
    """_vector_error_detail must strip absolute paths before they reach the HTTP response."""
    from api.routes.files import _vector_error_detail

    detail = _vector_error_detail("Qdrant failed reading /app/storage/chunks/abc/index.json")
    assert "/app/storage" not in detail["message"]
    assert "[redacted-path]" in detail["message"]
