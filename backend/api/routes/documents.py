from utils.storage_paths import storage_path
import csv
import io
import json
import logging
import math
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from api.routes.audit_routes import _parse_json
from core.config import settings
from db import repository
from db.session import get_session
from models.db_response_models import (
    AuditEventItem,
    AuditRecentResponse,
    ChunkSummary,
    ConversionSummary,
    DocumentDetail,
    DocumentListItem,
    DocumentListResponse,
    DocumentPaginatedResponse,
    DocumentSummary,
    IntegritySummary,
    LLMCallSummary,
    PayloadSummary,
    PipelineSummary,
    ProfileSummary,
)
from services.security_report_service import SecurityReportService

logger = logging.getLogger(__name__)

_security_svc = SecurityReportService()

router = APIRouter(prefix="/api/documents")


@router.get("", response_model=DocumentListResponse)
def list_documents() -> DocumentListResponse:
    with get_session() as session:
        docs = repository.list_documents(session)
        items = [
            DocumentListItem(
                document_id=d.document_id,
                original_filename=d.original_filename,
                mime_type=d.mime_type,
                file_size_bytes=d.file_size_bytes or 0,
                status=d.status or "raw",
                current_phase=d.current_phase or "upload",
                created_at=d.created_at,
                updated_at=d.updated_at,
            )
            for d in docs
        ]
    return DocumentListResponse(total=len(items), documents=items)


@router.get("/paginated", response_model=DocumentPaginatedResponse)
def list_documents_paginated(
    page: int = 1,
    page_size: int = 20,
    search: str = "",
    phase: str = "",
    sort: str = "newest",
) -> DocumentPaginatedResponse:
    safe_page = max(1, page)
    safe_size = min(max(1, page_size), 100)
    with get_session() as session:
        docs, total = repository.list_documents_paginated(
            session,
            page=safe_page,
            page_size=safe_size,
            search=search,
            phase=phase,
            sort=sort,
        )
        pages = math.ceil(total / safe_size) if safe_size > 0 else 1
        items = [
            DocumentListItem(
                document_id=d.document_id,
                original_filename=d.original_filename,
                mime_type=d.mime_type,
                file_size_bytes=d.file_size_bytes or 0,
                status=d.status or "raw",
                current_phase=d.current_phase or "upload",
                created_at=d.created_at,
                updated_at=d.updated_at,
            )
            for d in docs
        ]
    return DocumentPaginatedResponse(
        total=total,
        page=safe_page,
        page_size=safe_size,
        pages=pages,
        documents=items,
    )


_CSV_FIELDS = [
    "document_id", "original_filename", "mime_type", "file_size_bytes",
    "status", "current_phase", "created_at", "updated_at",
]


@router.get("/export.csv")
def export_documents_csv(
    search: str = "",
    phase: str = "",
    sort: str = "newest",
) -> Response:
    with get_session() as session:
        docs, _ = repository.list_documents_paginated(
            session, page=1, page_size=10000, search=search, phase=phase, sort=sort,
        )
        rows = [
            {
                "document_id": d.document_id,
                "original_filename": d.original_filename,
                "mime_type": d.mime_type or "",
                "file_size_bytes": d.file_size_bytes or 0,
                "status": d.status or "raw",
                "current_phase": d.current_phase or "upload",
                "created_at": d.created_at.isoformat() if d.created_at else "",
                "updated_at": d.updated_at.isoformat() if d.updated_at else "",
            }
            for d in docs
        ]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_CSV_FIELDS)
    writer.writeheader()
    writer.writerows(rows)
    return Response(
        content=buf.getvalue().encode("utf-8"),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="documents_export.csv"'},
    )


