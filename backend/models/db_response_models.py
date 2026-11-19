from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


# ── Document list / detail ────────────────────────────────────────────────────

class DocumentListItem(BaseModel):
    document_id: str
    original_filename: str
    mime_type: Optional[str]
    file_size_bytes: int
    status: str
    current_phase: str
    created_at: datetime
    updated_at: datetime


class DocumentListResponse(BaseModel):
    total: int
    documents: List[DocumentListItem]


class ProfileSummary(BaseModel):
    detected_type: Optional[str]
    mime_type: Optional[str]
    page_count: Optional[int]
    requires_ocr: bool
    created_at: datetime


class PipelineSummary(BaseModel):
    selected_pipeline: str
    output_format: Optional[str]
    created_at: datetime


class ConversionSummary(BaseModel):
    status: str
    converter_used: Optional[str]
    estimated_tokens: Optional[int]
    created_at: datetime


class ChunkSummary(BaseModel):
    total_chunks: int
    total_estimated_tokens: Optional[int]
    chunking_strategy: Optional[str]
    created_at: datetime


class IntegritySummary(BaseModel):
    status: str
    created_at: datetime


class PayloadSummary(BaseModel):
    payload_id: str
    provider: str
    query: str
    selected_chunk_count: int
    estimated_context_tokens: int
    created_at: datetime


class LLMCallSummary(BaseModel):
    call_id: str
    provider: str
    query: str
    status: str
    created_at: datetime


class DocumentDetail(BaseModel):
    document_id: str
    original_filename: str
    mime_type: Optional[str]
    file_size_bytes: int
    status: str
    current_phase: str
    created_at: datetime
    updated_at: datetime
    profile: Optional[ProfileSummary]
    pipeline: Optional[PipelineSummary]
    conversion: Optional[ConversionSummary]
    chunks: Optional[ChunkSummary]
    integrity: Optional[IntegritySummary]
    recent_payloads: List[PayloadSummary]
    recent_llm_calls: List[LLMCallSummary]


# ── Project list ──────────────────────────────────────────────────────────────

class ProjectListItem(BaseModel):
    project_id: str
    name: str
    document_count: int
    created_at: datetime
    updated_at: datetime


class ProjectListResponse(BaseModel):
    total: int
    projects: List[ProjectListItem]


# ── Audit events ──────────────────────────────────────────────────────────────

class AuditEventItem(BaseModel):
    id: int
    event_type: str
    document_id: Optional[str]
    project_id: Optional[str]
    payload_id: Optional[str]
    metadata: Dict[str, Any]
    created_at: datetime


class AuditRecentResponse(BaseModel):
    total: int
    events: List[AuditEventItem]


# ── Dashboard stats ───────────────────────────────────────────────────────────

class DashboardStats(BaseModel):
    total_documents: int
    total_projects: int
    completed_documents: int
    documents_in_progress: int


# ── Paginated document list ───────────────────────────────────────────────────

class DocumentPaginatedResponse(BaseModel):
    total: int
    page: int
    page_size: int
    pages: int
    documents: List[DocumentListItem]


# ── Document summary (read-only, no raw paths) ─────────────────────────────────

class DocumentSummary(BaseModel):
    document_id: str
    original_filename: str
    mime_type: Optional[str]
    file_size_bytes: int
    status: str
    current_phase: str
    created_at: datetime
    profile: Optional[ProfileSummary]
    pipeline: Optional[PipelineSummary]
    conversion: Optional[ConversionSummary]
    chunks: Optional[ChunkSummary]
    integrity_status: Optional[str]
    security_warnings_count: Optional[int]
    preview_excerpt: Optional[str]
