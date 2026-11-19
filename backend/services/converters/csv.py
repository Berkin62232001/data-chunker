import csv
import io
from pathlib import Path
from typing import List, Optional

from services.converters.base import BaseConverter, ConversionOutput

_MAX_PREVIEW_ROWS = 50


def _build_md_table(headers: List[str], rows: List[List[str]]) -> List[str]:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        padded = (list(row) + [""] * len(headers))[: len(headers)]
        cells = [str(c).replace("|", "\\|") for c in padded]
        lines.append("| " + " | ".join(cells) + " |")
    return lines


class CsvConverter(BaseConverter):
    def convert(self, file_path: Path) -> ConversionOutput:
        if file_path.suffix.lower() == ".xlsx":
            return self._convert_xlsx(file_path)
        return self._convert_csv(file_path)

    def _convert_csv(self, file_path: Path) -> ConversionOutput:
        warnings: List[str] = []
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
            reader = csv.reader(io.StringIO(text))
            rows = list(reader)
        except Exception as exc:
            return ConversionOutput(
                markdown=f"# CSV Parse Error\n\n*{exc}*",
                converter_used="csv_converter",
                errors=[str(exc)],
            )

        if not rows:
            return ConversionOutput(
                markdown="# Empty CSV\n\n*No data found.*",
                converter_used="csv_converter",
                warnings=["CSV file is empty."],
            )

        headers = [str(c) for c in rows[0]]
        data_rows = rows[1:]
        total_rows = len(data_rows)

        if total_rows > _MAX_PREVIEW_ROWS:
            preview = data_rows[:_MAX_PREVIEW_ROWS]
            warnings.append(f"Large file: showing {_MAX_PREVIEW_ROWS} of {total_rows} rows.")
        else:
            preview = data_rows

        lines = [
            f"# {file_path.name}",
            "",
            f"**Columns:** {len(headers)} | **Rows:** {total_rows}",
            "",
        ] + _build_md_table(headers, preview)

        if total_rows > _MAX_PREVIEW_ROWS:
            lines.append(f"\n*…{total_rows - _MAX_PREVIEW_ROWS} more rows not shown.*")

        return ConversionOutput(
            markdown="\n".join(lines),
            converter_used="csv_converter",
            warnings=warnings,
        )

    def _convert_xlsx(self, file_path: Path) -> ConversionOutput:
        warnings: List[str] = []
        try:
            import openpyxl
        except ImportError:
            return ConversionOutput(
                markdown=(
                    f"# {file_path.name}\n\n"
                    "*Install openpyxl to enable XLSX conversion: `pip install openpyxl`*"
                ),
                converter_used="xlsx_stub",
                warnings=["openpyxl not installed; XLSX conversion unavailable."],
                fallback_used=True,
            )

        try:
            wb = openpyxl.load_workbook(str(file_path), read_only=True, data_only=True)
            sections: List[str] = []

            for sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
                all_rows = [
                    [str(c) if c is not None else "" for c in row]
                    for row in ws.iter_rows(values_only=True)
                ]
                if not all_rows:
                    continue

                headers = all_rows[0]
                data_rows = all_rows[1:]
                total_rows = len(data_rows)

                if total_rows > _MAX_PREVIEW_ROWS:
                    preview = data_rows[:_MAX_PREVIEW_ROWS]
                    warnings.append(
                        f"Sheet '{sheet_name}': showing {_MAX_PREVIEW_ROWS} of {total_rows} rows."
                    )
                else:
                    preview = data_rows

                section = [
                    f"## Sheet: {sheet_name}",
                    "",
                    f"**Columns:** {len(headers)} | **Rows:** {total_rows}",
                    "",
                ] + _build_md_table(headers, preview)

                if total_rows > _MAX_PREVIEW_ROWS:
                    section.append(f"\n*…{total_rows - _MAX_PREVIEW_ROWS} more rows not shown.*")

                sections.append("\n".join(section))

            wb.close()
            markdown = f"# {file_path.name}\n\n" + "\n\n".join(sections)
            return ConversionOutput(
                markdown=markdown,
                converter_used="xlsx_converter",
                warnings=warnings,
            )
        except Exception as exc:
            return ConversionOutput(
                markdown=f"# XLSX Parse Error\n\n*{exc}*",
                converter_used="xlsx_converter",
                errors=[str(exc)],
            )
