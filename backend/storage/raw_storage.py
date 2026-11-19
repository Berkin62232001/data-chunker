from utils.storage_paths import storage_path
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core.config import settings


def save_raw_file(
    document_id: str,
    stored_filename: str,
    original_filename: str,
    content: bytes,
    mime_type: Optional[str],
) -> Path:
    doc_dir = storage_path(settings.raw_uploads_dir, document_id)
    doc_dir.mkdir(parents=True, exist_ok=True)

    file_path = doc_dir / stored_filename
    file_path.write_bytes(content)

    metadata = {
        "document_id": document_id,
        "original_filename": original_filename,
        "stored_filename": stored_filename,
        "size_bytes": len(content),
        "mime_type": mime_type,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "status": "raw",
    }
    (doc_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))

    return file_path
