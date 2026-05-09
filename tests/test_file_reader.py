from pathlib import Path

from docx import Document
from openpyxl import Workbook

from app.tools.file_reader import extract_text


def test_extract_text_from_txt(tmp_path: Path) -> None:
    path = tmp_path / "demo.txt"
    path.write_text("hello office agent", encoding="utf-8")
    assert "hello office agent" in extract_text(path)


def test_extract_text_from_docx(tmp_path: Path) -> None:
    path = tmp_path / "demo.docx"
    document = Document()
    document.add_paragraph("季度报告")
    document.save(path)
    assert "季度报告" in extract_text(path)


def test_extract_text_from_xlsx(tmp_path: Path) -> None:
    path = tmp_path / "demo.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "销售"
    sheet.append(["产品", "金额"])
    sheet.append(["A", 100])
    workbook.save(path)
    assert "销售" in extract_text(path)
    assert "产品 | 金额" in extract_text(path)
