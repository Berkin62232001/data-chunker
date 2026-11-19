from typing import List, Optional

from pydantic import BaseModel


class UploadResponse(BaseModel):
    document_id: str
    original_filename: str
    stored_filename: str
    size_bytes: int
    mime_type: Optional[str]
    status: str


class DocumentPreview(BaseModel):
    document_id: str
    exists: bool
    preview: str
    char_count: int
    truncated: bool
    source: str


class InitializeResult(BaseModel):
    document_id: str
    profile_created: bool
    pipeline_created: bool
    current_phase: str
    warnings: List[str]