@router.get("/{document_id}/summary", response_model=DocumentSummary)
def get_document_summary(document_id: str) -> DocumentSummary:
    with get_session() as session:
        doc = repository.get_document(session, document_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found.")

        prof = repository.get_latest_profile(session, document_id)
        pipe = repository.get_latest_pipeline_decision(session, document_id)
        conv = repository.get_latest_conversion(session, document_id)
        chunks = repository.get_latest_chunk_manifest(session, document_id)
        integ = repository.get_latest_integrity_report(session, document_id)

        summary = DocumentSummary(
            document_id=doc.document_id,
            original_filename=doc.original_filename,
            mime_type=doc.mime_type,
            file_size_bytes=doc.file_size_bytes or 0,
            status=doc.status or "raw",
            current_phase=doc.current_phase or "upload",
            created_at=doc.created_at,
            profile=ProfileSummary(
                detected_type=prof.detected_type,
                mime_type=prof.mime_type,
                page_count=prof.page_count,
                requires_ocr=prof.requires_ocr or False,
                created_at=prof.created_at,
            ) if prof else None,
            pipeline=PipelineSummary(
                selected_pipeline=pipe.selected_pipeline,
                output_format=pipe.output_format,
                created_at=pipe.created_at,
            ) if pipe else None,
            conversion=ConversionSummary(
                status=conv.status,
                converter_used=conv.converter_used,
                estimated_tokens=conv.estimated_tokens,
                created_at=conv.created_at,
            ) if conv else None,
            chunks=ChunkSummary(
                total_chunks=chunks.total_chunks,
                total_estimated_tokens=chunks.total_estimated_tokens,
                chunking_strategy=chunks.chunking_strategy,
                created_at=chunks.created_at,
            ) if chunks else None,
            integrity_status=integ.status if integ else None,
            security_warnings_count=None,
            preview_excerpt=None,
        )

    security_warnings: Optional[int] = None
    try:
        report = _security_svc.generate(document_id)
        security_warnings = len(report.injection_warnings)
    except Exception as exc:
        logger.warning("Security report generation failed for document %s: %s", document_id, exc)

    preview_excerpt: Optional[str] = None
    md_path = storage_path(settings.converted_dir, document_id, "document.md")
    if md_path.exists():
        try:
            text = md_path.read_text(encoding="utf-8")
            preview_excerpt = text[:3000]
        except Exception as exc:
            logger.warning("Preview excerpt read failed for document %s: %s", document_id, exc)

    summary.security_warnings_count = security_warnings
    summary.preview_excerpt = preview_excerpt
    return summary


@router.get("/{document_id}/audit", response_model=AuditRecentResponse)
def get_document_audit(document_id: str, limit: int = 50) -> AuditRecentResponse:
    with get_session() as session:
        doc = repository.get_document(session, document_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found.")
        events = repository.list_recent_audit_events(
            session,
            limit=min(limit, 200),
            document_id=document_id,
        )
        items = [
            AuditEventItem(
                id=e.id,
                event_type=e.event_type,
                document_id=e.document_id,
                project_id=e.project_id,
                payload_id=e.payload_id,
                metadata=_parse_json(e.metadata_json),
                created_at=e.created_at,
            )
            for e in events
        ]
    return AuditRecentResponse(total=len(items), events=items)


@router.get("/{document_id}", response_model=DocumentDetail)
def get_document(document_id: str) -> DocumentDetail:
    with get_session() as session:
        doc = repository.get_document(session, document_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found.")

        prof = repository.get_latest_profile(session, document_id)
        pipe = repository.get_latest_pipeline_decision(session, document_id)
        conv = repository.get_latest_conversion(session, document_id)
        chunks = repository.get_latest_chunk_manifest(session, document_id)
        integ = repository.get_latest_integrity_report(session, document_id)
        payloads = repository.list_payloads_for_document(session, document_id, limit=5)
        calls = repository.list_calls_for_document(session, document_id, limit=5)

        return DocumentDetail(
            document_id=doc.document_id,
            original_filename=doc.original_filename,
            mime_type=doc.mime_type,
            file_size_bytes=doc.file_size_bytes or 0,
            status=doc.status or "raw",
            current_phase=doc.current_phase or "upload",
            created_at=doc.created_at,
            updated_at=doc.updated_at,
            profile=ProfileSummary(
                detected_type=prof.detected_type,
                mime_type=prof.mime_type,
                page_count=prof.page_count,
                requires_ocr=prof.requires_ocr or False,
                created_at=prof.created_at,
            ) if prof else None,
            pipeline=PipelineSummary(
                selected_pipeline=pipe.selected_pipeline,
                output_format=pipe.output_format,
                created_at=pipe.created_at,
            ) if pipe else None,
            conversion=ConversionSummary(
                status=conv.status,
                converter_used=conv.converter_used,
                estimated_tokens=conv.estimated_tokens,
                created_at=conv.created_at,
            ) if conv else None,
            chunks=ChunkSummary(
                total_chunks=chunks.total_chunks,
                total_estimated_tokens=chunks.total_estimated_tokens,
                chunking_strategy=chunks.chunking_strategy,
                created_at=chunks.created_at,
            ) if chunks else None,
            integrity=IntegritySummary(
                status=integ.status,
                created_at=integ.created_at,
            ) if integ else None,
            recent_payloads=[
                PayloadSummary(
                    payload_id=p.payload_id,
                    provider=p.provider or "",
                    query=p.query or "",
                    selected_chunk_count=p.selected_chunk_count or 0,
                    estimated_context_tokens=p.estimated_context_tokens or 0,
                    created_at=p.created_at,
                )
                for p in payloads
            ],
            recent_llm_calls=[
                LLMCallSummary(
                    call_id=c.call_id,
                    provider=c.provider or "",
                    query=c.query or "",
                    status=c.status or "",
                    created_at=c.created_at,
                )
                for c in calls
            ],
        )
