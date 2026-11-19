"""
Thin CRUD helpers. Each function takes a Session and the values it needs.
Callers are responsible for opening a session via db.session.get_session().
"""
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from db.models import (
    AuditEvent,
    ChunkManifest,
    Conversion,
    Document,
    DocumentProfile,
    IntegrityReport,
    Job,
    LLMCall,
    LLMPayload,
    PipelineDecision,
    Project,
    ProjectDocument,
)


# ── Documents ─────────────────────────────────────────────────────────────────

def upsert_document(
    session: Session,
    *,
    document_id: str,
    original_filename: str,
    stored_filename: str,
    mime_type: Optional[str],
    file_size_bytes: int,
    status: str = "raw",
    current_phase: str = "upload",
) -> Document:
    doc = session.query(Document).filter_by(document_id=document_id).first()
    if doc is None:
        doc = Document(
            document_id=document_id,
            original_filename=original_filename,
            stored_filename=stored_filename,
            mime_type=mime_type,
            file_size_bytes=file_size_bytes,
            status=status,
            current_phase=current_phase,
        )
        session.add(doc)
    else:
        doc.status = status
        doc.current_phase = current_phase
        doc.updated_at = datetime.now(timezone.utc)
    return doc


def update_document_phase(
    session: Session,
    document_id: str,
    phase: str,
    status: Optional[str] = None,
) -> None:
    doc = session.query(Document).filter_by(document_id=document_id).first()
    if doc:
        doc.current_phase = phase
        doc.updated_at = datetime.now(timezone.utc)
        if status:
            doc.status = status


def list_documents(session: Session, limit: int = 200) -> List[Document]:
    return session.query(Document).order_by(Document.created_at.desc()).limit(limit).all()


def list_documents_paginated(
    session: Session,
    page: int = 1,
    page_size: int = 20,
    search: str = "",
    phase: str = "",
    sort: str = "newest",
) -> tuple:
    query = session.query(Document)
    if search:
        query = query.filter(Document.original_filename.ilike(f"%{search}%"))
    if phase:
        query = query.filter(Document.current_phase == phase)
    total = query.count()
    if sort == "oldest":
        query = query.order_by(Document.created_at.asc())
    else:
        query = query.order_by(Document.created_at.desc())
    offset = (page - 1) * page_size
    docs = query.offset(offset).limit(page_size).all()
    return docs, total


def get_document(session: Session, document_id: str) -> Optional[Document]:
    return session.query(Document).filter_by(document_id=document_id).first()


# ── Document profiles ─────────────────────────────────────────────────────────

def create_profile(
    session: Session,
    *,
    document_id: str,
    detected_type: Optional[str],
    mime_type: Optional[str],
    page_count: Optional[int],
    requires_ocr: bool,
    profile_data: Dict[str, Any],
) -> DocumentProfile:
    row = DocumentProfile(
        document_id=document_id,
        detected_type=detected_type,
        mime_type=mime_type,
        page_count=page_count,
        requires_ocr=requires_ocr,
        profile_json=json.dumps(profile_data, default=str),
    )
    session.add(row)
    return row


def get_latest_profile(session: Session, document_id: str) -> Optional[DocumentProfile]:
    return (
        session.query(DocumentProfile)
        .filter_by(document_id=document_id)
        .order_by(DocumentProfile.created_at.desc())
        .first()
    )


# ── Pipeline decisions ────────────────────────────────────────────────────────

def create_pipeline_decision(
    session: Session,
    *,
    document_id: str,
    selected_pipeline: str,
    output_format: str,
    llm_send_format: str,
    decision_data: Dict[str, Any],
) -> PipelineDecision:
    row = PipelineDecision(
        document_id=document_id,
        selected_pipeline=selected_pipeline,
        output_format=output_format,
        llm_send_format=llm_send_format,
        decision_json=json.dumps(decision_data, default=str),
    )
    session.add(row)
    return row


def get_latest_pipeline_decision(session: Session, document_id: str) -> Optional[PipelineDecision]:
    return (
        session.query(PipelineDecision)
        .filter_by(document_id=document_id)
        .order_by(PipelineDecision.created_at.desc())
        .first()
    )


# ── Conversions ───────────────────────────────────────────────────────────────

def create_conversion(
    session: Session,
    *,
    document_id: str,
    status: str,
    converter_used: str,
    estimated_tokens: Optional[int],
    warnings: List[str],
) -> Conversion:
    row = Conversion(
        document_id=document_id,
        status=status,
        converter_used=converter_used,
        estimated_tokens=estimated_tokens,
        warnings_json=json.dumps(warnings),
    )
    session.add(row)
    return row


