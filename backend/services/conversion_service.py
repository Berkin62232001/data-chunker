from utils.storage_paths import storage_path
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Tuple

from core.config import settings
from db import repository
from db.session import get_session
from models.conversion_models import ConversionMetadata, ConversionResult, ExtractionReport
from models.ocr_models import OCRResult
from models.pipeline_models import PipelineDecision
from models.profile_models import DocumentProfile
from services import audit_log_service
from services.converters.base import BaseConverter, ConversionOutput
from services.converters.csv import CsvConverter
from services.converters.docx import DocxConverter
from services.converters.fallback import FallbackConverter
from services.converters.pdf import PdfConverter
from services.converters.text import TxtConverter
from services.ocr_service import LocalOCRService

_fallback = FallbackConverter()

_CONVERTERS: Dict[str, BaseConverter] = {
    "text_to_markdown_jsonl":              TxtConverter(),
    "tabular_to_structured_json_summary":  CsvConverter(),
    "standard_pdf_to_markdown_jsonl":      PdfConverter(),
    "advanced_pdf_docling_to_markdown_jsonl": PdfConverter(),
    "ocr_pdf_to_markdown_jsonl":           PdfConverter(),
    "docx_to_markdown_jsonl":              DocxConverter(),
    "pptx_to_slide_markdown_jsonl":        _fallback,
    "html_to_clean_markdown_jsonl":        _fallback,
    "image_ocr_to_markdown_jsonl":         _fallback,
    "fallback_text_extraction":            _fallback,
}

_PREVIEW_CHARS = 2000
_OCR_DISABLED_WARNING = "This document appears scanned or image-heavy. Enable OCR to extract text."


def _status_from(output: ConversionOutput) -> str:
    if output.errors:
        return "failed"
    if output.warnings:
        return "partial"
    return "success"


class ConversionService:
    def __init__(self, ocr_service: Optional[LocalOCRService] = None) -> None:
        self._ocr_service = ocr_service

    def convert(self, document_id: str) -> ConversionResult:
        raw_dir = storage_path(settings.raw_uploads_dir, document_id)
        out_dir = storage_path(settings.converted_dir, document_id)
        out_dir.mkdir(parents=True, exist_ok=True)

        raw_meta = json.loads((raw_dir / "metadata.json").read_text())
        decision = PipelineDecision(**json.loads((raw_dir / "pipeline_decision.json").read_text()))
        profile = DocumentProfile(**json.loads((raw_dir / "profile.json").read_text()))

        raw_file = raw_dir / raw_meta["stored_filename"]
        converter = _CONVERTERS.get(decision.selected_pipeline, _fallback)
        output: ConversionOutput = converter.convert(raw_file)
        output, ocr_result = self._apply_ocr_if_needed(document_id, raw_file, profile, output)

        # Write document.md
        (out_dir / "document.md").write_text(output.markdown, encoding="utf-8")

        char_count = len(output.markdown)
        status = _status_from(output)

        meta = ConversionMetadata(
            document_id=document_id,
            original_filename=raw_meta["original_filename"],
            source_mime_type=profile.mime_type,
            selected_pipeline=decision.selected_pipeline,
            conversion_status=status,
            created_at=datetime.now(timezone.utc).isoformat(),
            output_files=["document.md", "metadata.json", "extraction_report.json"],
            estimated_character_count=char_count,
            estimated_token_count=char_count // 4,
        )
        (out_dir / "metadata.json").write_text(json.dumps(meta.model_dump(), indent=2))

        report = ExtractionReport(
            success=not bool(output.errors),
            converter_used=output.converter_used,
            warnings=output.warnings,
            errors=output.errors,
            fallback_used=output.fallback_used,
            ocr_used=bool(ocr_result and ocr_result.succeeded and ocr_result.text.strip()),
            ocr_provider=ocr_result.provider if ocr_result else None,
            ocr_language=ocr_result.language if ocr_result else None,
            ocr_pages_processed=ocr_result.pages_processed if ocr_result else None,
            ocr_succeeded=ocr_result.succeeded if ocr_result else None,
            ocr_warnings=ocr_result.warnings if ocr_result else [],
            ocr_error=ocr_result.error if ocr_result else None,
            ocr_text_char_count=len(ocr_result.text) if ocr_result else 0,
        )
        (out_dir / "extraction_report.json").write_text(
            json.dumps(report.model_dump(), indent=2)
        )

        audit_log_service.append(
            "conversion",
            document_id,
            pipeline=decision.selected_pipeline,
            status=status,
            char_count=char_count,
        )

        with get_session() as session:
            repository.create_conversion(
                session,
                document_id=document_id,
                status=status,
                converter_used=report.converter_used,
                estimated_tokens=meta.estimated_token_count,
                warnings=report.warnings,
            )
            repository.update_document_phase(
                session, document_id, phase="converted", status=status
            )

        return ConversionResult(
            document_id=document_id,
            conversion_status=status,
            markdown_path=str(out_dir / "document.md"),
            markdown_preview=output.markdown[:_PREVIEW_CHARS],
            metadata=meta,
            report=report,
        )

    def _apply_ocr_if_needed(
        self,
        document_id: str,
        raw_file: Path,
        profile: DocumentProfile,
        output: ConversionOutput,
    ) -> Tuple[ConversionOutput, Optional[OCRResult]]:
        if not profile.requires_ocr or not profile.ocr_supported:
            return output, None

        if not settings.ocr_enabled:
            output.warnings.append(_OCR_DISABLED_WARNING)
            return output, None

        ocr_result: OCRResult
        if profile.category == "pdf":
            ocr_result = self._ocr_service_instance().ocr_pdf_to_text(
                raw_file,
                document_id=document_id,
                language=settings.ocr_language,
                max_pages=settings.ocr_max_pages,
                timeout=settings.ocr_timeout_seconds,
            )
        elif profile.category == "image":
            ocr_result = self._ocr_service_instance().ocr_image_to_text(
                raw_file,
                language=settings.ocr_language,
                timeout=settings.ocr_timeout_seconds,
            )
        else:
            return output, None

        if ocr_result.succeeded and ocr_result.text.strip():
            return ConversionOutput(
                markdown=ocr_result.text,
                converter_used=f"{ocr_result.provider}_ocr",
                warnings=ocr_result.warnings,
                errors=[],
                fallback_used=False,
            ), ocr_result

        message = ocr_result.error or "OCR did not produce extractable text."
        if settings.ocr_fail_open:
            output.warnings.append(message)
        else:
            output.errors.append(message)
        return output, ocr_result

    def _ocr_service_instance(self) -> LocalOCRService:
        return self._ocr_service or LocalOCRService()

    def get_result(self, document_id: str) -> ConversionResult:
        out_dir = storage_path(settings.converted_dir, document_id)
        meta = ConversionMetadata(
            **json.loads((out_dir / "metadata.json").read_text())
        )
        report = ExtractionReport(
            **json.loads((out_dir / "extraction_report.json").read_text())
        )
        markdown_text = (out_dir / "document.md").read_text(encoding="utf-8")
        return ConversionResult(
            document_id=document_id,
            conversion_status=meta.conversion_status,
            markdown_path=str(out_dir / "document.md"),
            markdown_preview=markdown_text[:_PREVIEW_CHARS],
            metadata=meta,
            report=report,
        )
