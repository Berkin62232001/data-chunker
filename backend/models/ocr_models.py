from typing import List, Optional

from pydantic import BaseModel, Field


class OCRResult(BaseModel):
    text: str = ""
    provider: str
    language: str
    pages_processed: int = 0
    confidence: Optional[float] = None
    warnings: List[str] = Field(default_factory=list)
    artifacts: List[str] = Field(default_factory=list)
    succeeded: bool = False
    error: Optional[str] = None


class OCRAvailability(BaseModel):
    available: bool
    provider: str
    language: str
    warnings: List[str] = Field(default_factory=list)
    error: Optional[str] = None


class OCRStatusResponse(BaseModel):
    document_id: str
    ocr_enabled: bool
    ocr_available: bool
    requires_ocr: Optional[bool] = None
    ocr_supported: bool
    provider: str
    language: str
    warnings: List[str] = Field(default_factory=list)
    error: Optional[str] = None