def get_latest_conversion(session: Session, document_id: str) -> Optional[Conversion]:
    return (
        session.query(Conversion)
        .filter_by(document_id=document_id)
        .order_by(Conversion.created_at.desc())
        .first()
    )


# ── Chunk manifests ───────────────────────────────────────────────────────────

def create_chunk_manifest(
    session: Session,
    *,
    document_id: str,
    total_chunks: int,
    total_estimated_tokens: int,
    chunking_strategy: str,
    manifest_data: Dict[str, Any],
) -> ChunkManifest:
    row = ChunkManifest(
        document_id=document_id,
        total_chunks=total_chunks,
        total_estimated_tokens=total_estimated_tokens,
        chunking_strategy=chunking_strategy,
        manifest_json=json.dumps(manifest_data, default=str),
    )
    session.add(row)
    return row


def get_latest_chunk_manifest(session: Session, document_id: str) -> Optional[ChunkManifest]:
    return (
        session.query(ChunkManifest)
        .filter_by(document_id=document_id)
        .order_by(ChunkManifest.created_at.desc())
        .first()
    )


# ── Integrity reports ─────────────────────────────────────────────────────────

def create_integrity_report(
    session: Session,
    *,
    document_id: str,
    status: str,
    report_data: Dict[str, Any],
) -> IntegrityReport:
    row = IntegrityReport(
        document_id=document_id,
        status=status,
        report_json=json.dumps(report_data, default=str),
    )
    session.add(row)
    return row


def get_latest_integrity_report(session: Session, document_id: str) -> Optional[IntegrityReport]:
    return (
        session.query(IntegrityReport)
        .filter_by(document_id=document_id)
        .order_by(IntegrityReport.created_at.desc())
        .first()
    )


# ── LLM payloads ─────────────────────────────────────────────────────────────

def create_llm_payload(
    session: Session,
    *,
    payload_id: str,
    document_id: Optional[str],
    project_id: Optional[str],
    provider: str,
    query: str,
    retrieval_mode: Optional[str],
    selected_chunk_count: int,
    estimated_context_tokens: int,
) -> LLMPayload:
    row = LLMPayload(
        payload_id=payload_id,
        document_id=document_id,
        project_id=project_id,
        provider=provider,
        query=query,
        retrieval_mode=retrieval_mode,
        selected_chunk_count=selected_chunk_count,
        estimated_context_tokens=estimated_context_tokens,
    )
    session.add(row)
    return row


def list_payloads_for_document(
    session: Session, document_id: str, limit: int = 10
) -> List[LLMPayload]:
    return (
        session.query(LLMPayload)
        .filter_by(document_id=document_id)
        .order_by(LLMPayload.created_at.desc())
        .limit(limit)
        .all()
    )


# ── LLM calls ────────────────────────────────────────────────────────────────

def create_llm_call(
    session: Session,
    *,
    document_id: Optional[str],
    project_id: Optional[str],
    provider: str,
    query: str,
    status: str,
    payload_id: Optional[str] = None,
    error_message: Optional[str] = None,
) -> LLMCall:
    row = LLMCall(
        call_id=str(uuid.uuid4()),
        document_id=document_id,
        project_id=project_id,
        provider=provider,
        query=query,
        status=status,
        payload_id=payload_id,
        error_message=error_message,
    )
    session.add(row)
    return row


def list_calls_for_document(
    session: Session, document_id: str, limit: int = 10
) -> List[LLMCall]:
    return (
        session.query(LLMCall)
        .filter_by(document_id=document_id)
        .order_by(LLMCall.created_at.desc())
        .limit(limit)
        .all()
    )


# ── Projects ──────────────────────────────────────────────────────────────────

def upsert_project(
    session: Session,
    *,
    project_id: str,
    name: str,
    description: Optional[str] = None,
) -> Project:
    row = session.query(Project).filter_by(project_id=project_id).first()
    if row is None:
        row = Project(project_id=project_id, name=name, description=description)
        session.add(row)
    else:
        row.name = name
        row.updated_at = datetime.now(timezone.utc)
    return row


def add_project_document(
    session: Session, project_id: str, document_id: str
) -> None:
    exists = (
        session.query(ProjectDocument)
        .filter_by(project_id=project_id, document_id=document_id)
        .first()
    )
    if not exists:
        session.add(ProjectDocument(project_id=project_id, document_id=document_id))


