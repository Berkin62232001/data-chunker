from pathlib import Path

from core.config import settings
from db import repository
from db.session import get_session
from models.llm_gateway_models import AskRequest, AskResponse
from models.llm_payload_models import LLMPayloadRequest
from services import audit_log_service
from services.llm_gateway.base import LLMAdapter
from services.llm_gateway.claude_adapter import ClaudeAdapter
from services.llm_gateway.gemini_adapter import GeminiAdapter
from services.llm_gateway.mock_adapter import MockLLMAdapter
from services.llm_gateway.openai_adapter import OpenAIAdapter
from services.llm_payload_service import LLMPayloadService

_LOCAL_ONLY_MSG = (
    "[Local-only mode] External LLM calls are disabled. "
    "Set LOCAL_ONLY_MODE=false or use provider='mock'."
)

# Maps gateway provider names to the payload formatting style
_PAYLOAD_PROVIDER = {
    "mock":   "generic",
    "claude": "claude",
    "openai": "openai",
    "gemini": "gemini",
}


class LLMGateway:
    def __init__(self) -> None:
        self._payload_service = LLMPayloadService()
        self._adapters: dict[str, LLMAdapter] = {
            "mock":   MockLLMAdapter(),
            "claude": ClaudeAdapter(),
            "openai": OpenAIAdapter(),
            "gemini": GeminiAdapter(),
        }

    def ask(self, request: AskRequest) -> AskResponse:
        if settings.local_only_mode and request.provider != "mock":
            return AskResponse(
                answer=_LOCAL_ONLY_MSG,
                provider=request.provider,
                chunks_used=0,
                estimated_context_tokens=0,
                payload_id="",
            )

        payload_provider = _PAYLOAD_PROVIDER[request.provider]
        payload = self._payload_service.prepare(
            request.document_id,
            LLMPayloadRequest(
                query=request.query,
                top_k=request.top_k,
                provider=payload_provider,
                retrieval_mode=request.retrieval_mode,
            ),
        )

        adapter = self._adapters[request.provider]
        answer = adapter.ask(request.query, payload)
        payload_id = Path(payload.payload_path).stem

        audit_log_service.append(
            "llm_call",
            request.document_id,
            provider=request.provider,
            chunks_used=payload.chunks_used,
        )

        with get_session() as session:
            repository.create_llm_call(
                session,
                document_id=request.document_id,
                project_id=None,
                provider=request.provider,
                query=request.query,
                status="success",
                payload_id=payload_id,
            )

        return AskResponse(
            answer=answer,
            provider=request.provider,
            chunks_used=payload.chunks_used,
            estimated_context_tokens=payload.total_estimated_tokens,
            payload_id=payload_id,
        )

    def ask_with_payload(self, provider: str, query: str, payload) -> str:
        adapter = self._adapters[provider]
        return adapter.ask(query, payload)
