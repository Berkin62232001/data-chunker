from pathlib import Path
from typing import List

from services.converters.base import BaseConverter, ConversionOutput


class PdfConverter(BaseConverter):
    def convert(self, file_path: Path) -> ConversionOutput:
        docling_error: str = ""

        # Attempt Docling (optional heavy dependency)
        try:
            from docling.document_converter import DocumentConverter  # type: ignore

            converter = DocumentConverter()
            result = converter.convert(str(file_path))
            markdown = result.document.export_to_markdown()
            return ConversionOutput(markdown=markdown, converter_used="docling_pdf")
        except ImportError:
            pass  # Not installed — go straight to pypdf
        except Exception as exc:
            docling_error = str(exc)

        return self._convert_with_pypdf(file_path, docling_error)

    def _convert_with_pypdf(self, file_path: Path, docling_error: str = "") -> ConversionOutput:
        warnings: List[str] = []
        if docling_error:
            warnings.append(f"Docling failed ({docling_error}); using pypdf fallback.")

        try:
            import pypdf

            reader = pypdf.PdfReader(str(file_path))
            sections: List[str] = []

            for i, page in enumerate(reader.pages):
                text = (page.extract_text() or "").strip()
                if text:
                    sections.append(f"## Page {i + 1}\n\n{text}")

            if not sections:
                warnings.append("No extractable text found — document may be scanned.")
                markdown = (
                    "# PDF Document\n\n"
                    "*No text could be extracted. OCR may be required.*"
                )
            else:
                markdown = "\n\n---\n\n".join(sections)

            return ConversionOutput(
                markdown=markdown,
                converter_used="pypdf_fallback",
                warnings=warnings,
                fallback_used=bool(docling_error) or True,
            )
        except Exception as exc:
            return ConversionOutput(
                markdown=f"# PDF Extraction Failed\n\n*{exc}*",
                converter_used="pypdf_fallback",
                errors=[str(exc)],
                warnings=warnings,
                fallback_used=True,
            )
