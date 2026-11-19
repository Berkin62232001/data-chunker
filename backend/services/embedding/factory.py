from typing import Optional, Tuple
from urllib.parse import urlsplit

from core.config import settings
from services.embedding.base import EmbeddingConfigurationError, EmbeddingServiceBase
from services.embedding.lm_studio_embedding import LMStudioEmbeddingService
from services.embedding.mock_embedding import DeterministicDemoEmbeddingService

_SUPPORTED_PROVIDERS = ("deterministic_demo", "lm_studio")
_cached_key: Optional[Tuple[object, ...]] = None
_cached_service: Optional[EmbeddingServiceBase] = None


def create_embedding_service() -> EmbeddingServiceBase:
    provider = settings.embedding_provider.strip().lower()
    if provider == "deterministic_demo":
        return DeterministicDemoEmbeddingService()
    if provider == "lm_studio":
        url = urlsplit(settings.lm_studio_base_url)
        if settings.local_only_mode and (
            url.scheme not in ("http", "https")
            or url.hostname not in settings.local_embedding_hosts
            or url.username is not None
            or url.password is not None
        ):
            raise EmbeddingConfigurationError("Local-only mode requires an approved local embedding host.")
        return LMStudioEmbeddingService(
            base_url=settings.lm_studio_base_url,
            model_name=settings.lm_studio_embedding_model,
            api_key=settings.lm_studio_api_key,
            timeout_seconds=settings.lm_studio_timeout_seconds,
            batch_size=settings.lm_studio_batch_size,
        )
    raise EmbeddingConfigurationError(
        f"Unsupported EMBEDDING_PROVIDER '{settings.embedding_provider}'. "
        f"Supported providers: {', '.join(_SUPPORTED_PROVIDERS)}."
    )


def get_configured_embedding_service() -> EmbeddingServiceBase:
    global _cached_key, _cached_service
    key = _settings_key()
    if _cached_service is None or _cached_key != key:
        _cached_service = create_embedding_service()
        _cached_key = key
    return _cached_service


def reset_embedding_service_cache() -> None:
    global _cached_key, _cached_service
    close = getattr(_cached_service, "close", None)
    if callable(close):
        close()
    _cached_key = None
    _cached_service = None


def _settings_key() -> Tuple[object, ...]:
    provider = settings.embedding_provider.strip().lower()
    if provider == "lm_studio":
        return (
            provider,
            settings.lm_studio_base_url,
            settings.lm_studio_embedding_model,
            settings.lm_studio_api_key,
            settings.lm_studio_timeout_seconds,
            settings.lm_studio_batch_size,
            settings.local_only_mode,
            tuple(settings.local_embedding_hosts),
        )
    return (provider,)
