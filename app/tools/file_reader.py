from pathlib import Path

import pandas as pd
from docx import Document
from openpyxl import load_workbook
from pypdf import PdfReader


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return path.read_text(encoding="utf-8", errors="ignore")
    if suffix == ".csv":
        return pd.read_csv(path).to_markdown(index=False)
    if suffix in {".xlsx", ".xlsm"}:
        return _read_excel(path)
    if suffix == ".docx":
        return _read_docx(path)
    if suffix == ".pdf":
        return _read_pdf(path)
    return path.read_text(encoding="utf-8", errors="ignore")


def _read_docx(path: Path) -> str:
    document = Document(path)
    parts: list[str] = []
    parts.extend(paragraph.text for paragraph in document.paragraphs if paragraph.text.strip())
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            if any(cells):
                parts.append(" | ".join(cells))
    return "\n".join(parts)


def _read_excel(path: Path) -> str:
    workbook = load_workbook(path, data_only=True, read_only=True)
    sheets: list[str] = []
    for sheet in workbook.worksheets:
        rows = []
        for row in sheet.iter_rows(values_only=True):
            values = ["" if value is None else str(value) for value in row]
            if any(values):
                rows.append(" | ".join(values))
        if rows:
            sheets.append(f"工作表：{sheet.title}\n" + "\n".join(rows))
    workbook.close()
    return "\n\n".join(sheets)


def _read_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)
