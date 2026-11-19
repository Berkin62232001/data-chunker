from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

_VALID_STATUSES = {"success", "partial", "failed"}


class ConversionMetadata(BaseModel):
    document_id: str
    original_filename: str
    source_mime_type: Optional[str]
    selected_pipeline: str
    conversion_status: str        # "success" | "partial" | "failed"
    created_at: str
    output_files: List[str]
    estimated_character_count: int
    estimated_token_count: int    # rough char / 4 estimate

    @field_validator("conversion_status")
    @classmethod
    def status_must_be_valid(cls, v: str) -> str:
        if v not in _VALID_STATUSES:
            raise ValueError(f"conversion_status must be one of {_VALID_STATUSES}, got {v!r}")
        return v


class ExtractionReport(BaseModel):
    success: bool
    converter_used: str
    warnings: List[str]
    errors: List[str]
    fallback_used: bool
    ocr_used: bool = False
    ocr_provider: Optional[str] = None
    ocr_language: Optional[str] = None
    ocr_pages_processed: Optional[int] = None
    ocr_succeeded: Optional[bool] = None
    ocr_warnings: List[str] = Field(default_factory=list)
    ocr_error: Optional[str] = None
    ocr_text_char_count: int = 0


class ConversionResult(BaseModel):
    document_id: str
    conversion_status: str
    markdown_path: str
    markdown_preview: str         # first 2000 chars of document.md
    metadata: ConversionMetadata
    report: ExtractionReport
