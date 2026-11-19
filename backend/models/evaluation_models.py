from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


RetrievalEvaluationMode = Literal["keyword", "semantic", "hybrid"]


class TokenEfficiencySummary(BaseModel):
    document_id: str
    original_estimated_tokens: Optional[int] = None
    converted_estimated_tokens: Optional[int] = None
    total_chunk_tokens: Optional[int] = None
    selected_context_tokens: Optional[int] = None
    token_reduction_percent_vs_original: Optional[float] = None
    token_reduction_percent_vs_converted: Optional[float] = None
    interpretation: str
    warnings: List[str] = Field(default_factory=list)


class ChunkQualityReport(BaseModel):
    document_id: str
    total_chunks: int
    total_estimated_tokens: int
    average_chunk_tokens: int
    min_chunk_tokens: int
    max_chunk_tokens: int
    empty_chunks_count: int
    missing_text_count: int
    missing_metadata_count: int
    oversized_chunks_count: int
    undersized_chunks_count: int
    duplicate_text_chunks_count: int
    section_path_coverage_percent: float
    table_chunks_count: int
    ocr_chunks_count: int
    quality_score: float
    warnings: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)


class RetrievedChunkSummary(BaseModel):
    chunk_id: str
    chunk_index: int
    section_path: List[str]
    content_type: str
    score: float
    estimated_tokens: int
    text_preview: str


class RetrievalEvaluationRequest(BaseModel):
    query: str
    retrieval_mode: RetrievalEvaluationMode = "keyword"
    top_k: int = 5
    expected_terms: List[str] = Field(default_factory=list)
    expected_section: Optional[str] = None

    @field_validator("query")
    @classmethod
    def query_not_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("query must not be empty")
        return value

    @field_validator("top_k")
    @classmethod
    def top_k_in_range(cls, value: int) -> int:
        if value < 1:
            raise ValueError("top_k must be >= 1")
        if value > 50:
            raise ValueError("top_k must be <= 50")
        return value

    @field_validator("expected_terms")
    @classmethod
    def normalize_expected_terms(cls, value: List[str]) -> List[str]:
        return [term.strip() for term in value if term.strip()]

    @field_validator("expected_section")
    @classmethod
    def normalize_expected_section(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        return value or None


class RetrievalEvaluationResponse(BaseModel):
    document_id: str
    query: str
    retrieval_mode: RetrievalEvaluationMode
    top_k: int
    total_chunks_searched: int
    returned_chunks_count: int
    total_context_tokens: int
    average_result_score: Optional[float] = None
    top_score: Optional[float] = None
    low_score_results_count: int  # Absolute threshold is skipped for keyword-only retrieval
    expected_terms_found: List[str] = Field(default_factory=list)
    expected_terms_missing: List[str] = Field(default_factory=list)
    matched_expected_terms_count: int
    expected_section: Optional[str] = None
    expected_section_hit: Optional[bool] = None
    retrieval_score_estimate: float
    token_efficiency_estimate: TokenEfficiencySummary
    selected_results: List[RetrievedChunkSummary] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)


class EvaluationSetQuery(BaseModel):
    query: str
    expected_terms: List[str] = Field(default_factory=list)
    expected_section: Optional[str] = None

    @field_validator("query")
    @classmethod
    def query_not_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("query must not be empty")
        return value

    @field_validator("expected_terms")
    @classmethod
    def normalize_expected_terms(cls, value: List[str]) -> List[str]:
        return [term.strip() for term in value if term.strip()]

    @field_validator("expected_section")
    @classmethod
    def normalize_expected_section(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        return value or None


class RetrievalEvaluationSetRequest(BaseModel):
    retrieval_mode: RetrievalEvaluationMode = "keyword"
    top_k: int = 5
    queries: List[EvaluationSetQuery]

    @field_validator("top_k")
    @classmethod
    def top_k_in_range(cls, value: int) -> int:
        if value < 1:
            raise ValueError("top_k must be >= 1")
        if value > 50:
            raise ValueError("top_k must be <= 50")
        return value

    @field_validator("queries")
    @classmethod
    def queries_not_empty(cls, value: List[EvaluationSetQuery]) -> List[EvaluationSetQuery]:
        if not value:
            raise ValueError("queries must not be empty")
        return value


class RetrievalEvaluationSetResponse(BaseModel):
    document_id: str
    retrieval_mode: RetrievalEvaluationMode
    top_k: int
    total_queries: int
    average_retrieval_score_estimate: float
    average_context_tokens: float
    average_token_reduction_percent_vs_converted: Optional[float] = None
    queries: List[RetrievalEvaluationResponse] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
