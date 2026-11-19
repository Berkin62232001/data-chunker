from utils.storage_paths import storage_path
import json
from datetime import datetime, timezone
from typing import List, Tuple

from core.config import settings
from db import repository
from db.session import get_session
from models.pipeline_models import PipelineDecision
from models.profile_models import DocumentProfile

# PDFs with more than this many pages are routed to the heavier Docling pipeline.
_MANY_PAGES_THRESHOLD = 50

_OUTPUT_FORMAT = {
    "ocr_pdf_to_markdown_jsonl":              "markdown_jsonl",
    "standard_pdf_to_markdown_jsonl":         "markdown_jsonl",
    "advanced_pdf_docling_to_markdown_jsonl": "markdown_jsonl",
    "docx_to_markdown_jsonl":                 "markdown_jsonl",
    "pptx_to_slide_markdown_jsonl":           "markdown_jsonl",
    "tabular_to_structured_json_summary":     "structured_json_summary",
    "text_to_markdown_jsonl":                 "markdown_jsonl",
    "html_to_clean_markdown_jsonl":           "markdown_jsonl",
    "image_ocr_to_markdown_jsonl":            "markdown_jsonl",
    "fallback_text_extraction":               "markdown_jsonl",
}

_DEFAULT_ARTIFACTS = [
    "document.md",
    "chunks.jsonl",
    "metadata.json",
    "extraction_report.json",
]


def _select_pipeline(profile: DocumentProfile) -> Tuple[str, List[str], List[str]]:
    reasons: List[str] = []
    warnings: List[str] = []
    cat = profile.category

    if cat == "pdf":
        if profile.requires_ocr:
            reasons.append("PDF has no extractable text layer — OCR required.")
            return "ocr_pdf_to_markdown_jsonl", reasons, warnings

        if profile.text_extractable is None:
            warnings.append("PDF could not be inspected; defaulting to advanced pipeline.")
            reasons.append("Docling used for robust extraction when text-layer check fails.")
            return "advanced_pdf_docling_to_markdown_jsonl", reasons, warnings

        page_count = profile.page_count or 0
        if page_count > _MANY_PAGES_THRESHOLD:
            reasons.append(
                f"PDF has {page_count} pages (>{_MANY_PAGES_THRESHOLD}); "
                "Docling selected for reliable large-document extraction."
            )
            return "advanced_pdf_docling_to_markdown_jsonl", reasons, warnings

        reasons.append(
            f"PDF has an extractable text layer and {page_count} pages — "
            "standard parser is sufficient."
        )
        return "standard_pdf_to_markdown_jsonl", reasons, warnings

    if cat == "docx":
        reasons.append("DOCX format — Docling provides rich structure and heading extraction.")
        return "docx_to_markdown_jsonl", reasons, warnings

    if cat == "pptx":
        reasons.append("PPTX format — slide-aware extraction preserves deck structure.")
        return "pptx_to_slide_markdown_jsonl", reasons, warnings

    if cat in ("xlsx", "csv"):
        reasons.append(
            f"{cat.upper()} is tabular data — structured JSON summary preserves table structure."
        )
        return "tabular_to_structured_json_summary", reasons, warnings

    if cat in ("txt", "markdown"):
        reasons.append("Plain text format — minimal transformation needed; passthrough to Markdown JSONL.")
        return "text_to_markdown_jsonl", reasons, warnings

    if cat == "html":
        reasons.append("HTML format — boilerplate stripping and clean Markdown extraction applied.")
        return "html_to_clean_markdown_jsonl", reasons, warnings

    if cat == "image":
        reasons.append("Image file — OCR required to extract any text content.")
        return "image_ocr_to_markdown_jsonl", reasons, warnings

    warnings.append(f"Unrecognised category '{cat}'; falling back to basic text extraction.")
    return "fallback_text_extraction", reasons, warnings


class PipelineDecisionEngine:
    """
    Reads a DocumentProfile and selects the best conversion pipeline.
    Decision is cached in pipeline_decision.json; swap the class to change routing logic.
    """

    def decide(self, document_id: str) -> PipelineDecision:
        doc_dir = storage_path(settings.raw_uploads_dir, document_id)
        decision_path = doc_dir / "pipeline_decision.json"

        if decision_path.exists():
            return PipelineDecision(**json.loads(decision_path.read_text()))

        profile = DocumentProfile(**json.loads((doc_dir / "profile.json").read_text()))
        pipeline, reasons, warnings = _select_pipeline(profile)
        output_format = _OUTPUT_FORMAT.get(pipeline, "markdown_jsonl")

        decision = PipelineDecision(
            document_id=document_id,
            selected_pipeline=pipeline,
            output_format=output_format,
            output_artifacts=_DEFAULT_ARTIFACTS,
            llm_send_format_claude="xml_wrapped_markdown",
            llm_send_format_openai_gemini="markdown_with_json_metadata",
            reasons=reasons,
            warnings=warnings,
            decided_at=datetime.now(timezone.utc).isoformat(),
        )

        decision_path.write_text(json.dumps(decision.model_dump(), indent=2))

        with get_session() as session:
            repository.create_pipeline_decision(
                session,
                document_id=document_id,
                selected_pipeline=pipeline,
                output_format=output_format,
                llm_send_format="xml_wrapped_markdown / markdown_with_json_metadata",
                decision_data=decision.model_dump(),
            )
            repository.update_document_phase(session, document_id, phase="pipeline_decided")

        return decision
