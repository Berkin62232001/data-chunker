from typing import Literal

from pydantic import BaseModel, field_validator


class AskRequest(BaseModel):
    document_id: str
    query: str
    provider: Literal["mock", "claude", "openai", "gemini"] = "mock"
    top_k: int = 5
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


class AskResponse(BaseModel):
    answer: str
    provider: str
    chunks_used: int
    estimated_context_tokens: int
    payload_id: str
