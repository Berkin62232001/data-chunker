from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True)
    document_id = Column(String, unique=True, nullable=False, index=True)
    original_filename = Column(String, nullable=False)
    stored_filename = Column(String, nullable=False)
    mime_type = Column(String)
    file_size_bytes = Column(Integer)
    status = Column(String, default="raw")
    current_phase = Column(String, default="upload")
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class DocumentProfile(Base):
    __tablename__ = "document_profiles"

    id = Column(Integer, primary_key=True)
    document_id = Column(String, nullable=False, index=True)
    detected_type = Column(String)
    mime_type = Column(String)
    page_count = Column(Integer)
    requires_ocr = Column(Boolean, default=False)
    profile_json = Column(Text)
    created_at = Column(DateTime(timezone=True), default=utc_now)


class PipelineDecision(Base):
    __tablename__ = "pipeline_decisions"

    id = Column(Integer, primary_key=True)
    document_id = Column(String, nullable=False, index=True)
    selected_pipeline = Column(String, nullable=False)
    output_format = Column(String)
    llm_send_format = Column(String)
    decision_json = Column(Text)
    created_at = Column(DateTime(timezone=True), default=utc_now)


class Conversion(Base):
    __tablename__ = "conversions"

    id = Column(Integer, primary_key=True)
    document_id = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False)
    converter_used = Column(String)
    estimated_tokens = Column(Integer)
    warnings_json = Column(Text)
    created_at = Column(DateTime(timezone=True), default=utc_now)


class ChunkManifest(Base):
    __tablename__ = "chunk_manifests"

    id = Column(Integer, primary_key=True)
    document_id = Column(String, nullable=False, index=True)
    total_chunks = Column(Integer, nullable=False)
    total_estimated_tokens = Column(Integer)
    chunking_strategy = Column(String)
    manifest_json = Column(Text)
    created_at = Column(DateTime(timezone=True), default=utc_now)


class IntegrityReport(Base):
    __tablename__ = "integrity_reports"

    id = Column(Integer, primary_key=True)
    document_id = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False)
    report_json = Column(Text)
    created_at = Column(DateTime(timezone=True), default=utc_now)


class LLMPayload(Base):
    __tablename__ = "llm_payloads"

    id = Column(Integer, primary_key=True)
    payload_id = Column(String, unique=True, nullable=False, index=True)
    document_id = Column(String, index=True)
    project_id = Column(String, index=True)
    provider = Column(String)
    query = Column(Text)
    retrieval_mode = Column(String)
    selected_chunk_count = Column(Integer)
    estimated_context_tokens = Column(Integer)
    created_at = Column(DateTime(timezone=True), default=utc_now)


class LLMCall(Base):
    __tablename__ = "llm_calls"

    id = Column(Integer, primary_key=True)
    call_id = Column(String, unique=True, nullable=False, index=True)
    document_id = Column(String, index=True)
    project_id = Column(String, index=True)
    provider = Column(String)
    query = Column(Text)
    status = Column(String)
    payload_id = Column(String)
    error_message = Column(Text)
    created_at = Column(DateTime(timezone=True), default=utc_now)


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True)
    project_id = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class ProjectDocument(Base):
    __tablename__ = "project_documents"

    id = Column(Integer, primary_key=True)
    project_id = Column(String, nullable=False, index=True)
    document_id = Column(String, nullable=False, index=True)
    added_at = Column(DateTime(timezone=True), default=utc_now)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id = Column(Integer, primary_key=True)
    event_type = Column(String, nullable=False, index=True)
    document_id = Column(String, index=True)
    project_id = Column(String, index=True)
    payload_id = Column(String)
    metadata_json = Column(Text)
    created_at = Column(DateTime(timezone=True), default=utc_now)


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String, primary_key=True)
    document_id = Column(String, index=True)
    job_type = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, index=True, default="queued")
    progress_percent = Column(Integer, default=0)
    current_step = Column(String)
    message = Column(Text)
    request_json = Column(Text)
    result_json = Column(Text)
    error = Column(Text)
    retry_count = Column(Integer, default=0)
    retry_of_job_id = Column(String, index=True)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    started_at = Column(DateTime(timezone=True))
    finished_at = Column(DateTime(timezone=True))
    canceled_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
