from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class UploadSecurityInfo(BaseModel):
    extension: str
    mime_type: Optional[str]
    size_bytes: int
    extension_allowed: bool
    size_within_limit: bool
    mime_allowed: bool


class InjectionWarning(BaseModel):
    chunk_id: str
    chunk_index: int
    matched_pattern: str
    text_excerpt: str


class PayloadSafetyInfo(BaseModel):
    safety_instruction_present: bool
    payloads_generated: int


class SecurityReport(BaseModel):
    document_id: str
    generated_at: str
    local_only_mode: bool
    upload: UploadSecurityInfo
    injection_warnings: List[InjectionWarning]
    injection_scan_complete: bool
    payload_safety: PayloadSafetyInfo
    recent_audit_entries: List[Dict[str, Any]]