def count_all_documents(session: Session) -> int:
    return session.query(Document).count()


def count_all_projects(session: Session) -> int:
    return session.query(Project).count()


def count_documents_by_phase(session: Session, phase: str) -> int:
    return session.query(Document).filter(Document.current_phase == phase).count()


def list_projects(session: Session) -> List[Project]:
    return session.query(Project).order_by(Project.created_at.desc()).all()


def get_project(session: Session, project_id: str) -> Optional[Project]:
    return session.query(Project).filter_by(project_id=project_id).first()


def count_project_documents(session: Session, project_id: str) -> int:
    return session.query(ProjectDocument).filter_by(project_id=project_id).count()


# ── Audit events ──────────────────────────────────────────────────────────────

def create_audit_event(
    session: Session,
    *,
    event_type: str,
    document_id: Optional[str] = None,
    project_id: Optional[str] = None,
    payload_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> AuditEvent:
    row = AuditEvent(
        event_type=event_type,
        document_id=document_id,
        project_id=project_id,
        payload_id=payload_id,
        metadata_json=json.dumps(metadata or {}, default=str),
    )
    session.add(row)
    return row


def list_recent_audit_events(
    session: Session,
    limit: int = 50,
    document_id: Optional[str] = None,
    project_id: Optional[str] = None,
    event_type: Optional[str] = None,
    payload_id: Optional[str] = None,
) -> List[AuditEvent]:
    query = session.query(AuditEvent)
    if document_id is not None:
        query = query.filter(AuditEvent.document_id == document_id)
    if project_id is not None:
        query = query.filter(AuditEvent.project_id == project_id)
    if event_type is not None:
        query = query.filter(AuditEvent.event_type == event_type)
    if payload_id is not None:
        query = query.filter(AuditEvent.payload_id == payload_id)
    return query.order_by(AuditEvent.created_at.desc()).limit(limit).all()


# ── Jobs ─────────────────────────────────────────────────────────────────────

def create_job(
    session: Session,
    *,
    job_id: str,
    document_id: Optional[str],
    job_type: str,
    status: str,
    progress_percent: int,
    current_step: Optional[str],
    message: Optional[str],
    request_json: Optional[str],
    retry_of_job_id: Optional[str] = None,
) -> Job:
    now = datetime.now(timezone.utc)
    row = Job(
        id=job_id,
        document_id=document_id,
        job_type=job_type,
        status=status,
        progress_percent=progress_percent,
        current_step=current_step,
        message=message,
        request_json=request_json,
        retry_of_job_id=retry_of_job_id,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    return row


def get_job(session: Session, job_id: str) -> Optional[Job]:
    return session.query(Job).filter_by(id=job_id).first()


def list_jobs(
    session: Session,
    *,
    document_id: Optional[str] = None,
    status: Optional[str] = None,
    job_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    sort: str = "newest",
) -> List[Job]:
    query = session.query(Job)
    if document_id:
        query = query.filter_by(document_id=document_id)
    if status:
        query = query.filter_by(status=status)
    if job_type:
        query = query.filter_by(job_type=job_type)
    order = Job.created_at.asc() if sort == "oldest" else Job.created_at.desc()
    return query.order_by(order).offset(offset).limit(limit).all()


def count_jobs(
    session: Session,
    *,
    document_id: Optional[str] = None,
    status: Optional[str] = None,
    job_type: Optional[str] = None,
) -> int:
    query = session.query(Job)
    if document_id:
        query = query.filter_by(document_id=document_id)
    if status:
        query = query.filter_by(status=status)
    if job_type:
        query = query.filter_by(job_type=job_type)
    return query.count()


def list_document_jobs(session: Session, document_id: str, limit: int = 50) -> List[Job]:
    return list_jobs(session, document_id=document_id, limit=limit)


def update_job(
    session: Session,
    job_id: str,
    **values: Any,
) -> Optional[Job]:
    row = get_job(session, job_id)
    if row is None:
        return None
    for key, value in values.items():
        if hasattr(row, key):
            setattr(row, key, value)
    row.updated_at = datetime.now(timezone.utc)
    return row


def delete_jobs(
    session: Session,
    *,
    statuses: List[str],
    older_than: datetime,
) -> int:
    rows = (
        session.query(Job)
        .filter(Job.status.in_(statuses))
        .filter(Job.created_at < older_than)
        .all()
    )
    count = len(rows)
    for row in rows:
        session.delete(row)
    return count
