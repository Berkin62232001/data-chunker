from utils.storage_paths import storage_path
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from core.config import settings
from models.chunk_models import Chunk
from models.vector_models import (
    IndexManifest,
    IndexResponse,
    SemanticSearchRequest,
    SemanticSearchResponse,
    SemanticSearchResultItem,
)
from services.embedding.base import EmbeddingServiceBase
from services.embedding.base import EmbeddingProviderError
from services.embedding.factory import get_configured_embedding_service

_PREVIEW_CHARS = 300
_DIMENSION_MISMATCH_MESSAGE = (
    "Qdrant collection vector size does not match current embedding provider. "
    "Reset/recreate Qdrant collection or use a different collection name."
)
_PROVIDER_MISMATCH_MESSAGE = (
    "Qdrant collection embedding provider/model does not match current embedding provider. "
    "Reset/recreate Qdrant collection or use a different collection name."
)


class VectorIndexError(RuntimeError):
    """Raised when Qdrant indexing/search cannot complete cleanly."""


class VectorIndexService:
    def __init__(self, embedding_service: Optional[EmbeddingServiceBase] = None) -> None:
        self._embedding = embedding_service

    # ── public API ─────────────────────────────────────────────────────────────

    def index(self, document_id: str) -> IndexResponse:
        chunks = _load_chunks(storage_path(settings.chunks_dir, document_id, "chunks.jsonl"))
        embedding = self._embedding_service()

        try:
            vectors = embedding.embed_texts([chunk.text for chunk in chunks])
            vector_size = _resolve_vector_size(embedding, vectors)
            client = _client()
            if vector_size is not None:
                _ensure_collection_embedding_compatible(
                    settings.qdrant_collection,
                    embedding.provider_name,
                    embedding.model_name,
                    vector_size,
                )
                _ensure_collection(client, settings.qdrant_collection, vector_size)

            points = [
                PointStruct(
                    id=str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk.chunk_id)),
                    vector=vector,
                    payload={
                        "document_id": document_id,
                        "chunk_id": chunk.chunk_id,
                        "chunk_index": chunk.chunk_index,
                        "section_path": chunk.section_path,
                        "content_type": chunk.content_type,
                        "estimated_tokens": chunk.estimated_tokens,
                        "text_preview": _preview(chunk.text),
                        "embedding_provider": embedding.provider_name,
                        "embedding_model": embedding.model_name,
                    },
                )
                for chunk, vector in zip(chunks, vectors)
            ]

            if points:
                client.upsert(collection_name=settings.qdrant_collection, points=points)
        except EmbeddingProviderError as exc:
            raise VectorIndexError(str(exc)) from exc
        except VectorIndexError:
            raise
        except Exception as exc:
            raise VectorIndexError(f"Qdrant is unavailable or indexing failed: {exc}") from exc

        manifest = IndexManifest(
            document_id=document_id,
            collection=settings.qdrant_collection,
            indexed_chunks=len(points),
            embedding_dim=vector_size or 0,
            embedding_provider=embedding.provider_name,
            embedding_model=embedding.model_name,
            indexed_at=datetime.now(timezone.utc).isoformat(),
            qdrant_url=settings.qdrant_url,
        )
        manifest_path = storage_path(settings.chunks_dir, document_id, "index_manifest.json")
        manifest_path.write_text(json.dumps(manifest.model_dump(), indent=2), encoding="utf-8")
        if vector_size is not None:
            _write_collection_manifest(
                settings.qdrant_collection,
                embedding.provider_name,
                embedding.model_name,
                vector_size,
            )

        return IndexResponse(
            document_id=document_id,
            qdrant_configured=bool(settings.qdrant_url),
            qdrant_available=True,
            collection_name=settings.qdrant_collection,
            indexed_chunks=len(points),
            collection=settings.qdrant_collection,
            vector_size=vector_size,
            embedding_provider=embedding.provider_name,
            embedding_model=embedding.model_name,
            status="indexed",
            qdrant_url_configured=bool(settings.qdrant_url),
            manifest_path=None,
        )

    def semantic_search(
        self, document_id: str, request: SemanticSearchRequest
    ) -> SemanticSearchResponse:
        embedding = self._embedding_service()

        try:
            query_vector = embedding.embed_text(request.query)
            _ensure_document_index_matches_provider(document_id, embedding, len(query_vector))
            client = _client()
            _ensure_existing_collection_vector_size(client, settings.qdrant_collection, len(query_vector))
            hits = client.search(
                collection_name=settings.qdrant_collection,
                query_vector=query_vector,
                query_filter=Filter(
                    must=[FieldCondition(key="document_id", match=MatchValue(value=document_id))]
                ),
                limit=request.top_k,
                with_payload=True,
            )
        except EmbeddingProviderError as exc:
            raise VectorIndexError(str(exc)) from exc
        except VectorIndexError:
            raise
        except Exception as exc:
            raise VectorIndexError(f"Qdrant is unavailable or semantic search failed: {exc}") from exc

        results = [
            SemanticSearchResultItem(
                chunk_id=hit.payload["chunk_id"],
                chunk_index=hit.payload["chunk_index"],
                section_path=hit.payload["section_path"],
                content_type=hit.payload["content_type"],
                score=round(hit.score, 6),
                estimated_tokens=hit.payload["estimated_tokens"],
                text_preview=_payload_preview(hit.payload),
            )
            for hit in hits
        ]

        return SemanticSearchResponse(
            document_id=document_id,
            query=request.query,
            top_k=request.top_k,
            results=results,
        )

    def embedding_status(self) -> dict:
        try:
            embedding = self._embedding_service()
            status = {
                "embedding_provider": embedding.provider_name,
                "embedding_model": embedding.model_name,
                "vector_size": embedding.vector_size,
                "lm_studio_base_url": getattr(embedding, "base_url", None)
                if embedding.provider_name == "lm_studio"
                else None,
                "error": None,
            }
        except EmbeddingProviderError as exc:
            status = {
                "embedding_provider": settings.embedding_provider,
                "embedding_model": None,
                "vector_size": None,
                "lm_studio_base_url": settings.lm_studio_base_url
                if settings.embedding_provider.strip().lower() == "lm_studio"
                else None,
                "error": str(exc),
            }
        return status

    def _embedding_service(self) -> EmbeddingServiceBase:
        return self._embedding or get_configured_embedding_service()


