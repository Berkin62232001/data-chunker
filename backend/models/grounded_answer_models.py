from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


GroundedProvider = Literal["mock", "claude", "openai", "gemini"]
GroundedRetrievalMode = Literal["keyword", "semantic", "hybrid"]
EvidenceStrength = Literal["strong", "moderate", "weak", "none"]


class GroundedAnswerRequest(BaseModel):
    question: str
    retrieval_mode: GroundedRetrievalMode = "hybrid"
    top_k: int = 5
    provider: GroundedProvider = "mock"
    token_budget: Optional[int] = None

    @field_validator("question")
    @classmethod
    def question_not_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("question must not be empty")
        return value

    @field_validator("top_k")
    @classmethod
    def top_k_in_range(cls, value: int) -> int:
        if value < 1:
            raise ValueError("top_k must be >= 1")
        if value > 50:
            raise ValueError("top_k must be <= 50")
        return value

    @field_validator("token_budget")
    @classmethod
    def token_budget_positive(cls, value: Optional[int]) -> Optional[int]:
        if value is not None and value < 1:
            raise ValueError("token_budget must be >= 1")
        return value


class GroundedCitation(BaseModel):
    citation_id: str
    chunk_id: str
    chunk_index: int
    section_path: List[str] = Field(default_factory=list)
    page_number: Optional[int] = None
    source_label: str
    score: Optional[float] = None
    text_preview: str
    estimated_tokens: int


class GroundedEvidence(BaseModel):
    evidence_strength: EvidenceStrength
    retrieved_chunks_count: int
    citations_count: int
    total_context_tokens: int
    top_score: Optional[float] = None
    average_score: Optional[float] = None
    warnings: List[str] = Field(default_factory=list)


class GroundedAnswerResponse(BaseModel):
    document_id: str
    question: str
    answer: str
    provider: GroundedProvider
    retrieval_mode: GroundedRetrievalMode
    citations: List[GroundedCitation] = Field(default_factory=list)
    evidence: GroundedEvidence
    payload_id: Optional[str] = None
    call_id: Optional[str] = None
    local_only_mode: bool
    warnings: List[str] = Field(default_factory=list)
