import uuid
from typing import Optional

from fastapi import HTTPException, UploadFile

from core.config import settings
from models.file_models import UploadResponse
from db import repository
from db.session import get_session
from services import audit_log_service
from storage.raw_storage import save_raw_file
from utils.file_utils import get_extension, guess_mime_type, sanitize_filename


async def handle_upload(file: UploadFile) -> UploadResponse:
    original_name = file.filename or ""
    if not original_name:
        raise HTTPException(status_code=400, detail="Filename is required.")

    ext = get_extension(original_name)
    if ext not in settings.allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext or '(none)'}' is not allowed.",
        )

    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    content = await file.read(max_bytes + 1)

    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty files are not accepted.")

    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {settings.max_upload_size_mb} MB limit.",
        )

    document_id = str(uuid.uuid4())
    safe_name = sanitize_filename(original_name)
    guessed_mime: Optional[str] = guess_mime_type(safe_name)
    browser_mime: Optional[str] = file.content_type if file.content_type else None
    mime_type: Optional[str] = guessed_mime or browser_mime

    # Check the browser-provided MIME type against the allowlist, but skip the generic
    # "application/octet-stream" fallback that many clients send for unknown file types.
    effective_mime = browser_mime if (browser_mime and browser_mime != "application/octet-stream") else guessed_mime
    if effective_mime and not any(effective_mime.startswith(cat) for cat in settings.allowed_mime_categories):
        raise HTTPException(
            status_code=415,
            detail=f"MIME type '{effective_mime}' is not in the allowed categories.",
        )

    file_path = save_raw_file(
        document_id=document_id,
        stored_filename=safe_name,
        original_filename=original_name,
        content=content,
        mime_type=mime_type,
    )

    audit_log_service.append(
        "upload",
        document_id,
        original_filename=original_name,
        extension=ext,
        size_bytes=len(content),
        mime_type=mime_type,
    )

    with get_session() as session:
        repository.upsert_document(
            session,
            document_id=document_id,
            original_filename=original_name,
            stored_filename=safe_name,
            mime_type=mime_type,
            file_size_bytes=len(content),
        )

    return UploadResponse(
        document_id=document_id,
        original_filename=original_name,
        stored_filename=safe_name,
        size_bytes=len(content),
        mime_type=mime_type,
        status="raw",
    )
