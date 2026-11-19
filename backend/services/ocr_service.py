import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from core.config import settings
from models.ocr_models import OCRAvailability, OCRResult

logger = logging.getLogger(__name__)


class LocalOCRService:
    """Optional local OCR integration. No cloud calls are made."""

    def __init__(self, provider: Optional[str] = None) -> None:
        self.provider = (provider or settings.ocr_provider).strip().lower()

    def is_ocr_available(self) -> OCRAvailability:
        warnings = []
        if self.provider == "ocrmypdf":
            missing = [
                binary
                for binary in ("ocrmypdf", "tesseract")
                if shutil.which(binary) is None
            ]
            if missing:
                return OCRAvailability(
                    available=False,
                    provider=self.provider,
                    language=settings.ocr_language,
                    warnings=warnings,
                    error=f"OCR unavailable. Missing local command(s): {', '.join(missing)}.",
                )
            return OCRAvailability(
                available=True,
                provider=self.provider,
                language=settings.ocr_language,
                warnings=warnings,
            )

        if self.provider in ("local_tesseract", "tesseract"):
            if shutil.which("tesseract") is None:
                return OCRAvailability(
                    available=False,
                    provider=self.provider,
                    language=settings.ocr_language,
                    warnings=warnings,
                    error="OCR unavailable. Missing local command: tesseract.",
                )
            warnings.append("PDF OCR requires OCRmyPDF; local_tesseract supports image OCR only.")
            return OCRAvailability(
                available=True,
                provider=self.provider,
                language=settings.ocr_language,
                warnings=warnings,
            )

        return OCRAvailability(
            available=False,
            provider=self.provider,
            language=settings.ocr_language,
            error=f"Unsupported OCR_PROVIDER '{settings.ocr_provider}'.",
        )

    def ocr_pdf_to_text(
        self,
        input_pdf_path: Path,
        document_id: str,
        language: Optional[str] = None,
        max_pages: Optional[int] = None,
        timeout: Optional[int] = None,
    ) -> OCRResult:
        language = language or settings.ocr_language
        max_pages = max_pages or settings.ocr_max_pages
        timeout = timeout or settings.ocr_timeout_seconds

        if self.provider != "ocrmypdf":
            return OCRResult(
                provider=self.provider,
                language=language,
                warnings=["PDF OCR requires OCRmyPDF."],
                succeeded=False,
                error="OCR unavailable for PDFs with the configured provider.",
            )

        availability = self.is_ocr_available()
        if not availability.available:
            return OCRResult(
                provider=self.provider,
                language=language,
                warnings=availability.warnings,
                succeeded=False,
                error=availability.error,
            )

        with tempfile.TemporaryDirectory(prefix=f"ocr_{document_id}_") as tmp_dir:
            output_pdf = Path(tmp_dir) / "ocr_output.pdf"
            command = [
                "ocrmypdf",
                "--language",
                language,
                "--skip-text",
                "--output-type",
                "pdf",
                "--jobs",
                "1",
            ]
            if settings.ocr_dpi > 0:
                command.extend(["--image-dpi", str(settings.ocr_dpi)])
            if max_pages > 0:
                command.extend(["--pages", f"1-{max_pages}"])
            command.extend([str(input_pdf_path), str(output_pdf)])

            try:
                completed = subprocess.run(
                    command,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
            except subprocess.TimeoutExpired:
                return OCRResult(
                    provider=self.provider,
                    language=language,
                    pages_processed=0,
                    succeeded=False,
                    error=f"OCR timed out after {timeout} seconds.",
                )

            if completed.returncode != 0:
                return OCRResult(
                    provider=self.provider,
                    language=language,
                    pages_processed=0,
                    succeeded=False,
                    error=f"OCR command failed with exit code {completed.returncode}.",
                )

            text, pages_processed, warning = _extract_pdf_text(output_pdf, max_pages)
            warnings = []
            if warning:
                warnings.append(warning)
            if not text.strip():
                warnings.append("OCR completed but produced no extractable text.")
            return OCRResult(
                text=text,
                provider=self.provider,
                language=language,
                pages_processed=pages_processed,
                warnings=warnings,
                succeeded=True,
                artifacts=["ocr_output.pdf"],
            )

    def ocr_image_to_text(
        self,
        image_path: Path,
        language: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> OCRResult:
        language = language or settings.ocr_language
        timeout = timeout or settings.ocr_timeout_seconds

        if shutil.which("tesseract") is None:
            return OCRResult(
                provider=self.provider,
                language=language,
                succeeded=False,
                error="OCR unavailable. Missing local command: tesseract.",
            )

        command = ["tesseract", str(image_path), "stdout", "-l", language]
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return OCRResult(
                provider=self.provider,
                language=language,
                succeeded=False,
                error=f"OCR timed out after {timeout} seconds.",
            )

        if completed.returncode != 0:
            return OCRResult(
                provider=self.provider,
                language=language,
                succeeded=False,
                error=f"OCR command failed with exit code {completed.returncode}.",
            )

        text = completed.stdout.strip()
        warnings = [] if text else ["OCR completed but produced no extractable text."]
        return OCRResult(
            text=text,
            provider=self.provider,
            language=language,
            pages_processed=1,
            warnings=warnings,
            succeeded=True,
        )


def _extract_pdf_text(pdf_path: Path, max_pages: int) -> tuple[str, int, Optional[str]]:
    try:
        import pypdf

        reader = pypdf.PdfReader(str(pdf_path))
        pages = reader.pages[: max(1, min(len(reader.pages), max_pages))]
        sections = []
        for index, page in enumerate(pages):
            text = (page.extract_text() or "").strip()
            if text:
                sections.append(f"## Page {index + 1}\n\n{text}")
        return "\n\n---\n\n".join(sections), len(pages), None
    except Exception as exc:
        logger.warning("Text extraction from OCR output PDF %s failed: %s", pdf_path, exc)
        return "", 0, "OCR text extraction from generated PDF failed."
