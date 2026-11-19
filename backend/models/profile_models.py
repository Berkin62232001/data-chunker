from typing import Optional

from pydantic import BaseModel, field_validator

_VALID_CATEGORIES = {
    "pdf", "docx", "pptx", "xlsx", "csv",
    "txt", "markdown", "html", "image", "unknown",
}


class DocumentProfile(BaseModel):
    document_id: str
    original_filename: str
    stored_filename: str
    extension: str
    mime_type: Optional[str]
    size_bytes: int
    category: str          # pdf | docx | pptx | xlsx | csv | txt | markdown | html | image | unknown
    content_type: Optional[str]   # document | tabular | text | image | None
    page_count: Optional[int]
    text_extractable: Optional[bool]
    requires_ocr: bool
    has_text_layer: Optional[bool] = None
    scanned_like: Optional[bool] = None
    extracted_text_char_count: Optional[int] = None
    ocr_supported: bool = False
    ocr_reason: Optional[str] = None
    recommended_pipeline: str
    profiled_at: str

    @field_validator("category")
    @classmethod
    def category_must_be_known(cls, v: str) -> str:
        if v not in _VALID_CATEGORIES:
            raise ValueError(f"category must be one of {_VALID_CATEGORIES}, got {v!r}")
        return v