# ── helpers ────────────────────────────────────────────────────────────────────

def _client() -> QdrantClient:
    if not settings.qdrant_url:
        raise VectorIndexError("Qdrant is not configured. Set QDRANT_URL in your environment.")
    return QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key or None,
        timeout=30,
    )


def _ensure_collection(client: QdrantClient, name: str, dim: int) -> None:
    existing = {c.name for c in client.get_collections().collections}
    if name not in existing:
        client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )
        return
    _ensure_existing_collection_vector_size(client, name, dim)


def _ensure_existing_collection_vector_size(client: QdrantClient, name: str, dim: int) -> None:
    try:
        collection = client.get_collection(collection_name=name)
    except AttributeError:
        return
    existing_dim = _extract_collection_vector_size(collection)
    if existing_dim is not None and existing_dim != dim:
        raise VectorIndexError(_DIMENSION_MISMATCH_MESSAGE)


def _extract_collection_vector_size(collection: Any) -> Optional[int]:
    config = getattr(collection, "config", None)
    params = getattr(config, "params", None)
    vectors = getattr(params, "vectors", None)
    if isinstance(vectors, dict):
        for vector_params in vectors.values():
            size = _int_or_none(getattr(vector_params, "size", None))
            if size is not None:
                return size
        return None
    size = _int_or_none(getattr(vectors, "size", None))
    if size is not None:
        return size
    return None


