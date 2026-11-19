from utils.storage_paths import storage_path
import json
import re
from typing import Any, Dict, List

from core.config import settings
from models.evaluation_models import ChunkQualityReport

_UNDERSIZED_TOKEN_THRESHOLD = 80
_OVERSIZED_TOKEN_THRESHOLD = 900
_REQUIRED_METADATA_FIELDS = {
    "chunk_id",
    "chunk_index",
    "section_path",
    "content_type",
    "estimated_tokens",
}


def _load_json(path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _load_chunk_rows(document_id: str) -> tuple[List[Dict[str, Any]], int]:
    path = storage_path(settings.chunks_dir, document_id, "chunks.jsonl")
    if not path.exists():
        return [], 0

    rows: List[Dict[str, Any]] = []
    malformed_count = 0
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except Exception:
                malformed_count += 1
                continue
            if isinstance(payload, dict):
                rows.append(payload)
            else:
                malformed_count += 1
    return rows, malformed_count


def _normalized_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", value.lower()).strip()


def _read_ocr_used(document_id: str) -> bool:
    report = _load_json(storage_path(settings.converted_dir, document_id, "extraction_report.json"))
    return bool(report and report.get("ocr_used"))


def _score_quality(
    total_chunks: int,
    empty_chunks_count: int,
    missing_text_count: int,
    missing_metadata_count: int,
    oversized_chunks_count: int,
    undersized_chunks_count: int,
    duplicate_text_chunks_count: int,
    section_path_coverage_percent: float,
) -> float:
    if total_chunks == 0:
        return 0.0

    score = 100.0
    score -= min(40.0, (empty_chunks_count / total_chunks) * 100)
    score -= min(30.0, (missing_text_count / total_chunks) * 80)
    score -= min(30.0, (missing_metadata_count / total_chunks) * 60)
    score -= min(20.0, (oversized_chunks_count / total_chunks) * 45)
    score -= min(20.0, (undersized_chunks_count / total_chunks) * 25)
    score -= min(20.0, (duplicate_text_chunks_count / total_chunks) * 40)
    score -= max(0.0, (100.0 - section_path_coverage_percent) * 0.1)
    return round(max(0.0, min(100.0, score)), 2)


class ChunkQualityService:
    def evaluate(self, document_id: str) -> ChunkQualityReport:
        rows, malformed_count = _load_chunk_rows(document_id)
        warnings: List[str] = []
        recommendations: List[str] = []

        if not rows:
            if malformed_count:
                warnings.append("Chunk file contains malformed rows and no valid chunk rows.")
            else:
                warnings.append("Chunks are missing. Run chunking before evaluating chunk quality.")
            recommendations.append("Generate chunks, then re-run chunk quality evaluation.")
            return ChunkQualityReport(
                document_id=document_id,
                total_chunks=0,
                total_estimated_tokens=0,
                average_chunk_tokens=0,
                min_chunk_tokens=0,
                max_chunk_tokens=0,
                empty_chunks_count=0,
                missing_text_count=0,
                missing_metadata_count=0,
                oversized_chunks_count=0,
                undersized_chunks_count=0,
                duplicate_text_chunks_count=0,
                section_path_coverage_percent=0.0,
                table_chunks_count=0,
                ocr_chunks_count=0,
                quality_score=0.0,
                warnings=warnings,
                recommendations=recommendations,
            )

        token_values: List[int] = []
        missing_text_count = 0
        empty_chunks_count = 0
        missing_metadata_count = 0
        oversized_chunks_count = 0
        undersized_chunks_count = 0
        table_chunks_count = 0
        section_path_count = 0
        text_counts: Dict[str, int] = {}

        for row in rows:
            text = row.get("text")
            if not isinstance(text, str):
                missing_text_count += 1
                text = ""
            if not text.strip():
                empty_chunks_count += 1

            if any(field not in row for field in _REQUIRED_METADATA_FIELDS):
                missing_metadata_count += 1

            estimated_tokens = row.get("estimated_tokens")
            if isinstance(estimated_tokens, int) and estimated_tokens >= 0:
                token_values.append(estimated_tokens)
                if estimated_tokens > _OVERSIZED_TOKEN_THRESHOLD:
                    oversized_chunks_count += 1
                if estimated_tokens < _UNDERSIZED_TOKEN_THRESHOLD:
                    undersized_chunks_count += 1
            else:
                missing_metadata_count += 1

            if row.get("content_type") == "table":
                table_chunks_count += 1

            section_path = row.get("section_path")
            if isinstance(section_path, list) and any(str(part).strip() for part in section_path):
                section_path_count += 1

            normalized = _normalized_text(text)
            if len(normalized) > 20:
                text_counts[normalized] = text_counts.get(normalized, 0) + 1

        duplicate_text_chunks_count = sum(count - 1 for count in text_counts.values() if count > 1)
        total_chunks = len(rows)
        total_estimated_tokens = sum(token_values)
        average_chunk_tokens = total_estimated_tokens // total_chunks if total_chunks else 0
        min_chunk_tokens = min(token_values) if token_values else 0
        max_chunk_tokens = max(token_values) if token_values else 0
        section_path_coverage_percent = round((section_path_count / total_chunks) * 100, 2)
        ocr_chunks_count = total_chunks if _read_ocr_used(document_id) else 0

        if malformed_count:
            warnings.append(f"{malformed_count} malformed chunk row(s) were skipped.")
        if empty_chunks_count:
            warnings.append(f"{empty_chunks_count} empty chunk(s) detected.")
        if missing_text_count:
            warnings.append(f"{missing_text_count} chunk(s) are missing valid text.")
        if missing_metadata_count:
            warnings.append(f"{missing_metadata_count} chunk(s) are missing expected metadata.")
        if oversized_chunks_count:
            warnings.append(
                f"{oversized_chunks_count} chunk(s) exceed {_OVERSIZED_TOKEN_THRESHOLD} estimated tokens."
            )
            recommendations.append("Review conversion or chunk boundaries for oversized chunks.")
        if undersized_chunks_count:
            warnings.append(
                f"{undersized_chunks_count} chunk(s) are below {_UNDERSIZED_TOKEN_THRESHOLD} estimated tokens."
            )
            recommendations.append("Consider merging very small adjacent chunks when recall is noisy.")
        if duplicate_text_chunks_count:
            warnings.append(f"{duplicate_text_chunks_count} duplicate text chunk(s) detected.")
            recommendations.append("Inspect conversion output for repeated headers, footers, or OCR duplication.")
        if section_path_coverage_percent < 70:
            warnings.append("Most chunks lack section path metadata.")
            recommendations.append("Use heading-aware source structure when available.")
        if average_chunk_tokens and max_chunk_tokens > average_chunk_tokens * 3:
            warnings.append("Chunk token distribution is uneven.")
            recommendations.append("Review long sections that may need deeper splitting.")

        if not recommendations:
            recommendations.append("Chunk structure looks usable for retrieval.")

        quality_score = _score_quality(
            total_chunks,
            empty_chunks_count,
            missing_text_count,
            missing_metadata_count,
            oversized_chunks_count,
            undersized_chunks_count,
            duplicate_text_chunks_count,
            section_path_coverage_percent,
        )

        return ChunkQualityReport(
            document_id=document_id,
            total_chunks=total_chunks,
            total_estimated_tokens=total_estimated_tokens,
            average_chunk_tokens=average_chunk_tokens,
            min_chunk_tokens=min_chunk_tokens,
            max_chunk_tokens=max_chunk_tokens,
            empty_chunks_count=empty_chunks_count,
            missing_text_count=missing_text_count,
            missing_metadata_count=missing_metadata_count,
            oversized_chunks_count=oversized_chunks_count,
            undersized_chunks_count=undersized_chunks_count,
            duplicate_text_chunks_count=duplicate_text_chunks_count,
            section_path_coverage_percent=section_path_coverage_percent,
            table_chunks_count=table_chunks_count,
            ocr_chunks_count=ocr_chunks_count,
            quality_score=quality_score,
            warnings=warnings,
            recommendations=recommendations,
        )
