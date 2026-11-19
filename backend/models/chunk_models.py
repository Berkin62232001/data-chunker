import re
from typing import List

from pydantic import BaseModel, field_validator

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_VALID_CONTENT_TYPES = {"text", "code", "table"}


class Chunk(BaseModel):
    chunk_id: str
    document_id: str
    document_version: str
    section_path: List[str]
    chunk_index: int
    content_type: str       # "text" | "code" | "table"
    text: str
    char_count: int
    estimated_tokens: int
    sha256: str

    @field_validator("sha256")
    @classmethod
    def sha256_must_be_hex64(cls, v: str) -> str:
        if not _HEX64.match(v):
            raise ValueError(f"sha256 must be 64 lowercase hex chars, got {v!r}")
        return v

    @field_validator("content_type")
    @classmethod
    def content_type_must_be_known(cls, v: str) -> str:
        if v not in _VALID_CONTENT_TYPES:
            raise ValueError(f"content_type must be one of {_VALID_CONTENT_TYPES}, got {v!r}")
        return v

    @field_validator("char_count")
    @classmethod
    def char_count_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("char_count must be >= 0")
        return v

    @field_validator("estimated_tokens")
    @classmethod
    def tokens_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("estimated_tokens must be >= 1")
        return v


class ChunkManifest(BaseModel):
    document_id: str
    total_chunks: int
    total_estimated_tokens: int
    average_chunk_tokens: int
    created_at: str
    chunking_strategy: str
    source_document_md_sha256: str

    @field_validator("source_document_md_sha256")
    @classmethod
    def sha256_must_be_hex64(cls, v: str) -> str:
        if not _HEX64.match(v):
            raise ValueError(f"source_document_md_sha256 must be 64 lowercase hex chars")
        return v

    @field_validator("total_chunks")
    @classmethod
    def total_chunks_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("total_chunks must be >= 0")
        return v


class ChunkPreview(BaseModel):
    chunk_id: str
    chunk_index: int
    section_path: List[str]
    content_type: str
    text_preview: str       # first 200 chars
    char_count: int
    estimated_tokens: int


class ChunkingResult(BaseModel):
    document_id: str
    manifest: ChunkManifest
    chunks_preview: List[ChunkPreview]
