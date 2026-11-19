import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from core.config import settings
from db import repository
from db.models import Job
from db.session import get_session
from models.job_models import CleanupJobsRequest, JobDetail
from services import audit_log_service

_TERMINAL_STATUSES = {"succeeded", "failed", "canceled"}
_RETRYABLE_STATUSES = {"failed", "canceled"}
_CANCELABLE_STATUSES = {"queued", "running"}
_RETRYABLE_JOB_TYPES = {"convert", "chunk", "index", "retrieval_evaluation", "grounded_answer"}
_PATH_KEYS = {
    "path",
    "raw_path",
    "markdown_path",
    "payload_path",
    "manifest_path",
    "file_path",
}


class JobNotFoundError(FileNotFoundError):
    pass


class JobRetryNotAllowedError(ValueError):
    pass


class JobRetryUnavailableError(ValueError):
    pass


class JobService:
    def create_job(
        self,
        *,
        job_type: str,
        document_id: Optional[str] = None,
        request: Optional[dict] = None,
        message: Optional[str] = None,
        retry_of_job_id: Optional[str] = None,
    ) -> JobDetail:
        job_id = str(uuid.uuid4())
        safe_request = _sanitize_for_storage(request or {})
        with get_session() as session:
            row = repository.create_job(
                session,
                job_id=job_id,
                document_id=document_id,
                job_type=job_type,
                status="queued",
                progress_percent=0,
                current_step="queued",
                message=message or "Queued",
                request_json=json.dumps(safe_request, default=str),
                retry_of_job_id=retry_of_job_id,
            )
            detail = self._to_detail(row)
        audit_log_service.append("job_created", document_id or "", job_id=job_id, job_type=job_type)
        return detail

    def get_job(self, job_id: str) -> JobDetail:
        with get_session() as session:
            row = repository.get_job(session, job_id)
            if row is None:
                raise JobNotFoundError(job_id)
            return self._to_detail(row)

    def list_jobs(
        self,
        *,
        document_id: Optional[str] = None,
        status: Optional[str] = None,
        job_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        sort: str = "newest",
    ) -> list[JobDetail]:
        safe_limit = min(max(1, limit), 200)
        safe_offset = max(0, offset)
        safe_sort = "oldest" if sort == "oldest" else "newest"
        with get_session() as session:
            return [
                self._to_detail(row)
                for row in repository.list_jobs(
                    session,
                    document_id=document_id,
                    status=status,
                    job_type=job_type,
                    limit=safe_limit,
                    offset=safe_offset,
                    sort=safe_sort,
                )
            ]

    def count_jobs(
        self,
        *,
        document_id: Optional[str] = None,
        status: Optional[str] = None,
        job_type: Optional[str] = None,
    ) -> int:
        with get_session() as session:
            return repository.count_jobs(
                session,
                document_id=document_id,
                status=status,
                job_type=job_type,
            )

    def start_job(self, job_id: str, *, step: str, message: Optional[str] = None) -> Optional[JobDetail]:
        now = datetime.now(timezone.utc)
        with get_session() as session:
            row = repository.get_job(session, job_id)
            if row is None:
                return None
            if row.status == "canceled":
                return self._to_detail(row)
            row = repository.update_job(
                session,
                job_id,
                status="running",
                progress_percent=max(row.progress_percent or 0, 1),
                current_step=step,
                message=message or step,
                started_at=now,
            )
            detail = self._to_detail(row)
        audit_log_service.append("job_started", detail.document_id or "", job_id=job_id, job_type=detail.job_type)
        return detail

    def update_progress(
        self,
        job_id: str,
        *,
        progress_percent: int,
        step: Optional[str] = None,
        message: Optional[str] = None,
    ) -> Optional[JobDetail]:
        with get_session() as session:
            row = repository.get_job(session, job_id)
            if row is None:
                return None
            if row.status in _TERMINAL_STATUSES:
                return self._to_detail(row)
            row = repository.update_job(
                session,
                job_id,
                status="running",
                progress_percent=min(max(0, progress_percent), 99),
                current_step=step or row.current_step,
                message=message or row.message,
            )
            return self._to_detail(row)

    def succeed_job(
        self,
        job_id: str,
        *,
        result: Optional[Any] = None,
        message: str = "Complete",
    ) -> Optional[JobDetail]:
        now = datetime.now(timezone.utc)
        safe_result = _sanitize_for_storage(_to_plain_data(result))
        with get_session() as session:
            row = repository.get_job(session, job_id)
            if row is None:
                return None
            if row.status == "canceled":
                return self._to_detail(row)
            row = repository.update_job(
                session,
                job_id,
                status="succeeded",
                progress_percent=100,
                current_step="complete",
                message=message,
                result_json=json.dumps(safe_result, default=str),
                error=None,
                finished_at=now,
            )
            detail = self._to_detail(row)
        audit_log_service.append("job_succeeded", detail.document_id or "", job_id=job_id, job_type=detail.job_type)
        return detail

    def fail_job(self, job_id: str, *, error: Any, step: Optional[str] = None) -> Optional[JobDetail]:
        now = datetime.now(timezone.utc)
        safe_error = _safe_error(error)
        with get_session() as session:
            row = repository.get_job(session, job_id)
            if row is None:
                return None
            if row.status == "canceled":
                return self._to_detail(row)
            row = repository.update_job(
                session,
                job_id,
                status="failed",
                current_step=step or row.current_step,
                message="Failed",
                error=safe_error,
                finished_at=now,
            )
            detail = self._to_detail(row)
        audit_log_service.append("job_failed", detail.document_id or "", job_id=job_id, job_type=detail.job_type)
        return detail

    def cancel_job(self, job_id: str) -> JobDetail:
        now = datetime.now(timezone.utc)
        with get_session() as session:
            row = repository.get_job(session, job_id)
            if row is None:
                raise JobNotFoundError(job_id)
            if row.status not in _TERMINAL_STATUSES:
                row = repository.update_job(
                    session,
                    job_id,
                    status="canceled",
                    current_step="canceled",
                    message="Cancellation requested. Running tasks stop between major steps.",
                    canceled_at=now,
                    finished_at=now,
                )
            detail = self._to_detail(row)
        audit_log_service.append("job_canceled", detail.document_id or "", job_id=job_id, job_type=detail.job_type)
        return detail

    def retry_job(self, job_id: str) -> JobDetail:
        with get_session() as session:
            row = repository.get_job(session, job_id)
            if row is None:
                raise JobNotFoundError(job_id)
            if not _can_retry(row):
                raise JobRetryNotAllowedError(
                    "Only failed, canceled, or interrupted jobs can be retried."
                )
            if row.job_type not in _RETRYABLE_JOB_TYPES:
                raise JobRetryUnavailableError(f"Job type '{row.job_type}' cannot be retried.")
            request = _loads_object(row.request_json)
            if request is None:
                raise JobRetryUnavailableError("Original job request data is missing; retry cannot be created.")
            document_id = row.document_id
            job_type = row.job_type

        new_job = self.create_job(
            job_type=job_type,
            document_id=document_id,
            request=request,
            message=f"Retry queued from {job_id}",
            retry_of_job_id=job_id,
        )
        audit_log_service.append(
            "job_retried",
            document_id or "",
            job_id=new_job.job_id,
            retry_of_job_id=job_id,
            job_type=job_type,
        )
        return new_job

    def cleanup_jobs(self, request: CleanupJobsRequest) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=request.older_than_days)
        statuses = sorted(set(request.statuses))
        with get_session() as session:
            deleted = repository.delete_jobs(session, statuses=statuses, older_than=cutoff)
        audit_log_service.append(
            "job_cleanup",
            "",
            deleted_count=deleted,
            statuses=",".join(statuses),
        )
        return deleted

    def is_canceled(self, job_id: str) -> bool:
        with get_session() as session:
            row = repository.get_job(session, job_id)
            return bool(row and row.status == "canceled")

    def mark_stale_jobs_interrupted(self, *, older_than_hours: int = 6) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=older_than_hours)
        changed = 0
        with get_session() as session:
            rows = repository.list_jobs(session, limit=500)
            for row in rows:
                if row.status not in {"queued", "running"}:
                    continue
                updated_at = row.updated_at or row.created_at
                if updated_at and updated_at.replace(tzinfo=timezone.utc) > cutoff:
                    continue
                row.status = "failed"
                row.current_step = "interrupted"
                row.message = "Interrupted by backend restart."
                row.error = "Job was interrupted before completion."
                row.finished_at = datetime.now(timezone.utc)
                row.updated_at = datetime.now(timezone.utc)
                changed += 1
        return changed

    def _to_detail(self, row: Job) -> JobDetail:
        request = _loads_object(row.request_json)
        result = None
        if row.result_json:
            try:
                loaded = json.loads(row.result_json)
                result = loaded if isinstance(loaded, dict) else {"value": loaded}
            except Exception:
                result = None
        return JobDetail(
            job_id=row.id,
            document_id=row.document_id,
            job_type=row.job_type,
            status=row.status,
            progress_percent=row.progress_percent or 0,
            current_step=row.current_step,
            message=row.message,
            request=request,
            result=result,
            error=row.error,
            created_at=row.created_at,
            started_at=row.started_at,
            finished_at=row.finished_at,
            updated_at=row.updated_at,
            canceled_at=row.canceled_at,
            retry_of_job_id=row.retry_of_job_id,
            can_retry=_can_retry(row),
            can_cancel=row.status in _CANCELABLE_STATUSES,
        )


