from utils.storage_paths import storage_path
import json
from typing import Dict, List, Optional, Tuple

from core.config import settings
from models.chunk_models import Chunk
from models.evaluation_models import (
    RetrievedChunkSummary,
    RetrievalEvaluationRequest,
    RetrievalEvaluationResponse,
    RetrievalEvaluationSetRequest,
    RetrievalEvaluationSetResponse,
)
from models.hybrid_search_models import HybridSearchRequest
from models.search_models import SearchRequest
from models.vector_models import SemanticSearchRequest
from services.hybrid_search_service import HybridSearchService
from services.search_service import SearchService
from services.token_efficiency_service import TokenEfficiencyService
from services.vector_index_service import VectorIndexError, VectorIndexService

_LOW_SCORE_THRESHOLD = 0.1


def _load_chunks(document_id: str) -> List[Chunk]:
    path = storage_path(settings.chunks_dir, document_id, "chunks.jsonl")
    if not path.exists():
        return []

    chunks: List[Chunk] = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                chunks.append(Chunk(**json.loads(line)))
            except Exception:
                continue
    return chunks


def _round_optional(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return round(value, 6)


def _score_average(scores: List[float]) -> Optional[float]:
    if not scores:
        return None
    return round(sum(scores) / len(scores), 6)


def _percent(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 2)


class RetrievalEvaluationService:
    def __init__(
        self,
        keyword_service: Optional[SearchService] = None,
        vector_service: Optional[VectorIndexService] = None,
        hybrid_service: Optional[HybridSearchService] = None,
        token_service: Optional[TokenEfficiencyService] = None,
    ) -> None:
        self._keyword = keyword_service or SearchService()
        self._vector = vector_service or VectorIndexService()
        self._hybrid = hybrid_service or HybridSearchService(self._keyword, self._vector)
        self._token_service = token_service or TokenEfficiencyService()

    def evaluate(
        self,
        document_id: str,
        request: RetrievalEvaluationRequest,
    ) -> RetrievalEvaluationResponse:
        chunks = _load_chunks(document_id)
        chunk_by_id = {chunk.chunk_id: chunk for chunk in chunks}
        warnings: List[str] = []
        recommendations: List[str] = []

        if not chunks:
            warnings.append("Chunks are missing or empty. Run chunking before retrieval evaluation.")
            recommendations.append("Generate chunks, then re-run retrieval evaluation.")
            token_summary = self._token_service.summarize(document_id, selected_context_tokens=0)
            return self._build_response(
                document_id=document_id,
                request=request,
                total_chunks_searched=0,
                results=[],
                chunk_by_id=chunk_by_id,
                warnings=warnings,
                recommendations=recommendations,
                token_summary=token_summary,
            )

        results, retrieval_warnings, total_chunks_searched, keyword_only = self._run_retrieval(
            document_id, request, len(chunks)
        )
        warnings.extend(retrieval_warnings)

        if not results:
            warnings.append("Retrieval returned no chunks for this query.")
            recommendations.append("Try broader keywords or inspect whether the document was chunked correctly.")

        selected_tokens = sum(result.estimated_tokens for result in results)
        token_summary = self._token_service.summarize(
            document_id,
            selected_context_tokens=selected_tokens,
        )

        if selected_tokens > 4000:
            warnings.append("Selected context exceeds 4,000 estimated tokens.")
            recommendations.append("Reduce top_k or improve the query to target fewer chunks.")

        return self._build_response(
            document_id=document_id,
            request=request,
            total_chunks_searched=total_chunks_searched,
            results=results,
            chunk_by_id=chunk_by_id,
            warnings=warnings,
            recommendations=recommendations,
            token_summary=token_summary,
            keyword_only=keyword_only,
        )

    def evaluate_set(
        self,
        document_id: str,
        request: RetrievalEvaluationSetRequest,
    ) -> RetrievalEvaluationSetResponse:
        query_results: List[RetrievalEvaluationResponse] = []
        warnings: List[str] = []

        for query in request.queries:
            item_request = RetrievalEvaluationRequest(
                query=query.query,
                retrieval_mode=request.retrieval_mode,
                top_k=request.top_k,
                expected_terms=query.expected_terms,
                expected_section=query.expected_section,
            )
            result = self.evaluate(document_id, item_request)
            query_results.append(result)
            warnings.extend(result.warnings)

        total = len(query_results)
        avg_score = sum(result.retrieval_score_estimate for result in query_results) / total
        avg_context_tokens = sum(result.total_context_tokens for result in query_results) / total
        reduction_values = [
            result.token_efficiency_estimate.token_reduction_percent_vs_converted
            for result in query_results
            if result.token_efficiency_estimate.token_reduction_percent_vs_converted is not None
        ]
        avg_reduction = None
        if reduction_values:
            avg_reduction = round(sum(reduction_values) / len(reduction_values), 2)

        return RetrievalEvaluationSetResponse(
            document_id=document_id,
            retrieval_mode=request.retrieval_mode,
            top_k=request.top_k,
            total_queries=total,
            average_retrieval_score_estimate=round(avg_score, 2),
            average_context_tokens=round(avg_context_tokens, 2),
            average_token_reduction_percent_vs_converted=avg_reduction,
            queries=query_results,
            warnings=sorted(set(warnings)),
        )

    def _run_retrieval(
        self,
        document_id: str,
        request: RetrievalEvaluationRequest,
        fallback_total_chunks: int,
    ) -> Tuple[List[RetrievedChunkSummary], List[str], int, bool]:
        warnings: List[str] = []

        if request.retrieval_mode == "keyword":
            response = self._keyword.search(
                document_id,
                SearchRequest(query=request.query, top_k=request.top_k, include_full_text=False),
            )
            return (
                [
                    RetrievedChunkSummary(
                        chunk_id=result.chunk_id,
                        chunk_index=result.chunk_index,
                        section_path=result.section_path,
                        content_type=result.content_type,
                        score=result.score,
                        estimated_tokens=result.estimated_tokens,
                        text_preview=result.text_preview,
                    )
                    for result in response.results
                ],
                warnings,
                response.total_chunks_searched,
                True,
            )

        if request.retrieval_mode == "semantic":
            if not settings.qdrant_url:
                warnings.append("Semantic search is unavailable because Qdrant is not configured.")
                return [], warnings, fallback_total_chunks, False
            if not (storage_path(settings.chunks_dir, document_id, "index_manifest.json")).exists():
                warnings.append("Semantic index is missing. Index the document before semantic evaluation.")
                return [], warnings, fallback_total_chunks, False
            try:
                response = self._vector.semantic_search(
                    document_id,
                    SemanticSearchRequest(query=request.query, top_k=request.top_k),
                )
            except VectorIndexError:
                warnings.append("Semantic search failed. Check Qdrant and embedding provider configuration.")
                return [], warnings, fallback_total_chunks, False
            return (
                [
                    RetrievedChunkSummary(
                        chunk_id=result.chunk_id,
                        chunk_index=result.chunk_index,
                        section_path=result.section_path,
                        content_type=result.content_type,
                        score=result.score,
                        estimated_tokens=result.estimated_tokens,
                        text_preview=result.text_preview,
                    )
                    for result in response.results
                ],
                warnings,
                fallback_total_chunks,
                False,
            )

        response = self._hybrid.search(
            document_id,
            HybridSearchRequest(query=request.query, top_k=request.top_k),
        )
        if not response.semantic_available:
            warnings.append("Hybrid evaluation used keyword results only because semantic search is unavailable.")
        return (
            [
                RetrievedChunkSummary(
                    chunk_id=result.chunk_id,
                    chunk_index=result.chunk_index,
                    section_path=result.section_path,
                    content_type=result.content_type,
                    score=result.combined_score,
                    estimated_tokens=result.estimated_tokens,
                    text_preview=result.text_preview,
                )
                for result in response.results
            ],
            warnings,
            fallback_total_chunks,
            not response.semantic_available,
        )

    def _build_response(
        self,
        document_id: str,
        request: RetrievalEvaluationRequest,
        total_chunks_searched: int,
        results: List[RetrievedChunkSummary],
        chunk_by_id: Dict[str, Chunk],
        warnings: List[str],
        recommendations: List[str],
        token_summary,
        keyword_only: bool = False,
    ) -> RetrievalEvaluationResponse:
        scores = [result.score for result in results]
        low_score_results_count = 0
        if keyword_only and results:
            warnings.append(
                "Keyword BM25 scores are relative; absolute low-score thresholds are not applied."
            )
        else:
            low_score_results_count = sum(1 for score in scores if score < _LOW_SCORE_THRESHOLD)
        selected_texts = [
            self._selected_text(chunk_by_id[result.chunk_id])
            for result in results
            if result.chunk_id in chunk_by_id
        ]

        expected_found, expected_missing = self._evaluate_expected_terms(
            selected_texts,
            request.expected_terms,
        )
        expected_section_hit = self._evaluate_expected_section(results, request.expected_section)

        if expected_missing:
            warnings.append("Some expected terms were not found in retrieved chunks.")
            recommendations.append("Try hybrid or semantic retrieval, or adjust chunk boundaries around target sections.")
        if expected_section_hit is False:
            warnings.append("Expected section was not represented in retrieved chunks.")
            recommendations.append("Use a query that includes the expected section heading or re-index for semantic retrieval.")
        if low_score_results_count and len(results) == request.top_k:
            recommendations.append("Lower top_k if low-score chunks add unnecessary context.")

        retrieval_score_estimate = self._estimate_retrieval_score(
            returned_count=len(results),
            top_k=request.top_k,
            expected_terms_count=len(request.expected_terms),
            expected_terms_found_count=len(expected_found),
            expected_section=request.expected_section,
            expected_section_hit=expected_section_hit,
        )

        return RetrievalEvaluationResponse(
            document_id=document_id,
            query=request.query,
            retrieval_mode=request.retrieval_mode,
            top_k=request.top_k,
            total_chunks_searched=total_chunks_searched,
            returned_chunks_count=len(results),
            total_context_tokens=sum(result.estimated_tokens for result in results),
            average_result_score=_score_average(scores),
            top_score=_round_optional(max(scores) if scores else None),
            low_score_results_count=low_score_results_count,
            expected_terms_found=expected_found,
            expected_terms_missing=expected_missing,
            matched_expected_terms_count=len(expected_found),
            expected_section=request.expected_section,
            expected_section_hit=expected_section_hit,
            retrieval_score_estimate=retrieval_score_estimate,
            token_efficiency_estimate=token_summary,
            selected_results=results,
            warnings=sorted(set(warnings)),
            recommendations=sorted(set(recommendations)),
        )

    @staticmethod
    def _selected_text(chunk: Chunk) -> str:
        section_text = " ".join(chunk.section_path)
        return f"{section_text}\n{chunk.text}".lower()

    @staticmethod
    def _evaluate_expected_terms(
        selected_texts: List[str],
        expected_terms: List[str],
    ) -> Tuple[List[str], List[str]]:
        joined = "\n".join(selected_texts)
        found: List[str] = []
        missing: List[str] = []
        for term in expected_terms:
            if term.lower() in joined:
                found.append(term)
            else:
                missing.append(term)
        return found, missing

    @staticmethod
    def _evaluate_expected_section(
        results: List[RetrievedChunkSummary],
        expected_section: Optional[str],
    ) -> Optional[bool]:
        if expected_section is None:
            return None
        expected = expected_section.lower()
        for result in results:
            section_text = " ".join(result.section_path).lower()
            if expected in section_text:
                return True
        return False

    @staticmethod
    def _estimate_retrieval_score(
        returned_count: int,
        top_k: int,
        expected_terms_count: int,
        expected_terms_found_count: int,
        expected_section: Optional[str],
        expected_section_hit: Optional[bool],
    ) -> float:
        components: List[float] = []
        if expected_terms_count:
            components.append((expected_terms_found_count / expected_terms_count) * 100)
        if expected_section is not None:
            components.append(100.0 if expected_section_hit else 0.0)
        if not components:
            components.append((returned_count / max(1, top_k)) * 100)
        return _percent(sum(components) / len(components))
