from utils.storage_paths import storage_path
import json
import logging
from typing import Optional

from core.config import settings
from models.evaluation_models import TokenEfficiencySummary

logger = logging.getLogger(__name__)


def _read_json(path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to read JSON file %s: %s", path, exc)
        return None


def _reduction_percent(selected_tokens: Optional[int], source_tokens: Optional[int]) -> Optional[float]:
    if selected_tokens is None or source_tokens is None or source_tokens <= 0:
        return None
    return round((1 - (selected_tokens / source_tokens)) * 100, 2)


def _interpret(
    selected_context_tokens: Optional[int],
    converted_estimated_tokens: Optional[int],
    reduction_percent: Optional[float],
) -> str:
    if selected_context_tokens is None:
        return "Run retrieval evaluation to estimate selected-context token efficiency."
    if converted_estimated_tokens is None or converted_estimated_tokens <= 0:
        return "Converted token estimate is unavailable, so efficiency cannot be rated."
    if reduction_percent is None:
        return "Token reduction could not be calculated."
    if reduction_percent >= 90:
        return "Excellent reduction: retrieval uses only a small fraction of the converted document."
    if reduction_percent >= 70:
        return "Good reduction: retrieval materially lowers context size."
    if reduction_percent >= 40:
        return "Moderate reduction: retrieved context is smaller, but chunk targeting may be improved."
    return "Low reduction: retrieved context remains close to the converted document size."


class TokenEfficiencyService:
    def summarize(
        self,
        document_id: str,
        selected_context_tokens: Optional[int] = None,
    ) -> TokenEfficiencySummary:
        warnings = []

        raw_meta = _read_json(storage_path(settings.raw_uploads_dir, document_id, "metadata.json"))
        converted_meta = _read_json(storage_path(settings.converted_dir, document_id, "metadata.json"))
        chunk_manifest = _read_json(storage_path(settings.chunks_dir, document_id, "chunk_manifest.json"))

        original_estimated_tokens = None
        if raw_meta:
            size_bytes = raw_meta.get("size_bytes")
            if isinstance(size_bytes, int) and size_bytes > 0:
                original_estimated_tokens = max(1, size_bytes // 4)
            else:
                warnings.append("Original file size is missing; original token estimate unavailable.")
        else:
            warnings.append("Raw metadata is missing; original token estimate unavailable.")

        converted_estimated_tokens = None
        if converted_meta:
            value = converted_meta.get("estimated_token_count")
            if isinstance(value, int) and value >= 0:
                converted_estimated_tokens = value
            else:
                warnings.append("Converted metadata is missing an estimated_token_count value.")
        else:
            warnings.append("Converted metadata is missing; converted token estimate unavailable.")

        total_chunk_tokens = None
        if chunk_manifest:
            value = chunk_manifest.get("total_estimated_tokens")
            if isinstance(value, int) and value >= 0:
                total_chunk_tokens = value
            else:
                warnings.append("Chunk manifest is missing total_estimated_tokens.")
        else:
            warnings.append("Chunk manifest is missing; chunk token estimate unavailable.")

        if selected_context_tokens is None:
            warnings.append("Selected context tokens are unavailable until retrieval evaluation runs.")

        reduction_vs_original = _reduction_percent(selected_context_tokens, original_estimated_tokens)
        reduction_vs_converted = _reduction_percent(selected_context_tokens, converted_estimated_tokens)

        return TokenEfficiencySummary(
            document_id=document_id,
            original_estimated_tokens=original_estimated_tokens,
            converted_estimated_tokens=converted_estimated_tokens,
            total_chunk_tokens=total_chunk_tokens,
            selected_context_tokens=selected_context_tokens,
            token_reduction_percent_vs_original=reduction_vs_original,
            token_reduction_percent_vs_converted=reduction_vs_converted,
            interpretation=_interpret(
                selected_context_tokens,
                converted_estimated_tokens,
                reduction_vs_converted,
            ),
            warnings=warnings,
        )
