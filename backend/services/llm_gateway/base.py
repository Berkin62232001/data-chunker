from abc import ABC, abstractmethod

from models.llm_payload_models import LLMPayloadResponse


class LLMAdapter(ABC):
    @abstractmethod
    def ask(self, query: str, payload: LLMPayloadResponse) -> str:
        """Return an answer string given a query and the prepared payload."""
        ...

    @property
    @abstractmethod
    def is_configured(self) -> bool:
        """True when this adapter has the credentials it needs to call the real API."""
        ...
