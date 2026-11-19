from core.config import settings
from models.llm_payload_models import LLMPayloadResponse
from services.llm_gateway.base import LLMAdapter

_NOT_CONFIGURED = (
    "[Gemini] Provider not configured yet. "
    "Set GEMINI_API_KEY in your environment to enable real Gemini responses."
)


class GeminiAdapter(LLMAdapter):
    @property
    def is_configured(self) -> bool:
        return bool(settings.gemini_api_key)

    def ask(self, query: str, payload: LLMPayloadResponse) -> str:
        # TODO Phase 10: call Google Gemini API using payload.formatted_context
        return _NOT_CONFIGURED
