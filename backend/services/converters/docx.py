from pathlib import Path
from typing import List

from services.converters.base import BaseConverter, ConversionOutput


class DocxConverter(BaseConverter):
    def convert(self, file_path: Path) -> ConversionOutput:
        docling_error: str = ""

        # Attempt Docling (optional heavy dependency)
        try:
            from docling.document_converter import DocumentConverter  # type: ignore

            converter = DocumentConverter()
            result = converter.convert(str(file_path))
            markdown = result.document.export_to_markdown()
            return ConversionOutput(markdown=markdown, converter_used="docling_docx")
        except ImportError:
            pass
        except Exception as exc:
            docling_error = str(exc)

        return self._convert_with_python_docx(file_path, docling_error)

    def _convert_with_python_docx(self, file_path: Path, docling_error: str = "") -> ConversionOutput:
        warnings: List[str] = []
        if docling_error:
            warnings.append(f"Docling failed ({docling_error}); using python-docx fallback.")

        try:
            from docx import Document as DocxDocument  # type: ignore

            doc = DocxDocument(str(file_path))
            lines: List[str] = []

            for para in doc.paragraphs:
                text = para.text.strip()
                if not text:
                    lines.append("")
                    continue
                style = para.style.name if para.style else ""
                if "Heading 1" in style:
                    lines.append(f"# {text}")
                elif "Heading 2" in style:
                    lines.append(f"## {text}")
                elif "Heading 3" in style:
                    lines.append(f"### {text}")
                else:
                    lines.append(text)

            markdown = "\n".join(lines).strip() or "*No text content found in document.*"
            return ConversionOutput(
                markdown=markdown,
                converter_used="python_docx_fallback",
                warnings=warnings,
                fallback_used=True,
            )
        except ImportError:
            return ConversionOutput(
                markdown="# DOCX Extraction Failed\n\n*python-docx not installed.*",
                converter_used="no_converter",
                errors=["python-docx not installed. Run: pip install python-docx"],
                warnings=warnings,
                fallback_used=True,
            )
        except Exception as exc:
            return ConversionOutput(
                markdown=f"# DOCX Extraction Failed\n\n*{exc}*",
                converter_used="python_docx_fallback",
                errors=[str(exc)],
                warnings=warnings,
                fallback_used=True,
            )
