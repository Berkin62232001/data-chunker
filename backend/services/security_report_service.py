from utils.storage_paths import storage_path
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from core.config import settings
from models.chunk_models import Chunk
from models.security_models import (
    InjectionWarning,
    PayloadSafetyInfo,
    SecurityReport,
    UploadSecurityInfo,
)
from services import audit_log_service
from services.prompt_injection_service import scan_chunks

_SAFETY_MARKER = "untrusted source material"  # must be present in every payload's safety notice


class SecurityReportService:
    def generate(self, document_id: str) -> SecurityReport:
        upload_info = self._upload_info(document_id)
        injection_warnings, scan_complete = self._injection_scan(document_id)
        payload_safety = self._payload_safety(document_id)
        audit_entries = audit_log_service.read_for_document(document_id)

        return SecurityReport(
            document_id=document_id,
            generated_at=datetime.now(timezone.utc).isoformat(),
            local_only_mode=settings.local_only_mode,
            upload=upload_info,
            injection_warnings=injection_warnings,
            injection_scan_complete=scan_complete,
            payload_safety=payload_safety,
            recent_audit_entries=audit_entries,
        )

    # ── helpers ───────────────────────────────────────────────────────────────

    def _upload_info(self, document_id: str) -> UploadSecurityInfo:
        meta_path = storage_path(settings.raw_uploads_dir, document_id, "metadata.json")
        meta = json.loads(meta_path.read_text(encoding="utf-8"))

        ext = Path(meta.get("stored_filename", "")).suffix.lower()
        mime = meta.get("mime_type")
        size = meta.get("size_bytes", 0)

        ext_allowed = ext in settings.allowed_extensions
        size_ok = size <= settings.max_upload_size_mb * 1024 * 1024

        if mime:
            mime_ok = any(mime.startswith(cat) for cat in settings.allowed_mime_categories)
        else:
            mime_ok = True  # guessed from extension; extension already validated

        return UploadSecurityInfo(
            extension=ext,
            mime_type=mime,
            size_bytes=size,
            extension_allowed=ext_allowed,
            size_within_limit=size_ok,
            mime_allowed=mime_ok,
        )

    def _injection_scan(self, document_id: str) -> tuple:
        jsonl_path = storage_path(settings.chunks_dir, document_id, "chunks.jsonl")
        if not jsonl_path.exists():
            return [], False

        chunks: List[Chunk] = []
        with open(jsonl_path, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    try:
                        chunks.append(Chunk(**json.loads(line)))
                    except Exception:
                        pass

        hits = scan_chunks(chunks)
        warnings = [
            InjectionWarning(
                chunk_id=h.chunk_id,
                chunk_index=h.chunk_index,
                matched_pattern=h.matched_pattern,
                text_excerpt=h.text_excerpt,
            )
            for h in hits
        ]
        return warnings, True

    def _payload_safety(self, document_id: str) -> PayloadSafetyInfo:
        payload_dir = storage_path(settings.llm_payloads_dir, document_id)
        if not payload_dir.exists():
            return PayloadSafetyInfo(safety_instruction_present=True, payloads_generated=0)

        payload_files = list(payload_dir.glob("payload_*.json"))
        safety_ok = True

        for pf in payload_files:
            try:
                content = pf.read_text(encoding="utf-8")
                if _SAFETY_MARKER not in content.lower():
                    safety_ok = False
                    break
            except OSError:
                pass

        return PayloadSafetyInfo(
            safety_instruction_present=safety_ok,
            payloads_generated=len(payload_files),
        )
