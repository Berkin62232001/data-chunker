from utils.storage_paths import storage_path
from typing import Dict, List, Optional, Tuple

from core.config import settings
from models.hybrid_search_models import HybridResultItem, HybridSearchRequest, HybridSearchResponse
from models.search_models import SearchRequest
from models.vector_models import SemanticSearchRequest
from services.search_service import SearchService
from services.vector_index_service import VectorIndexService

# Retrieve more candidates than top_k so deduplication keeps the best ones
_OVER_RETRIEVE = 3
_MAX_RETRIEVE = 50

_PREVIEW_CHARS = 300


class HybridSearchService:
    def __init__(
        self,
        keyword_service: Optional[SearchService] = None,
        vector_service: Optional[VectorIndexService] = None,
    ) -> None:
        self._keyword = keyword_service or SearchService()
        self._vector = vector_service or VectorIndexService()

    def search(self, document_id: str, request: HybridSearchRequest) -> HybridSearchResponse:
        over_k = min(request.top_k * _OVER_RETRIEVE, _MAX_RETRIEVE)

        kw_raw = self._run_keyword(document_id, request.query, over_k)
        sem_raw, semantic_available = self._run_semantic(document_id, request.query, over_k)

        results = _merge(kw_raw, sem_raw, request.keyword_weight, request.semantic_weight)
        top = results[: request.top_k]

        return HybridSearchResponse(
            document_id=document_id,
            query=request.query,
            top_k=request.top_k,
            keyword_weight=request.keyword_weight,
            semantic_weight=request.semantic_weight,
            semantic_available=semantic_available,
            results=top,
        )

    # ── internal helpers ───────────────────────────────────────────────────────

    def _run_keyword(
        self, document_id: str, query: str, top_k: int
    ) -> List[Tuple[str, float, dict]]:
        """Return list of (chunk_id, raw_score, meta_dict)."""
        resp = self._keyword.search(
            document_id,
            SearchRequest(query=query, top_k=top_k, include_full_text=False),
        )
        return [
            (
                r.chunk_id,
                r.score,
                {
                    "chunk_index": r.chunk_index,
                    "section_path": r.section_path,
                    "content_type": r.content_type,
                    "estimated_tokens": r.estimated_tokens,
                    "text_preview": r.text_preview,
                },
            )
            for r in resp.results
        ]

    def _run_semantic(
        self, document_id: str, query: str, top_k: int
    ) -> Tuple[List[Tuple[str, float, dict]], bool]:
        """Return (results, available).  Silently returns ([], False) on any failure."""
        if not settings.qdrant_url:
            return [], False
        if not (storage_path(settings.chunks_dir, document_id, "index_manifest.json")).exists():
            return [], False
        try:
            resp = self._vector.semantic_search(
                document_id,
                SemanticSearchRequest(query=query, top_k=top_k),
            )
            rows = [
                (
                    r.chunk_id,
                    r.score,
                    {
                        "chunk_index": r.chunk_index,
                        "section_path": r.section_path,
                        "content_type": r.content_type,
                        "estimated_tokens": r.estimated_tokens,
                        "text_preview": r.text_preview,
                    },
                )
                for r in resp.results
            ]
            return rows, True
        except Exception:
            return [], False


# ── pure helpers (importable for unit tests) ──────────────────────────────────

def normalize_scores(scores: Dict[str, float]) -> Dict[str, float]:
    """Min-max normalise to [0, 1].  Single-item or flat distributions → 1.0."""
    if not scores:
        return {}
    lo, hi = min(scores.values()), max(scores.values())
    if hi == lo:
        return {k: 1.0 for k in scores}
    span = hi - lo
    return {k: (v - lo) / span for k, v in scores.items()}


def _merge(
    kw_raw: List[Tuple[str, float, dict]],
    sem_raw: List[Tuple[str, float, dict]],
    kw_weight: float,
    sem_weight: float,
) -> List[HybridResultItem]:
    kw_scores = {cid: score for cid, score, _ in kw_raw}
    sem_scores = {cid: score for cid, score, _ in sem_raw}

    kw_norm = normalize_scores(kw_scores)
    sem_norm = normalize_scores(sem_scores)

    # Metadata: prefer keyword entry (has text_preview from keyword search)
    meta: Dict[str, dict] = {}
    for cid, _, m in sem_raw:
        meta[cid] = m
    for cid, _, m in kw_raw:  # keyword overwrites; its text_preview is always set
        meta[cid] = m

    results: List[HybridResultItem] = []
    for cid in meta:
        kw = kw_norm.get(cid, 0.0)
        sem = sem_norm.get(cid, 0.0)
        combined = kw_weight * kw + sem_weight * sem
        m = meta[cid]
        results.append(
            HybridResultItem(
                chunk_id=cid,
                chunk_index=m["chunk_index"],
                section_path=m["section_path"],
                content_type=m["content_type"],
                combined_score=round(combined, 6),
                keyword_score=round(kw, 6),
                semantic_score=round(sem, 6),
                estimated_tokens=m["estimated_tokens"],
                text_preview=m["text_preview"],
            )
        )

    results.sort(key=lambda r: (-r.combined_score, r.chunk_index))
    return results
