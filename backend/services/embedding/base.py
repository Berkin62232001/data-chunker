from abc import ABC, abstractmethod
from typing import List, Optional


class EmbeddingProviderError(RuntimeError):
    """Raised when an embedding provider cannot complete a request."""


class EmbeddingConfigurationError(EmbeddingProviderError):
    """Raised when embedding provider settings are invalid."""


class EmbeddingProviderUnavailableError(EmbeddingProviderError):
    """Raised when a configured embedding server cannot be reached."""


class EmbeddingServiceBase(ABC):
    @property
    def dim(self) -> int:
        """Dimensionality of the embedding vectors produced by this service."""
        if self.vector_size is None:
            raise EmbeddingProviderError("Embedding vector size is not known yet.")
        return self.vector_size

    @property
    @abstractmethod
    def provider_name(self) -> str:
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        ...

    @property
    @abstractmethod
    def vector_size(self) -> Optional[int]:
        """Dimensionality if known without making another provider call."""
        ...

    @abstractmethod
    def embed_text(self, text: str) -> List[float]:
        """Return a normalised embedding vector for the given text."""
        ...

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        return [self.embed_text(t) for t in texts]

    def embed(self, text: str) -> List[float]:
        return self.embed_text(text)

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return self.embed_texts(texts)
