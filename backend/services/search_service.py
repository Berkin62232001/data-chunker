from utils.storage_paths import storage_path
import json
import math
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import List, Tuple

from core.config import settings
from models.chunk_models import Chunk
from models.search_models import SearchRequest, SearchResponse, SearchResultItem

_PREVIEW_CHARS = 300


def _tokenize(text: str) -> List[str]:
    """Normalize Unicode and Turkish casing while preserving accented words."""
    normalized = unicodedata.normalize("NFKC", text).casefold()
    normalized = normalized.replace("\u0307", "").replace("ı", "i")
    return [token for token in re.findall(r"[^\W_]+", normalized) if len(token) >= 2]


def _bm25_scores(query_terms: List[str], chunks: List[Chunk]) -> List[float]:
    """Score chunks against document-wide term frequencies, including headings."""
    if not chunks or not query_terms:
        return [0.0] * len(chunks)

    text_counts = [Counter(_tokenize(chunk.text)) for chunk in chunks]
    section_counts = [Counter(_tokenize(" ".join(chunk.section_path))) for chunk in chunks]
    lengths = [max(1, sum(counts.values())) for counts in text_counts]
    average_length = max(1.0, sum(lengths) / len(chunks))
    document_frequencies: Counter = Counter()
    for text, section in zip(text_counts, section_counts):
        terms = set(text)
        if settings.keyword_section_weight:
            terms.update(section)
        document_frequencies.update(terms)

    query_terms = sorted(set(query_terms))
    inverse_frequencies = {
        term: math.log1p(
            (len(chunks) - document_frequencies[term] + 0.5)
            / (document_frequencies[term] + 0.5)
        )
        for term in query_terms
    }
    scores: List[float] = []
    for text, section, length in zip(text_counts, section_counts, lengths):
        normalization = settings.keyword_bm25_k1 * (
            1 - settings.keyword_bm25_b
            + settings.keyword_bm25_b * length / average_length
        )
        score = 0.0
        for term in query_terms:
            frequency = text[term] + settings.keyword_section_weight * section[term]
            score += (
                inverse_frequencies[term] * frequency * (settings.keyword_bm25_k1 + 1)
                / (frequency + normalization)
            )
        scores.append(score)
    return scores


def _load_chunks(path: Path) -> List[Chunk]:
    chunks: List[Chunk] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                try:
                    chunks.append(Chunk(**json.loads(line)))
                except Exception:
                    pass  # skip malformed lines; integrity check handles them separately
    return chunks


def _make_result(chunk: Chunk, score: float, include_full_text: bool) -> SearchResultItem:
    return SearchResultItem(
        chunk_id=chunk.chunk_id,
        chunk_index=chunk.chunk_index,
        section_path=chunk.section_path,
        content_type=chunk.content_type,
        score=round(score, 6),
        estimated_tokens=chunk.estimated_tokens,
        text_preview=chunk.text[:_PREVIEW_CHARS],
        text=chunk.text if include_full_text else None,
    )


class SearchService:
    def search(self, document_id: str, request: SearchRequest) -> SearchResponse:
        jsonl_path = storage_path(settings.chunks_dir, document_id, "chunks.jsonl")
        chunks = _load_chunks(jsonl_path)

        query_terms = _tokenize(request.query)

        scores = _bm25_scores(query_terms, chunks)
        scored: List[Tuple[float, Chunk]] = list(zip(scores, chunks))

        # Sort: score descending, chunk_index ascending for ties
        scored.sort(key=lambda x: (-x[0], x[1].chunk_index))

        # Keep only positive-score results up to top_k
        positive = [(s, c) for s, c in scored if s > 0.0]
        top = positive[: request.top_k]

        results = [_make_result(c, s, request.include_full_text) for s, c in top]

        return SearchResponse(
            document_id=document_id,
            query=request.query,
            top_k=request.top_k,
            total_chunks_searched=len(chunks),
            results=results,
        )
