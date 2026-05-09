from pathlib import Path
import re
from uuid import uuid4

from docx import Document
from openpyxl import Workbook

from app.core.config import settings


def generate_word(filename: str, content: str) -> Path:
    settings.artifact_dir.mkdir(parents=True, exist_ok=True)
    path = settings.artifact_dir / f"{_safe_stem(filename)}-{uuid4().hex[:8]}.docx"
    document = Document()
    for block in content.splitlines():
        text = block.strip()
        if text:
            document.add_paragraph(text)
    if not document.paragraphs:
        document.add_paragraph(content)
    document.save(path)
    return path


def generate_excel(filename: str, content: str) -> Path:
    settings.artifact_dir.mkdir(parents=True, exist_ok=True)
    path = settings.artifact_dir / f"{_safe_stem(filename)}-{uuid4().hex[:8]}.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Sheet1"
    rows = [line for line in content.splitlines() if line.strip()]
    for row_index, line in enumerate(rows or [content], start=1):
        cells = _split_row(line)
        for col_index, value in enumerate(cells, start=1):
            sheet.cell(row=row_index, column=col_index, value=value)
    workbook.save(path)
    return path


def _safe_stem(filename: str) -> str:
    stem = Path(filename).stem or "artifact"
    cleaned = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", stem).strip("_")
    return cleaned[:64] or "artifact"


def _split_row(line: str) -> list[str]:
    if "\t" in line:
        return [item.strip() for item in line.split("\t")]
    if "," in line:
        return [item.strip() for item in line.split(",")]
    if "|" in line:
        return [item.strip() for item in line.split("|")]
    return [line.strip()]
