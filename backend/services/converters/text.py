import re
from pathlib import Path

from services.converters.base import BaseConverter, ConversionOutput


def _normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


class TxtConverter(BaseConverter):
    def convert(self, file_path: Path) -> ConversionOutput:
        is_md = file_path.suffix.lower() == ".md"
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
            return ConversionOutput(
                markdown=_normalize(text),
                converter_used="markdown_passthrough" if is_md else "txt_normalizer",
            )
        except Exception as exc:
            return ConversionOutput(
                markdown=f"# Read Error\n\n*{exc}*",
                converter_used="txt_normalizer",
                errors=[str(exc)],
            )
