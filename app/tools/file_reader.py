from pathlib import Path

import pandas as pd
from docx import Document
from openpyxl import load_workbook
from pypdf import PdfReader


# 根据文件后缀选择合适的文本抽取方式。
# txt/md 直接读文本，csv 转成 markdown 表格，Excel/Word/PDF 调用专门函数；
# 如果遇到未知后缀，就按普通文本尝试读取。
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


# 读取 Word docx 文件内容。
# 不只读取普通段落，也会遍历表格，把每行单元格用竖线拼起来，
# 最后合并成一段纯文本供检索和 Agent 阅读。
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


# 读取 Excel 工作簿内容。
# 遍历每个工作表和每一行，把非空单元格转成字符串；
# 每个工作表会带上工作表标题，方便后续知道内容来自哪个 sheet。
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


# 读取 PDF 文件内容。
# 使用 pypdf 逐页抽取文本，并用换行连接；
# 如果某一页抽不到文字，就用空字符串占位，避免程序报错。
def _read_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)
