from typing import List, Optional

from pydantic import BaseModel, field_validator


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    include_full_text: bool = False

    @field_validator("query")
    @classmethod
    def query_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("query must not be empty")
        return v

    @field_validator("top_k")
    @classmethod
    def top_k_in_range(cls, v: int) -> int:
        if v < 1:
            raise ValueError("top_k must be >= 1")
        if v > 50:
            raise ValueError("top_k must be <= 50")
        return v


class SearchResultItem(BaseModel):
    chunk_id: str
    chunk_index: int
    section_path: List[str]
    content_type: str
    score: float       # Relative BM25 ranking score, not answer confidence
    estimated_tokens: int
    text_preview: str       # first 300 chars
    text: Optional[str]     # full text when include_full_text=True


class SearchResponse(BaseModel):
    document_id: str
    query: str
    top_k: int
    total_chunks_searched: int
    results: List[SearchResultItem]
