from typing import Optional

from pydantic import BaseModel


class VectorStatusResponse(BaseModel):
    qdrant_configured: bool
    qdrant_available: bool
    collection_name: str
    embedding_provider: str
    embedding_model: Optional[str] = None
    vector_size: Optional[int] = None
    lm_studio_base_url: Optional[str] = None
    error: Optional[str] = None


class DocumentIndexStatusResponse(BaseModel):
    document_id: str
    qdrant_configured: bool
    qdrant_available: bool
    collection_name: str
    indexed: bool
    indexed_chunks: int
    total_chunks: Optional[int] = None
    embedding_provider: str
    embedding_model: Optional[str] = None
    vector_size: Optional[int] = None
    indexed_embedding_provider: Optional[str] = None
    indexed_embedding_model: Optional[str] = None
    indexed_vector_size: Optional[int] = None
    error: Optional[str] = None
