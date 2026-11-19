from typing import List, Literal, Optional

from pydantic import BaseModel, field_validator


class IndexManifest(BaseModel):
    document_id: str
    collection: str
    indexed_chunks: int
    embedding_dim: int
    embedding_provider: str
    embedding_model: Optional[str] = None
    indexed_at: str
    qdrant_url: Optional[str]


class IndexResponse(BaseModel):
    document_id: str
    qdrant_configured: bool
    qdrant_available: bool = True
    collection_name: str
    indexed_chunks: int
    vector_size: Optional[int]
    embedding_provider: str
    embedding_model: str
    status: Literal["indexed"] = "indexed"
    collection: str
    qdrant_url_configured: bool
    manifest_path: Optional[str] = None


class SemanticSearchRequest(BaseModel):
    query: str
    top_k: int = 5

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


class SemanticSearchResultItem(BaseModel):
    chunk_id: str
    chunk_index: int
    section_path: List[str]
    content_type: str
    score: float
    estimated_tokens: int
    text_preview: str
    retrieval_mode: Literal["semantic"] = "semantic"


class SemanticSearchResponse(BaseModel):
    document_id: str
    query: str
    top_k: int
    results: List[SemanticSearchResultItem]
    search_mode: Literal["semantic"] = "semantic"
