from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, field_validator


class LLMPayloadRequest(BaseModel):
    query: str
    top_k: int = 5
    provider: Literal["claude", "openai", "gemini", "generic"] = "generic"
    # hybrid uses keyword+semantic and falls back to keyword when Qdrant is unavailable
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


class PayloadIntegrity(BaseModel):
    all_chunks_verified: bool
    verified_count: int
    failed_chunk_ids: List[str]


class TokenBudgetInfo(BaseModel):
    requested_top_k: int
    selected_chunk_count: int
    estimated_context_tokens: int
    skipped_chunks_due_to_budget: int


class LLMPayloadResponse(BaseModel):
    document_id: str
    provider: str
    query: str
    chunks_used: int
    total_estimated_tokens: int
    payload_path: str
    universal_payload: Dict[str, Any]
    formatted_context: str
    integrity: PayloadIntegrity
    token_budget: TokenBudgetInfo


class EstimateContextRequest(BaseModel):
    query: str
    top_k: int = 5
    provider: Literal["claude", "openai", "gemini", "generic"] = "generic"
    retrieval_mode: Literal["keyword", "semantic", "hybrid"] = "hybrid"
    budget: Optional[int] = None

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

    @field_validator("budget")
    @classmethod
    def budget_positive(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 1:
            raise ValueError("budget must be >= 1")
        return v


class EstimateContextResponse(BaseModel):
    document_id: str
    provider: str
    query: str
    requested_top_k: int
    selected_chunk_count: int
    estimated_context_tokens: int
    skipped_chunks_due_to_budget: int
    budget_used: int
