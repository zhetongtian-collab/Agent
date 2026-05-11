from pathlib import Path
from typing import Any

from openpyxl import load_workbook


# 分析 Excel 文件的结构，返回每个工作表的概览信息。
# max_rows 控制每个工作表最多展示多少行样例数据。
# 返回结果包括工作表名、非空行数、列数、表头和样例行，
# 方便 Agent 在不读取完整大表的情况下先了解表格长什么样。
def analyze_excel_file(path: str | Path, max_rows: int = 5) -> dict[str, Any]:
    workbook = load_workbook(path, data_only=True, read_only=True)
    try:
        sheets = []
        for sheet in workbook.worksheets:
            rows = list(sheet.iter_rows(values_only=True))
            non_empty_rows = [
                ["" if value is None else value for value in row]
                for row in rows
                if any(value is not None and str(value).strip() for value in row)
            ]
            headers = [str(value) for value in non_empty_rows[0]] if non_empty_rows else []
            samples = [
                ["" if value is None else str(value) for value in row]
                for row in non_empty_rows[1 : max_rows + 1]
            ]
            sheets.append(
                {
                    "sheet_name": sheet.title,
                    "row_count": len(non_empty_rows),
                    "column_count": max((len(row) for row in non_empty_rows), default=0),
                    "headers": headers,
                    "sample_rows": samples,
                }
            )
        return {"sheets": sheets}
    finally:
        workbook.close()
