from utils.storage_paths import storage_path
import hashlib
import json
from pathlib import Path
from typing import List, Tuple

from core.config import settings
from db import repository
from db.session import get_session
from models.chunk_models import Chunk, ChunkManifest
from models.conversion_models import ConversionMetadata
from models.integrity_models import IntegrityCheck, IntegrityReport
from models.pipeline_models import PipelineDecision
from models.profile_models import DocumentProfile


def _pass(name: str, msg: str) -> IntegrityCheck:
    return IntegrityCheck(name=name, status="pass", message=msg)


def _warn(name: str, msg: str) -> IntegrityCheck:
    return IntegrityCheck(name=name, status="warn", message=msg)


def _fail(name: str, msg: str) -> IntegrityCheck:
    return IntegrityCheck(name=name, status="fail", message=msg)


def _skip(name: str, msg: str) -> IntegrityCheck:
    return IntegrityCheck(name=name, status="skip", message=msg)


class IntegrityService:

    @staticmethod
    def sha256_text(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def sha256_file(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for block in iter(lambda: fh.read(65536), b""):
                h.update(block)
        return h.hexdigest()

    @staticmethod
    def verify_chunk(chunk: Chunk) -> bool:
        expected = hashlib.sha256(chunk.text.encode("utf-8")).hexdigest()
        return chunk.sha256 == expected

    def verify_chunks_jsonl(self, document_id: str) -> Tuple[int, List[str]]:
        """Read chunks.jsonl, validate schema and SHA-256. Returns (valid_count, errors)."""
        jsonl_path = storage_path(settings.chunks_dir, document_id, "chunks.jsonl")
        errors: List[str] = []
        valid = 0

        with open(jsonl_path, encoding="utf-8") as fh:
            for i, line in enumerate(fh):
                if not line.strip():
                    continue
                try:
                    chunk = Chunk(**json.loads(line))
                except Exception as exc:
                    errors.append(f"Line {i}: schema error — {exc}")
                    continue
                if not self.verify_chunk(chunk):
                    short_id = chunk.chunk_id[:8]
                    errors.append(
                        f"Line {i} (chunk_id={short_id}…): SHA-256 mismatch — "
                        "text may have been modified"
                    )
                else:
                    valid += 1

        return valid, errors

    def verify_document_outputs(self, document_id: str) -> IntegrityReport:
        checks: List[IntegrityCheck] = []
        warnings: List[str] = []
        errors: List[str] = []

        raw_dir = storage_path(settings.raw_uploads_dir, document_id)
        converted_dir = storage_path(settings.converted_dir, document_id)
        chunks_dir = storage_path(settings.chunks_dir, document_id)

        # ── 1. Raw metadata.json ──────────────────────────────────────────────
        raw_meta_path = raw_dir / "metadata.json"
        raw_meta = None
        if not raw_meta_path.exists():
            checks.append(_fail("raw_metadata", "metadata.json not found in raw storage"))
            errors.append("metadata.json missing")
            return _build_report(document_id, checks, warnings, errors)

        try:
            raw_meta = json.loads(raw_meta_path.read_text())
            checks.append(_pass("raw_metadata", "Raw metadata.json readable"))
        except Exception as exc:
            checks.append(_fail("raw_metadata", f"metadata.json unreadable: {exc}"))
            errors.append(str(exc))
            return _build_report(document_id, checks, warnings, errors)

        # ── 2. Raw file exists ────────────────────────────────────────────────
        stored_filename = raw_meta.get("stored_filename", "")
        raw_file = raw_dir / stored_filename
        if stored_filename and raw_file.exists():
            size = raw_file.stat().st_size
            checks.append(_pass("raw_file", f"Raw file exists: {stored_filename} ({size} bytes)"))
        else:
            msg = f"Raw file missing: {stored_filename!r}"
            checks.append(_fail("raw_file", msg))
            errors.append(msg)

        # ── 3. profile.json ───────────────────────────────────────────────────
        profile_path = raw_dir / "profile.json"
        if not profile_path.exists():
            msg = "profile.json not found — run GET /profile first"
            checks.append(_warn("profile", msg))
            warnings.append(msg)
        else:
            try:
                DocumentProfile(**json.loads(profile_path.read_text()))
                checks.append(_pass("profile", "profile.json valid"))
            except Exception as exc:
                msg = f"profile.json invalid: {exc}"
                checks.append(_fail("profile", msg))
                errors.append(msg)

        # ── 4. pipeline_decision.json ─────────────────────────────────────────
        pipeline_path = raw_dir / "pipeline_decision.json"
        if not pipeline_path.exists():
            msg = "pipeline_decision.json not found — run GET /pipeline first"
            checks.append(_warn("pipeline_decision", msg))
            warnings.append(msg)
        else:
            try:
                PipelineDecision(**json.loads(pipeline_path.read_text()))
                checks.append(_pass("pipeline_decision", "pipeline_decision.json valid"))
            except Exception as exc:
                msg = f"pipeline_decision.json invalid: {exc}"
                checks.append(_fail("pipeline_decision", msg))
                errors.append(msg)

        # ── 5. document.md ────────────────────────────────────────────────────
        doc_md = converted_dir / "document.md"
        if not doc_md.exists():
            msg = "document.md not found — run POST /convert first"
            checks.append(_warn("document_md", msg))
            warnings.append(msg)
        else:
            size = doc_md.stat().st_size
            checks.append(_pass("document_md", f"document.md exists ({size} bytes)"))

        # ── 6. Converted metadata.json ────────────────────────────────────────
        conv_meta_path = converted_dir / "metadata.json"
        if not conv_meta_path.exists():
            msg = "Converted metadata.json not found"
            checks.append(_warn("conversion_metadata", msg))
            warnings.append(msg)
        else:
            try:
                ConversionMetadata(**json.loads(conv_meta_path.read_text()))
                checks.append(_pass("conversion_metadata", "Converted metadata.json valid"))
            except Exception as exc:
                msg = f"Converted metadata.json invalid: {exc}"
                checks.append(_fail("conversion_metadata", msg))
                errors.append(msg)

        # ── 7. chunks.jsonl (optional) ────────────────────────────────────────
        jsonl_path = chunks_dir / "chunks.jsonl"
        if not jsonl_path.exists():
            checks.append(_skip("chunks_jsonl", "chunks.jsonl not found — run POST /chunk first"))
        else:
            valid_count, chunk_errors = self.verify_chunks_jsonl(document_id)
            if chunk_errors:
                errors.extend(chunk_errors)
                checks.append(_fail(
                    "chunks_jsonl",
                    f"{valid_count} chunks valid, {len(chunk_errors)} error(s)",
                ))
            else:
                checks.append(_pass("chunks_jsonl", f"All {valid_count} chunks valid"))

        # ── 8. chunk_manifest.json (optional) ────────────────────────────────
        manifest_path = chunks_dir / "chunk_manifest.json"
        if not manifest_path.exists():
            checks.append(_skip("chunk_manifest", "chunk_manifest.json not found"))
        else:
            try:
                manifest = ChunkManifest(**json.loads(manifest_path.read_text()))
                if doc_md.exists():
                    actual_sha = self.sha256_text(doc_md.read_text(encoding="utf-8"))
                    if manifest.source_document_md_sha256 == actual_sha:
                        checks.append(_pass(
                            "chunk_manifest",
                            "chunk_manifest.json valid; source SHA-256 matches document.md",
                        ))
                    else:
                        msg = "Manifest source SHA-256 does not match document.md — file may have changed"
                        checks.append(_fail("chunk_manifest", msg))
                        errors.append(msg)
                else:
                    msg = "chunk_manifest.json valid but document.md missing; cannot verify SHA-256"
                    checks.append(_warn("chunk_manifest", msg))
                    warnings.append(msg)
            except Exception as exc:
                msg = f"chunk_manifest.json invalid: {exc}"
                checks.append(_fail("chunk_manifest", msg))
                errors.append(msg)

        report = _build_report(document_id, checks, warnings, errors)

        with get_session() as session:
            repository.create_integrity_report(
                session,
                document_id=document_id,
                status=report.status,
                report_data=report.model_dump(),
            )

        return report


def _build_report(
    document_id: str,
    checks: List[IntegrityCheck],
    warnings: List[str],
    errors: List[str],
) -> IntegrityReport:
    statuses = {c.status for c in checks}
    if "fail" in statuses:
        overall = "fail"
    elif "warn" in statuses:
        overall = "warn"
    else:
        overall = "pass"
    return IntegrityReport(
        document_id=document_id,
        status=overall,
        checks=checks,
        warnings=warnings,
        errors=errors,
    )
