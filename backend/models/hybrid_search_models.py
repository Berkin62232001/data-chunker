from typing import List, Literal

from pydantic import BaseModel, field_validator, model_validator


class HybridSearchRequest(BaseModel):
    query: str
    top_k: int = 8
    keyword_weight: float = 0.4
    semantic_weight: float = 0.6

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

    @field_validator("keyword_weight", "semantic_weight")
    @classmethod
    def weight_non_negative(cls, v: float) -> float:
        if v < 0.0:
            raise ValueError("weights must be >= 0.0")
        return round(v, 6)

    @model_validator(mode="after")
    def weights_sum_positive(self) -> "HybridSearchRequest":
        if self.keyword_weight + self.semantic_weight <= 0.0:
            raise ValueError("keyword_weight + semantic_weight must be > 0")
        return self


class HybridResultItem(BaseModel):
    chunk_id: str
    chunk_index: int
    section_path: List[str]
    content_type: str
    combined_score: float
    keyword_score: float    # normalised to [0, 1]; 0 if chunk not found by keyword search
    semantic_score: float   # normalised to [0, 1]; 0 if chunk not found by semantic search
    estimated_tokens: int
    text_preview: str


class HybridSearchResponse(BaseModel):
    document_id: str
    query: str
    top_k: int
    keyword_weight: float
    semantic_weight: float
    semantic_available: bool
    results: List[HybridResultItem]
    search_mode: Literal["hybrid"] = "hybrid"
