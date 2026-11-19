import hashlib
from typing import List, Optional

from services.embedding.base import EmbeddingServiceBase


class DeterministicDemoEmbeddingService(EmbeddingServiceBase):
    """Deterministic fake embeddings — no external calls, safe for tests."""

    def __init__(self, dim: int = 128) -> None:
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def vector_size(self) -> Optional[int]:
        return self._dim

    @property
    def provider_name(self) -> str:
        return "deterministic_demo"

    @property
    def model_name(self) -> str:
        return f"deterministic-demo-{self._dim}"

    def embed_text(self, text: str) -> List[float]:
        # LCG seeded from SHA-256 -> deterministic, finite, unit vector
        seed = int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], "little")
        floats: List[float] = []
        for _ in range(self._dim):
            seed = (seed * 6364136223846793005 + 1442695040888963407) & 0xFFFFFFFFFFFFFFFF
            floats.append((seed / 0xFFFFFFFFFFFFFFFF) * 2.0 - 1.0)
        magnitude = sum(x * x for x in floats) ** 0.5
        if magnitude > 0:
            return [x / magnitude for x in floats]
        return [1.0] + [0.0] * (self._dim - 1)


class MockEmbeddingService(DeterministicDemoEmbeddingService):
    """Backward-compatible import name for older tests and callers."""