def _can_retry(row: Job) -> bool:
    if row.job_type not in _RETRYABLE_JOB_TYPES:
        return False
    if row.status in _RETRYABLE_STATUSES:
        return True
    return row.status == "failed" and row.current_step == "interrupted"


def _loads_object(value: Optional[str]) -> Optional[Dict[str, Any]]:
    if value is None or value == "":
        return None
    try:
        loaded = json.loads(value)
    except Exception:
        return None
    if isinstance(loaded, dict):
        return _sanitize_for_storage(loaded)
    return {}


def _to_plain_data(value: Any) -> Any:
    if value is None:
        return {}
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return value
    return {"value": str(value)}


def _sanitize_for_storage(value: Any) -> Any:
    if isinstance(value, dict):
        safe: Dict[str, Any] = {}
        for key, item in value.items():
            if key in _PATH_KEYS or key.endswith("_path"):
                continue
            safe[key] = _sanitize_for_storage(item)
        return safe
    if isinstance(value, list):
        return [_sanitize_for_storage(item) for item in value]
    if isinstance(value, str):
        return _safe_text(value)
    return value


def _safe_error(error: Any) -> str:
    text = str(error)
    if not text:
        text = error.__class__.__name__ if hasattr(error, "__class__") else "Job failed."
    return _safe_text(text)[:1000]


def _safe_text(text: str) -> str:
    paths = [
        settings.raw_uploads_dir,
        settings.converted_dir,
        settings.chunks_dir,
        settings.llm_payloads_dir,
        settings.projects_dir,
        settings.audit_log_dir,
        settings.storage_root,
    ]
    safe = text
    for path in paths:
        # Replace the configured path (may be relative in dev, absolute in containers)
        safe = safe.replace(str(path), "[redacted-path]")
        # Also replace the OS-resolved absolute form (e.g. /app/storage/... in Docker)
        resolved = str(path.resolve())
        if resolved != str(path):
            safe = safe.replace(resolved, "[redacted-path]")
    # Catch remaining absolute Unix storage paths: Docker /app/, Linux /home/, macOS /Users/,
    # /private/ (macOS tmp symlink), /tmp/, /var/, and bare /storage/ at root.
    safe = re.sub(r"/(?:app|home|Users|private|tmp|var|storage)/[^\s\"']+", "[redacted-path]", safe)
    return safe
