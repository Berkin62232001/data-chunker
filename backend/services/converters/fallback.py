from pathlib import Path

from services.converters.base import BaseConverter, ConversionOutput

# These formats need dedicated converters; raw text extraction makes no sense for them.
_BINARY_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".pdf", ".docx", ".pptx", ".xlsx"}


class FallbackConverter(BaseConverter):
    def convert(self, file_path: Path) -> ConversionOutput:
        suffix = file_path.suffix.lower()

        if suffix in _BINARY_EXTENSIONS:
            return ConversionOutput(
                markdown=(
                    f"# {file_path.name}\n\n"
                    f"*File type `{suffix}` requires a dedicated converter "
                    "not yet available in this phase.*"
                ),
                converter_used="fallback_unsupported",
                warnings=[f"No converter available for `{suffix}` in this phase."],
                fallback_used=True,
            )

        try:
            text = file_path.read_text(encoding="utf-8", errors="replace").strip()
            note = "*Note: No dedicated converter for this file type. Raw text extracted.*\n\n"
            return ConversionOutput(
                markdown=f"# {file_path.name}\n\n{note}{text}",
                converter_used="fallback_text",
                warnings=["Unsupported file type; raw text extraction used."],
                fallback_used=True,
            )
        except Exception as exc:
            return ConversionOutput(
                markdown=f"# Extraction Failed\n\n*{exc}*",
                converter_used="fallback_text",
                errors=[str(exc)],
                fallback_used=True,
            )
