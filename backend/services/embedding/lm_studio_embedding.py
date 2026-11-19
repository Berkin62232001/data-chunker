from typing import List, Optional

import httpx

from services.embedding.base import (
    EmbeddingProviderError,
    EmbeddingProviderUnavailableError,
    EmbeddingServiceBase,
)


LM_STUDIO_UNAVAILABLE_MESSAGE = (
    "LM Studio embedding server is unavailable. Start LM Studio local server "
    "or switch EMBEDDING_PROVIDER to deterministic_demo."
)
LM_STUDIO_NO_MODEL_LOADED_MESSAGE = (
    "LM Studio has no embedding model loaded. Load an embeddings-capable model "
    "in LM Studio, then set LM_STUDIO_EMBEDDING_MODEL to that model."
)
LM_STUDIO_MODEL_UNAVAILABLE_TEMPLATE = (
    "LM Studio embedding model '{model}' is unavailable. Load that model in "
    "LM Studio or update LM_STUDIO_EMBEDDING_MODEL."
)
LM_STUDIO_MODEL_NOT_EMBEDDING_CAPABLE_TEMPLATE = (
    "LM Studio model '{model}' did not return embeddings. Load an "
    "embeddings-capable model and set LM_STUDIO_EMBEDDING_MODEL to it."
)


class LMStudioEmbeddingService(EmbeddingServiceBase):
    """OpenAI-compatible embedding provider for LM Studio's local server."""

    def __init__(
        self,
        base_url: str,
        model_name: str,
        api_key: str = "",
        timeout_seconds: int = 30,
        batch_size: int = 16,
        http_client: Optional[httpx.Client] = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model_name = model_name
        self._api_key = api_key
        self._batch_size = max(1, batch_size)
        self._vector_size: Optional[int] = None
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(timeout=timeout_seconds)

    @property
    def provider_name(self) -> str:
        return "lm_studio"

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def vector_size(self) -> Optional[int]:
        return self._vector_size

    @property
    def base_url(self) -> str:
        return self._base_url

    def embed_text(self, text: str) -> List[float]:
        return self.embed_texts([text])[0]

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []

        vectors: List[List[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start:start + self._batch_size]
            vectors.extend(self._embed_batch(batch))
        return vectors

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _embed_batch(self, texts: List[str]) -> List[List[float]]:
        payload = {"model": self._model_name, "input": texts}
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            response = self._client.post(
                f"{self._base_url}/embeddings",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.TimeoutException):
            raise EmbeddingProviderUnavailableError(LM_STUDIO_UNAVAILABLE_MESSAGE) from None
        except httpx.RequestError as exc:
            raise EmbeddingProviderUnavailableError(LM_STUDIO_UNAVAILABLE_MESSAGE) from exc
        except httpx.HTTPStatusError as exc:
            raise EmbeddingProviderError(self._message_for_error_response(exc.response)) from exc

        try:
            body = response.json()
        except ValueError as exc:
            raise EmbeddingProviderError("LM Studio embedding response was not valid JSON.") from exc

        return self._parse_embeddings(body, expected_count=len(texts))

    def _parse_embeddings(self, body: object, expected_count: int) -> List[List[float]]:
        if not isinstance(body, dict):
            raise EmbeddingProviderError("LM Studio embedding response had an unexpected shape.")

        error_text = _extract_error_text(body)
        if error_text:
            raise EmbeddingProviderError(self._message_for_error_text(error_text))

        data = body.get("data")
        if not isinstance(data, list) or len(data) != expected_count:
            raise EmbeddingProviderError(self._model_not_embedding_capable_message())

        vectors: List[List[float]] = []
        for item in data:
            if not isinstance(item, dict):
                raise EmbeddingProviderError("LM Studio embedding response had an unexpected item.")
            embedding = item.get("embedding")
            if not isinstance(embedding, list) or not embedding:
                raise EmbeddingProviderError(self._model_not_embedding_capable_message())
            try:
                vector = [float(value) for value in embedding]
            except (TypeError, ValueError) as exc:
                raise EmbeddingProviderError("LM Studio embedding response contained non-numeric values.") from exc

            if self._vector_size is None:
                self._vector_size = len(vector)
            elif len(vector) != self._vector_size:
                raise EmbeddingProviderError("LM Studio embedding response vector size changed between calls.")
            vectors.append(vector)

        return vectors

    def _message_for_error_response(self, response: httpx.Response) -> str:
        error_text = ""
        try:
            body = response.json()
        except ValueError:
            body = None
        if isinstance(body, dict):
            error_text = _extract_error_text(body)
        if not error_text:
            error_text = response.text
        message = self._message_for_error_text(error_text)
        if message:
            return message
        return f"LM Studio embedding request failed with status {response.status_code}."

    def _message_for_error_text(self, error_text: str) -> str:
        text = error_text.lower()
        if "no models loaded" in text:
            return LM_STUDIO_NO_MODEL_LOADED_MESSAGE
        if "not found" in text or "not loaded" in text or "model not found" in text:
            return LM_STUDIO_MODEL_UNAVAILABLE_TEMPLATE.format(model=self._model_name)
        if (
            "embedding" in text
            and (
                "not support" in text
                or "unsupported" in text
                or "not capable" in text
                or "not available" in text
            )
        ):
            return self._model_not_embedding_capable_message()
        return ""

    def _model_not_embedding_capable_message(self) -> str:
        return LM_STUDIO_MODEL_NOT_EMBEDDING_CAPABLE_TEMPLATE.format(model=self._model_name)


def _extract_error_text(body: dict) -> str:
    error = body.get("error")
    if isinstance(error, str):
        return error
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, str):
            return message
    message = body.get("message")
    if isinstance(message, str):
        return message
    return ""