def _int_or_none(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _resolve_vector_size(
    embedding: EmbeddingServiceBase, vectors: List[List[float]]
) -> Optional[int]:
    if embedding.vector_size is not None:
        return embedding.vector_size
    if not vectors:
        return None
    size = len(vectors[0])
    if any(len(vector) != size for vector in vectors):
        raise VectorIndexError("Embedding provider returned inconsistent vector sizes.")
    return size


def _load_chunks(path: Path) -> List[Chunk]:
    chunks: List[Chunk] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                try:
                    chunks.append(Chunk(**json.loads(line)))
                except Exception:
                    pass
    return chunks


def _preview(text: str) -> str:
    return text[:_PREVIEW_CHARS]


def _payload_preview(payload: dict) -> str:
    preview = payload.get("text_preview")
    if isinstance(preview, str):
        return preview[:_PREVIEW_CHARS]
    text = payload.get("text")
    if isinstance(text, str):
        return text[:_PREVIEW_CHARS]
    return ""


def _ensure_collection_embedding_compatible(
    collection: str,
    provider: str,
    model: str,
    vector_size: int,
) -> None:
    manifests = [_read_collection_manifest(collection)]
    manifests.extend(_iter_document_index_manifests(collection))

    for manifest in manifests:
        if not manifest:
            continue
        existing_provider = _normalise_provider(manifest.get("embedding_provider"))
        current_provider = _normalise_provider(provider)
        existing_model = _normalise_model(
            manifest.get("embedding_model"),
            existing_provider,
            manifest.get("embedding_dim") or manifest.get("vector_size"),
        )
        current_model = _normalise_model(model, current_provider, vector_size)
        existing_dim = manifest.get("embedding_dim") or manifest.get("vector_size")

        if existing_dim is not None and existing_dim != vector_size:
            raise VectorIndexError(_DIMENSION_MISMATCH_MESSAGE)
        if existing_provider and existing_provider != current_provider:
            raise VectorIndexError(_PROVIDER_MISMATCH_MESSAGE)
        if existing_model and existing_model != current_model:
            raise VectorIndexError(_PROVIDER_MISMATCH_MESSAGE)


def _ensure_document_index_matches_provider(
    document_id: str,
    embedding: EmbeddingServiceBase,
    query_vector_size: int,
) -> None:
    manifest_path = storage_path(settings.chunks_dir, document_id, "index_manifest.json")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return

    manifest_dim = manifest.get("embedding_dim") or manifest.get("vector_size")
    if manifest_dim is not None and manifest_dim != query_vector_size:
        raise VectorIndexError(_DIMENSION_MISMATCH_MESSAGE)

    manifest_provider = _normalise_provider(manifest.get("embedding_provider"))
    current_provider = _normalise_provider(embedding.provider_name)
    manifest_model = _normalise_model(manifest.get("embedding_model"), manifest_provider, manifest_dim)
    current_model = _normalise_model(embedding.model_name, current_provider, query_vector_size)

    if manifest_provider and manifest_provider != current_provider:
        raise VectorIndexError(
            "Document index embedding provider/model does not match current embedding provider. "
            "Re-index this document or switch EMBEDDING_PROVIDER back to the indexed provider."
        )
    if manifest_model and manifest_model != current_model:
        raise VectorIndexError(
            "Document index embedding provider/model does not match current embedding provider. "
            "Re-index this document or switch EMBEDDING_PROVIDER back to the indexed provider."
        )


def _collection_manifest_path(collection: str) -> Path:
    safe = "".join(c if c.isalnum() or c in ("-", "_", ".") else "_" for c in collection)
    return settings.chunks_dir / "_vector_collections" / f"{safe}.json"


def _read_collection_manifest(collection: str) -> Optional[dict]:
    path = _collection_manifest_path(collection)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _write_collection_manifest(
    collection: str,
    provider: str,
    model: str,
    vector_size: int,
) -> None:
    path = _collection_manifest_path(collection)
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "collection": collection,
        "embedding_provider": provider,
        "embedding_model": model,
        "vector_size": vector_size,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _iter_document_index_manifests(collection: str) -> List[dict]:
    manifests: List[dict] = []
    if not settings.chunks_dir.exists():
        return manifests
    for manifest_path in settings.chunks_dir.glob("*/index_manifest.json"):
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(data, dict) and data.get("collection") == collection:
            manifests.append(data)
    return manifests


def _normalise_provider(provider: Any) -> Optional[str]:
    if not isinstance(provider, str) or not provider:
        return None
    provider = provider.strip().lower()
    if provider == "mock":
        return "deterministic_demo"
    return provider


def _normalise_model(model: Any, provider: Optional[str], vector_size: Any) -> Optional[str]:
    if isinstance(model, str) and model:
        return model
    if provider == "deterministic_demo" and vector_size:
        return f"deterministic-demo-{vector_size}"
    return None


# ── status helpers ─────────────────────────────────────────────────────────────

def check_qdrant_status() -> dict:
    """Return {configured, available, collection_name, error} without crashing."""
    embedding_status = VectorIndexService().embedding_status()
    result = {
        "qdrant_configured": bool(settings.qdrant_url),
        "qdrant_available": False,
        "collection_name": settings.qdrant_collection,
        "embedding_provider": embedding_status["embedding_provider"],
        "embedding_model": embedding_status["embedding_model"],
        "vector_size": embedding_status["vector_size"],
        "lm_studio_base_url": embedding_status["lm_studio_base_url"],
        "error": embedding_status["error"],
    }
    if not settings.qdrant_url:
        result["error"] = _join_errors(result["error"], "QDRANT_URL is not set.")
        return result
    try:
        client = _client()
        client.get_collections()
        result["qdrant_available"] = True
    except VectorIndexError as exc:
        result["error"] = _join_errors(result["error"], str(exc))
    except Exception as exc:
        result["error"] = _join_errors(result["error"], f"Qdrant connection failed: {exc}")
    return result


def check_document_index_status(document_id: str) -> dict:
    """Return {indexed, indexed_chunks, total_chunks} without crashing."""
    result: dict = {
        "indexed": False,
        "indexed_chunks": 0,
        "total_chunks": None,
        "indexed_embedding_provider": None,
        "indexed_embedding_model": None,
        "indexed_vector_size": None,
    }

    # Check chunk manifest for total chunks
    chunk_manifest_path = storage_path(settings.chunks_dir, document_id, "chunk_manifest.json")
    if chunk_manifest_path.exists():
        try:
            manifest = json.loads(chunk_manifest_path.read_text(encoding="utf-8"))
            result["total_chunks"] = manifest.get("total_chunks")
        except Exception:
            pass

    # Check index manifest for indexed state
    index_manifest_path = storage_path(settings.chunks_dir, document_id, "index_manifest.json")
    if index_manifest_path.exists():
        try:
            manifest = json.loads(index_manifest_path.read_text(encoding="utf-8"))
            result["indexed"] = True
            result["indexed_chunks"] = manifest.get("indexed_chunks", 0)
            result["indexed_embedding_provider"] = manifest.get("embedding_provider")
            result["indexed_embedding_model"] = manifest.get("embedding_model")
            result["indexed_vector_size"] = manifest.get("embedding_dim")
        except Exception:
            pass

    return result


def _join_errors(first: Optional[str], second: str) -> str:
    if first:
        return f"{first} {second}"
    return second
