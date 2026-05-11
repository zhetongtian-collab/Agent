from pathlib import Path
import re
from uuid import uuid4

from docx import Document
from openpyxl import Workbook

from app.core.config import settings


# 根据文本内容生成 Word 文档。
# filename 用来生成安全的文件名，content 按行拆分后逐段写入 Word；
# 如果 content 没有可用行，就把原始内容作为一个段落写进去。
# 最后返回生成文件在本地磁盘上的 Path。
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


# 根据文本内容生成 Excel 文件。
# filename 用来生成安全的文件名，content 会按行拆分；
# 每一行再按制表符、逗号或竖线拆成单元格，写入 Sheet1。
# 最后返回生成文件在本地磁盘上的 Path。
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


# 生成安全的文件主名。
# 会去掉目录和扩展名，只保留中英文、数字、下划线和短横线等安全字符；
# 同时限制长度，避免文件名过长或为空。
def _safe_stem(filename: str) -> str:
    stem = Path(filename).stem or "artifact"
    cleaned = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", stem).strip("_")
    return cleaned[:64] or "artifact"


# 把一行文本拆成 Excel 的单元格列表。
# 优先识别制表符，其次识别英文逗号，再识别竖线；
# 如果都没有，就把整行作为一个单元格。
def _split_row(line: str) -> list[str]:
    if "\t" in line:
        return [item.strip() for item in line.split("\t")]
    if "," in line:
        return [item.strip() for item in line.split(",")]
    if "|" in line:
        return [item.strip() for item in line.split("|")]
    return [line.strip()]
