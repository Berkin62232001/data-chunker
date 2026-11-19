from core.config import settings
from models.llm_payload_models import LLMPayloadResponse
from services.llm_gateway.base import LLMAdapter

_NOT_CONFIGURED = (
    "[OpenAI] Provider not configured yet. "
    "Set OPENAI_API_KEY in your environment to enable real OpenAI responses."
)


class OpenAIAdapter(LLMAdapter):
    @property
    def is_configured(self) -> bool:
        return bool(settings.openai_api_key)

    def ask(self, query: str, payload: LLMPayloadResponse) -> str:
        # TODO Phase 10: call OpenAI Chat Completions API using payload.formatted_context
        return _NOT_CONFIGURED
