from typing import List, Optional

from services.embedding.base import EmbeddingServiceBase


class PlaceholderEmbeddingService(EmbeddingServiceBase):
    """Skeleton for a real embedding provider (e.g. OpenAI text-embedding-3-small).
    TODO Phase 12: implement real embedding calls and wire in via config."""

    @property
    def dim(self) -> int:
        return 1536  # OpenAI text-embedding-3-small output dimension

    @property
    def vector_size(self) -> Optional[int]:
        return self.dim

    @property
    def provider_name(self) -> str:
        return "placeholder"

    @property
    def model_name(self) -> str:
        return "placeholder"

    def embed_text(self, text: str) -> List[float]:
        raise NotImplementedError(
            "Real embedding provider not configured. "
            "Use MockEmbeddingService or implement a concrete provider."
        )
