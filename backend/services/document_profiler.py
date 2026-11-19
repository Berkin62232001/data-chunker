from utils.storage_paths import storage_path
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core.config import settings
from db import repository
from db.session import get_session
from models.profile_models import DocumentProfile
from utils.file_utils import get_extension, guess_mime_type

_CATEGORY_MAP = {
    ".pdf":  "pdf",
    ".docx": "docx",
    ".pptx": "pptx",
    ".xlsx": "xlsx",
    ".csv":  "csv",
    ".txt":  "txt",
    ".md":   "markdown",
    ".html": "html",
    ".png":  "image",
    ".jpg":  "image",
    ".jpeg": "image",
    ".webp": "image",
}

_CONTENT_TYPE_MAP = {
    "pdf":      "document",
    "docx":     "document",
    "pptx":     "document",
    "xlsx":     "tabular",
    "csv":      "tabular",
    "txt":      "text",
    "markdown": "text",
    "html":     "text",
    "image":    "image",
    "unknown":  None,
}

_PIPELINE_MAP = {
    "pdf":      "docling_pdf",
    "docx":     "docling_docx",
    "pptx":     "docling_pptx",
    "xlsx":     "tabular_parser",
    "csv":      "tabular_parser",
    "txt":      "plaintext_passthrough",
    "markdown": "plaintext_passthrough",
    "html":     "html_parser",
    "image":    "ocr_pipeline",
    "unknown":  "unsupported",
}

_MIN_TEXT_LAYER_CHARS = 50
_MIN_TEXT_CHARS_PER_PAGE = 40


def _profile_pdf(file_path: Path) -> dict:
    """Return explainable PDF text-layer/OCR heuristics without requiring OCR."""
    result = {
        "page_count": None,
        "text_extractable": None,
        "has_text_layer": None,
        "scanned_like": None,
        "extracted_text_char_count": None,
        "requires_ocr": False,
        "ocr_reason": None,
    }
    try:
        import pypdf

        reader = pypdf.PdfReader(str(file_path))
        page_count = len(reader.pages)
        pages_to_check = reader.pages[: max(1, min(page_count, settings.ocr_max_pages))]

        texts = [(page.extract_text() or "") for page in pages_to_check]
        extracted_chars = len("".join(texts).strip())
        inspected_pages = max(1, len(pages_to_check))
        chars_per_page = extracted_chars / inspected_pages
        has_text_layer = extracted_chars > 0
        text_extractable = extracted_chars >= _MIN_TEXT_LAYER_CHARS
        scanned_like = chars_per_page < _MIN_TEXT_CHARS_PER_PAGE

        result.update(
            {
                "page_count": page_count,
                "text_extractable": text_extractable,
                "has_text_layer": has_text_layer,
                "scanned_like": scanned_like,
                "extracted_text_char_count": extracted_chars,
            }
        )

        if not has_text_layer:
            result["requires_ocr"] = True
            result["ocr_reason"] = "PDF has no extractable text layer."
        elif scanned_like:
            result["requires_ocr"] = True
            result["ocr_reason"] = (
                "PDF has very little extractable text per page and appears scanned or image-heavy."
            )

        return result
    except Exception:
        result["ocr_reason"] = "PDF could not be inspected for an extractable text layer."
        return result


def _recommend_pipeline(category: str, requires_ocr: bool) -> str:
    if category == "pdf" and requires_ocr:
        return "ocr_pdf"
    return _PIPELINE_MAP.get(category, "unsupported")


class DocumentProfiler:
    """
    Inspects a raw uploaded file and produces a DocumentProfile.
    Results are cached in profile.json next to the raw file.
    Swap this class out to plug in Docling/Tika/Unstructured in later phases.
    """

    def profile(self, document_id: str) -> DocumentProfile:
        doc_dir = storage_path(settings.raw_uploads_dir, document_id)
        profile_path = doc_dir / "profile.json"

        if profile_path.exists():
            return DocumentProfile(**json.loads(profile_path.read_text()))

        metadata = json.loads((doc_dir / "metadata.json").read_text())
        stored_filename: str = metadata["stored_filename"]
        original_filename: str = metadata["original_filename"]
        size_bytes: int = metadata["size_bytes"]

        ext = get_extension(stored_filename)
        mime_type: Optional[str] = guess_mime_type(stored_filename) or metadata.get("mime_type")
        category = _CATEGORY_MAP.get(ext, "unknown")
        content_type: Optional[str] = _CONTENT_TYPE_MAP.get(category)

        page_count: Optional[int] = None
        text_extractable: Optional[bool] = None
        requires_ocr = False
        has_text_layer: Optional[bool] = None
        scanned_like: Optional[bool] = None
        extracted_text_char_count: Optional[int] = None
        ocr_supported = category in ("pdf", "image")
        ocr_reason: Optional[str] = None

        if category == "pdf":
            pdf_profile = _profile_pdf(doc_dir / stored_filename)
            page_count = pdf_profile["page_count"]
            text_extractable = pdf_profile["text_extractable"]
            has_text_layer = pdf_profile["has_text_layer"]
            scanned_like = pdf_profile["scanned_like"]
            extracted_text_char_count = pdf_profile["extracted_text_char_count"]
            requires_ocr = bool(pdf_profile["requires_ocr"])
            ocr_reason = pdf_profile["ocr_reason"]
        elif category == "image":
            requires_ocr = True
            scanned_like = True
            ocr_reason = "Image files require OCR to extract text."

        profile = DocumentProfile(
            document_id=document_id,
            original_filename=original_filename,
            stored_filename=stored_filename,
            extension=ext,
            mime_type=mime_type,
            size_bytes=size_bytes,
            category=category,
            content_type=content_type,
            page_count=page_count,
            text_extractable=text_extractable,
            requires_ocr=requires_ocr,
            has_text_layer=has_text_layer,
            scanned_like=scanned_like,
            extracted_text_char_count=extracted_text_char_count,
            ocr_supported=ocr_supported,
            ocr_reason=ocr_reason,
            recommended_pipeline=_recommend_pipeline(category, requires_ocr),
            profiled_at=datetime.now(timezone.utc).isoformat(),
        )

        profile_path.write_text(json.dumps(profile.model_dump(), indent=2))

        with get_session() as session:
            repository.create_profile(
                session,
                document_id=document_id,
                detected_type=category,
                mime_type=mime_type,
                page_count=page_count,
                requires_ocr=requires_ocr,
                profile_data=profile.model_dump(),
            )
            repository.update_document_phase(session, document_id, phase="profiled")

        return profile
