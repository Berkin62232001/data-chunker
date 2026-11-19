from typing import List, Literal, Optional

from pydantic import BaseModel, field_validator


class Project(BaseModel):
    project_id: str
    name: str
    document_ids: List[str]
    created_at: str


class ProjectCreateRequest(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be empty")
        return v


class AddDocumentRequest(BaseModel):
    document_id: str

    @field_validator("document_id")
    @classmethod
    def doc_id_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("document_id must not be empty")
        return v


class ProjectSearchRequest(BaseModel):
    query: str
    top_k: int = 10
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


class ProjectSearchResultItem(BaseModel):
    document_id: str
    source_filename: str
    chunk_id: str
    chunk_index: int
    section_path: List[str]
    content_type: str
    score: float
    estimated_tokens: int
    text_preview: str
    text: Optional[str]


class ProjectSearchResponse(BaseModel):
    project_id: str
    query: str
    top_k: int
    documents_searched: int
    total_chunks_searched: int
    results: List[ProjectSearchResultItem]


class ProjectAskRequest(BaseModel):
    query: str
    top_k: int = 10
    provider: Literal["mock", "claude", "openai", "gemini"] = "mock"
    retrieval_mode: Literal["keyword", "semantic", "hybrid"] = "hybrid"

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


class ProjectAskResponse(BaseModel):
    answer: str
    provider: str
    project_id: str
    chunks_used: int
    document_count: int
    estimated_context_tokens: int
