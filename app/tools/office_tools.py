from pathlib import Path
import json
import re
from typing import Any, Literal

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import FileRecord, PdfTableRecord, TaskArtifact
from app.memory.store import MemoryStore
from app.memory.vector_store import VectorStore
from app.tools.email_tools import (
    EmailAttachment,
    EmailConfigurationError,
    EmailReceiveError,
    EmailSendError,
    fetch_unread_email_messages,
    send_email_message,
)
from app.tools.excel_tools import (
    analyze_excel_file,
    filter_excel_rows,
    generate_excel_chart_image,
    lookup_excel_value,
    read_excel_range_data,
    sum_excel_range,
)
from app.tools.json_utils import fail, ok
from app.tools.output_tools import edit_excel_cells, fill_excel_formula, generate_excel, generate_word, write_excel_range


# 通用搜索工具的入参模型。
# Agent 调用需要“搜索某些内容”的工具时，会按这个结构传入关键词 query 和返回条数 limit。
class SearchInput(BaseModel):
    query: str = Field(description="用户问题或检索关键词")
    limit: int = Field(default=5, ge=1, le=10)


# 文件搜索工具的入参模型。
# 在通用搜索参数基础上增加 file_ids，
# 这样 Agent 可以选择只在用户指定的某几个上传文件里检索相关内容。
class SearchFilesInput(BaseModel):
    query: str = Field(description="用户问题或检索关键词")
    limit: int = Field(default=5, ge=1, le=10)
    file_ids: list[int] = Field(default_factory=list, description="如果只想检索指定文件，传入文件 ID 列表")


# 保存长期记忆工具的入参模型。
# content 表示需要长期保存的事实或偏好，例如用户身份、项目背景、输出格式偏好等。
class SaveMemoryInput(BaseModel):
    content: str = Field(description="需要长期保存的用户偏好、业务背景或事实")


# 读取上传文件工具的入参模型。
# file_id 指定要读取哪个文件，max_chars 限制最多返回多少字符，
# 避免一次性把超长文件内容全部塞给大模型。
class ReadFileInput(BaseModel):
    file_id: int = Field(description="上传文件的 ID")
    max_chars: int = Field(default=12000, ge=500, le=30000, description="最多返回多少字符")


# Excel 分析工具的入参模型。
# 只需要一个 file_id，用来告诉工具要分析哪一个已上传的 Excel 文件。
class AnalyzeExcelInput(BaseModel):
    file_id: int = Field(description="Excel 文件 ID")


class GenerateExcelChartInput(BaseModel):
    file_id: int = Field(description="已上传 Excel 文件的 ID")
    chart_type: Literal["line", "bar"] = Field(description="图表类型：line 表示折线图，bar 表示柱状图")
    sheet_name: str | None = Field(default=None, description="可选。工作表名称；不传时使用当前活动工作表。")
    x_axis_column: str | None = Field(
        default=None,
        description="可选。横轴列名、列字母或从 1 开始的列序号；不传时使用第一列。",
    )
    y_columns: list[str] | None = Field(
        default=None,
        description="可选。数值系列列，可传列名、列字母或从 1 开始的列序号；不传时自动识别数值列。",
    )
    title: str | None = Field(default=None, description="可选。图表标题")
    max_rows: int = Field(default=50, ge=1, le=200, description="最多纳入多少行数据")


# Word 生成工具的入参模型。
# title 用作报告标题或文件名来源，content 是要写入 Word 文档的正文内容。
class ListPdfTablesInput(BaseModel):
    file_id: int = Field(description="PDF 文件 ID")


class ReadPdfTableInput(BaseModel):
    file_id: int = Field(description="PDF 文件 ID")
    table_label: str = Field(description="表格编号，例如 Table 1、TABLE I、表 1")


class GenerateWordInput(BaseModel):
    title: str = Field(description="报告标题或文件名")
    content: str = Field(description="Word 正文内容")


# Excel 生成工具的入参模型。
# filename 用来生成导出的 Excel 文件名，content 是表格文本，
# 后续会按逗号、制表符或竖线拆分成单元格。
class GenerateExcelInput(BaseModel):
    filename: str = Field(description="Excel 文件名")
    content: str = Field(description="表格内容，支持逗号、制表符或竖线分隔")
    highlight_gt: float | None = Field(default=None, description="可选。数值大于该阈值时标红，例如 500")
    highlight_lt: float | None = Field(default=None, description="可选。数值小于该阈值时标红，例如 1000")
    highlight_column: str | None = Field(default=None, description="可选。只按指定列判断，例如 销售额、B、2")
    highlight_scope: Literal["row", "cell"] = Field(default="row", description="标红范围：row 标红整行，cell 只标红超阈值单元格")


class ExcelCellUpdate(BaseModel):
    cell: str = Field(description="需要写入的单元格地址，例如 B7、J2")
    value: Any = Field(description="写入值。可以是文本、数字、布尔值或以 = 开头的 Excel 公式")
    sheet_name: str | None = Field(default=None, description="可选。工作表名称；不传时使用当前活动工作表")


class EditExcelCellsInput(BaseModel):
    file_id: int = Field(description="需要修改的已上传 Excel 文件 ID")
    filename: str = Field(default="edited_workbook.xlsx", description="生成的 Excel 文件名")
    updates: list[ExcelCellUpdate] = Field(min_length=1, description="要写入的单元格更新列表")


class ReadExcelRangeInput(BaseModel):
    file_id: int = Field(description="已上传 Excel 文件 ID")
    cell_range: str = Field(description="读取区域，例如 A1:F20")
    sheet_name: str | None = Field(default=None, description="可选。工作表名称")
    data_only: bool = Field(default=True, description="是否读取公式计算后的值；false 时读取公式文本")
    max_cells: int = Field(default=2000, ge=1, le=10000, description="最多读取多少个单元格")


class SumExcelRangeInput(BaseModel):
    file_id: int = Field(description="已上传 Excel 文件 ID")
    sum_range: str = Field(description="求和区域，例如 B2:B12")
    sheet_name: str | None = Field(default=None, description="可选。工作表名称")
    criteria_range: str | None = Field(default=None, description="可选。条件区域，例如 A2:A12")
    criteria: Any | None = Field(default=None, description="可选。条件值，例如 111111")


class LookupExcelValueInput(BaseModel):
    file_id: int = Field(description="已上传 Excel 文件 ID")
    lookup_value: Any = Field(description="查找值")
    lookup_range: str = Field(description="查找区域，例如 A2:A12")
    result_range: str = Field(description="返回值区域，例如 B2:B12")
    sheet_name: str | None = Field(default=None, description="可选。工作表名称")


class FilterExcelRowsInput(BaseModel):
    file_id: int = Field(description="已上传 Excel 文件 ID")
    data_range: str = Field(description="包含表头的数据区域，例如 A1:C200")
    column: str = Field(description="筛选列名、列字母或从 1 开始的列序号")
    operator: Literal["eq", "neq", "contains", "gt", "gte", "lt", "lte"] = Field(description="筛选操作")
    value: Any = Field(description="筛选值")
    sheet_name: str | None = Field(default=None, description="可选。工作表名称")
    limit: int = Field(default=200, ge=1, le=1000, description="最多返回多少行")


class WriteExcelRangeInput(BaseModel):
    file_id: int = Field(description="需要修改的已上传 Excel 文件 ID")
    filename: str = Field(default="edited_workbook.xlsx", description="生成的 Excel 文件名")
    start_cell: str = Field(description="写入起始单元格，例如 B2")
    values: list[list[Any]] = Field(min_length=1, description="按行提供二维值列表")
    sheet_name: str | None = Field(default=None, description="可选。工作表名称")


class FillExcelFormulaInput(BaseModel):
    file_id: int = Field(description="需要修改的已上传 Excel 文件 ID")
    filename: str = Field(default="formula_workbook.xlsx", description="生成的 Excel 文件名")
    cell_range: str = Field(description="填充区域，例如 C2:C20")
    formula: str = Field(description="左上角单元格使用的 Excel 公式，必须以 = 开头")
    sheet_name: str | None = Field(default=None, description="可选。工作表名称")


class SendEmailInput(BaseModel):
    to: str = Field(description="收件人邮箱地址，例如 1254543711@qq.com")
    subject: str = Field(default="LongChain Office Agent", description="邮件主题")
    content: str = Field(description="邮件正文内容")
    file_ids: list[int] = Field(default_factory=list, description="需要作为附件发送的已上传文件 ID 列表")


class FetchUnreadEmailsInput(BaseModel):
    limit: int = Field(default=5, ge=1, le=20, description="最多拉取多少封未读邮件")
    body_max_chars: int = Field(default=4000, ge=500, le=20000, description="每封邮件正文或文本附件最多返回多少字符")
    mark_read: bool = Field(default=True, description="拉取成功后是否把这些未读邮件标记为已读，默认标记为已读")


# 构建给办公 Agent 使用的一组工具。
# 这些工具会被 LangChain 包装成 StructuredTool，模型可以根据任务自主调用。
# db 用于查上传文件、保存 artifact 和读写记忆；
# public_base_url 用于把下载路径拼成前端可直接访问的完整地址。
def build_office_tools(db: Session, public_base_url: str = "") -> list[StructuredTool]:
    memory = MemoryStore(db)
    vectors = VectorStore()

    # 列出最近上传的文件。
    # 这个工具给 Agent 了解“当前有哪些文件可用”，返回文件 ID、文件名、类型和内容预览。
    # query 参数暂时没有参与过滤，保留它是为了让工具签名更符合自然语言调用习惯。
    def list_uploaded_files(query: str = "", limit: int = 20) -> str:
        records = db.scalars(select(FileRecord).order_by(FileRecord.created_at.desc()).limit(limit)).all()
        return ok(
            {
                "files": [
                    {
                        "id": record.id,
                        "filename": record.filename,
                        "content_type": record.content_type,
                        "preview": record.extracted_text[:300],
                    }
                    for record in records
                ]
            }
        )

    # 按文件 ID 读取上传文件的抽取文本。
    # max_chars 用来限制返回长度，避免一次把很大的文件全部塞给模型。
    # 如果文件不存在，会返回统一格式的失败 JSON。
    def read_file(file_id: int, max_chars: int = 12000) -> str:
        record = db.get(FileRecord, file_id)
        if not record:
            return fail("file not found", file_id=file_id)
        return ok(
            {
                "file": {
                    "id": record.id,
                    "filename": record.filename,
                    "content_type": record.content_type,
                    "content": record.extracted_text[:max_chars],
                }
            }
        )

    # 在已上传文件的向量索引中搜索相关片段。
    # query 是搜索问题或关键词，limit 控制返回条数；
    # file_ids 不为空时只搜索指定文件，适合用户明确选择了文件的场景。
    def search_uploaded_files(query: str, limit: int = 5, file_ids: list[int] | None = None) -> str:
        results = vectors.search_documents(query, limit=limit, file_ids=file_ids or None)
        return ok({"matches": results})

    # 分析指定 Excel 文件的结构。
    # 先检查文件是否存在，再检查后缀是否是支持的 Excel 类型；
    # 通过后才调用 analyze_excel_file 返回工作表、表头、行列数和样例数据。
    def analyze_excel(file_id: int) -> str:
        record = db.get(FileRecord, file_id)
        if not record:
            return fail("file not found", file_id=file_id)
        suffix = Path(record.path).suffix.lower()
        if suffix not in {".xlsx", ".xlsm"}:
            return fail("file is not an Excel workbook", file_id=file_id, suffix=suffix)
        return ok({"file_id": file_id, "filename": record.filename, "analysis": analyze_excel_file(record.path)})

    def generate_excel_chart(
        file_id: int,
        chart_type: str,
        sheet_name: str | None = None,
        x_axis_column: str | None = None,
        y_columns: list[str] | None = None,
        title: str | None = None,
        max_rows: int = 50,
    ) -> str:
        record = db.get(FileRecord, file_id)
        if not record:
            return fail("file not found", file_id=file_id)
        suffix = Path(record.path).suffix.lower()
        if suffix not in {".xlsx", ".xlsm"}:
            return fail("file is not an Excel workbook", file_id=file_id, suffix=suffix)
        try:
            result = generate_excel_chart_image(
                record.path,
                chart_type=chart_type,
                sheet_name=sheet_name,
                x_axis_column=x_axis_column,
                y_columns=y_columns,
                title=title,
                max_rows=max_rows,
            )
        except Exception as exc:
            return fail(str(exc), file_id=file_id)

        artifact = TaskArtifact(kind="chart", file_id=record.id, path=str(result["path"]))
        db.add(artifact)
        db.commit()
        db.refresh(artifact)
        return _artifact_result(artifact, public_base_url, metadata=result.get("chart", {}))

    def list_pdf_tables(file_id: int) -> str:
        record = db.get(FileRecord, file_id)
        if not record:
            return fail("file not found", file_id=file_id)
        suffix = Path(record.path).suffix.lower()
        if suffix != ".pdf":
            return fail("file is not a PDF", file_id=file_id, suffix=suffix)
        tables = db.scalars(
            select(PdfTableRecord)
            .where(PdfTableRecord.file_id == file_id)
            .order_by(PdfTableRecord.page_number, PdfTableRecord.id)
        ).all()
        if not tables:
            return fail(
                "no structured PDF tables were found; do not invent table data",
                file_id=file_id,
                filename=record.filename,
            )
        return ok(
            {
                "file_id": file_id,
                "filename": record.filename,
                "tables": [
                    {
                        "id": table.id,
                        "label": table.label,
                        "caption": table.caption,
                        "page": table.page_number,
                        "extraction_method": table.extraction_method,
                        "confidence": table.confidence,
                    }
                    for table in tables
                ],
            }
        )

    def read_pdf_table(file_id: int, table_label: str) -> str:
        record = db.get(FileRecord, file_id)
        if not record:
            return fail("file not found", file_id=file_id)
        suffix = Path(record.path).suffix.lower()
        if suffix != ".pdf":
            return fail("file is not a PDF", file_id=file_id, suffix=suffix)
        tables = db.scalars(
            select(PdfTableRecord)
            .where(PdfTableRecord.file_id == file_id)
            .order_by(PdfTableRecord.page_number, PdfTableRecord.id)
        ).all()
        table_list = list(tables)
        target = _match_pdf_table(table_list, table_label)
        if not target:
            return fail(
                "requested PDF table was not found; do not invent table data",
                file_id=file_id,
                table_label=table_label,
                available_tables=[
                    {"label": table.label, "caption": table.caption, "page": table.page_number}
                    for table in table_list
                ],
            )
        return ok(
            {
                "file_id": file_id,
                "filename": record.filename,
                "table": {
                    "id": target.id,
                    "label": target.label,
                    "caption": target.caption,
                    "page": target.page_number,
                    "rows": json.loads(target.data_json),
                    "raw_text": target.raw_text,
                    "extraction_method": target.extraction_method,
                    "confidence": target.confidence,
                },
            }
        )

    # 搜索长期记忆。
    # Agent 可以用它查找用户偏好、身份信息、项目背景等之前保存过的内容。
    def search_memory(query: str, limit: int = 5) -> str:
        results = memory.search(query, limit=limit)
        return ok({"memories": [{"id": item.id, "content": item.content, "source": item.source} for item in results]})

    # 保存一条长期记忆。
    # Agent 只有在用户明确表达长期偏好、身份、项目背景等信息时才应调用它。
    def save_memory(content: str) -> str:
        record = memory.add(content, source="tool")
        return ok({"memory": {"id": record.id, "content": record.content}})

    # 生成 Word 报告并登记为 artifact。
    # 文件生成后会写入 TaskArtifact 表，这样前端可以通过 artifact ID 下载真实文件。
    def generate_word_report(title: str, content: str) -> str:
        path = generate_word(title, content)
        artifact = TaskArtifact(kind="word", path=str(path))
        db.add(artifact)
        db.commit()
        db.refresh(artifact)
        return _artifact_result(artifact, public_base_url)

    # 生成 Excel 表格并登记为 artifact。
    # content 会由 output_tools 解析成行列数据，生成的文件路径会保存到数据库。
    def generate_excel_table(
        filename: str,
        content: str,
        highlight_gt: float | None = None,
        highlight_lt: float | None = None,
        highlight_column: str | None = None,
        highlight_scope: str = "row",
    ) -> str:
        path = generate_excel(
            filename,
            content,
            highlight_gt=highlight_gt,
            highlight_lt=highlight_lt,
            highlight_column=highlight_column,
            highlight_scope=highlight_scope,
        )
        artifact = TaskArtifact(kind="excel", path=str(path))
        db.add(artifact)
        db.commit()
        db.refresh(artifact)
        return _artifact_result(artifact, public_base_url)

    def edit_uploaded_excel_cells(file_id: int, filename: str, updates: list[dict[str, Any]]) -> str:
        record = db.get(FileRecord, file_id)
        if not record:
            return fail("file not found", file_id=file_id)
        suffix = Path(record.path).suffix.lower()
        if suffix not in {".xlsx", ".xlsm"}:
            return fail("file is not an Excel workbook", file_id=file_id, suffix=suffix)
        try:
            normalized_updates = [
                update.model_dump() if isinstance(update, BaseModel) else update
                for update in updates
            ]
            path = edit_excel_cells(record.path, filename, normalized_updates)
        except Exception as exc:
            return fail(str(exc), file_id=file_id)
        artifact = TaskArtifact(kind="excel", file_id=record.id, path=str(path))
        db.add(artifact)
        db.commit()
        db.refresh(artifact)
        return _artifact_result(artifact, public_base_url)

    def read_excel_range(
        file_id: int,
        cell_range: str,
        sheet_name: str | None = None,
        data_only: bool = True,
        max_cells: int = 2000,
    ) -> str:
        record = _excel_record(db, file_id)
        if not record:
            return fail("Excel file not found", file_id=file_id)
        try:
            return ok(read_excel_range_data(record.path, cell_range, sheet_name, data_only, max_cells))
        except Exception as exc:
            return fail(str(exc), file_id=file_id)

    def calculate_excel_sum(
        file_id: int,
        sum_range: str,
        sheet_name: str | None = None,
        criteria_range: str | None = None,
        criteria: Any | None = None,
    ) -> str:
        record = _excel_record(db, file_id)
        if not record:
            return fail("Excel file not found", file_id=file_id)
        try:
            return ok(sum_excel_range(record.path, sum_range, sheet_name, criteria_range, criteria))
        except Exception as exc:
            return fail(str(exc), file_id=file_id)

    def lookup_excel(
        file_id: int,
        lookup_value: Any,
        lookup_range: str,
        result_range: str,
        sheet_name: str | None = None,
    ) -> str:
        record = _excel_record(db, file_id)
        if not record:
            return fail("Excel file not found", file_id=file_id)
        try:
            return ok(lookup_excel_value(record.path, lookup_value, lookup_range, result_range, sheet_name))
        except Exception as exc:
            return fail(str(exc), file_id=file_id)

    def filter_excel(
        file_id: int,
        data_range: str,
        column: str,
        operator: str,
        value: Any,
        sheet_name: str | None = None,
        limit: int = 200,
    ) -> str:
        record = _excel_record(db, file_id)
        if not record:
            return fail("Excel file not found", file_id=file_id)
        try:
            return ok(filter_excel_rows(record.path, data_range, column, operator, value, sheet_name, limit))
        except Exception as exc:
            return fail(str(exc), file_id=file_id)

    def write_uploaded_excel_range(
        file_id: int,
        filename: str,
        start_cell: str,
        values: list[list[Any]],
        sheet_name: str | None = None,
    ) -> str:
        record = _excel_record(db, file_id)
        if not record:
            return fail("Excel file not found", file_id=file_id)
        try:
            path = write_excel_range(record.path, filename, start_cell, values, sheet_name)
        except Exception as exc:
            return fail(str(exc), file_id=file_id)
        return _save_excel_artifact(db, record, path, public_base_url)

    def fill_uploaded_excel_formula(
        file_id: int,
        filename: str,
        cell_range: str,
        formula: str,
        sheet_name: str | None = None,
    ) -> str:
        record = _excel_record(db, file_id)
        if not record:
            return fail("Excel file not found", file_id=file_id)
        if not formula.strip().startswith("="):
            return fail("formula must start with =", file_id=file_id)
        try:
            path = fill_excel_formula(record.path, filename, cell_range, formula, sheet_name)
        except Exception as exc:
            return fail(str(exc), file_id=file_id)
        return _save_excel_artifact(db, record, path, public_base_url)

    def send_email(
        to: str,
        subject: str = "LongChain Office Agent",
        content: str = "",
        file_ids: list[int] | None = None,
    ) -> str:
        if not content.strip():
            return fail("email content is required")
        attachments = []
        for file_id in file_ids or []:
            record = db.get(FileRecord, file_id)
            if not record:
                return fail("attachment file not found", file_id=file_id)
            attachments.append(
                EmailAttachment(
                    path=Path(record.path),
                    filename=record.filename,
                    content_type=record.content_type,
                )
            )
        try:
            result = send_email_message(to=to, subject=subject, content=content, attachments=attachments)
        except EmailConfigurationError as exc:
            return fail(str(exc), to=to)
        except EmailSendError as exc:
            return fail(str(exc), to=to)
        return ok(
            {
                "email": {
                    "to": result["to"],
                    "subject": result["subject"],
                    "status": "sent",
                    "attachments": result["attachments"],
                }
            }
        )

    def fetch_unread_emails(limit: int = 5, body_max_chars: int = 4000, mark_read: bool = True) -> str:
        try:
            result = fetch_unread_email_messages(limit=limit, body_max_chars=body_max_chars, mark_read=mark_read)
        except EmailConfigurationError as exc:
            return fail(str(exc))
        except EmailReceiveError as exc:
            return fail(str(exc))
        return ok({"unread_emails": result})

    return [
        StructuredTool.from_function(
            name="list_uploaded_files",
            description="列出用户已经上传的办公文件，返回文件 ID、文件名和内容预览。",
            func=list_uploaded_files,
        ),
        StructuredTool.from_function(
            name="read_file",
            description="根据文件 ID 读取完整或部分文件文本内容。需要分析指定文件时先调用这个工具。",
            func=read_file,
            args_schema=ReadFileInput,
        ),
        StructuredTool.from_function(
            name="search_uploaded_files",
            description="从已上传文件的向量索引中检索与问题相关的内容片段。",
            func=search_uploaded_files,
            args_schema=SearchFilesInput,
        ),
        StructuredTool.from_function(
            name="analyze_excel",
            description="分析 Excel 文件结构，返回工作表、表头、行数、列数和样例行。",
            func=analyze_excel,
            args_schema=AnalyzeExcelInput,
        ),
        StructuredTool.from_function(
            name="generate_excel_chart",
            description="根据已上传的 Excel 工作簿生成可视化图表图片，并返回图表 artifact，前端会把该图片直接展示在对话窗口。用户要求生成折线图、柱状图、趋势图，或要求把选中的 Excel 数据可视化时必须使用。若用户本轮只选择了一个 Excel 文件，直接使用该 file_id。chart_type 只能是 line 或 bar。不要回答不支持生成图表，也不要让用户改为本地绘图。",
            func=generate_excel_chart,
            args_schema=GenerateExcelChartInput,
        ),
        StructuredTool.from_function(
            name="read_excel_range",
            description="Read an exact Excel range such as A1:F20. Use analyze_excel first when the used range is unknown. Always pass both start and end rows and columns; do not pass only A:F or 1:20.",
            func=read_excel_range,
            args_schema=ReadExcelRangeInput,
        ),
        StructuredTool.from_function(
            name="calculate_excel_sum",
            description="Calculate a numeric Excel range sum, optionally restricted by an aligned criteria range and criteria value.",
            func=calculate_excel_sum,
            args_schema=SumExcelRangeInput,
        ),
        StructuredTool.from_function(
            name="lookup_excel",
            description="Find a value in one Excel range and return the aligned value from another range. Use this for exact lookup tasks.",
            func=lookup_excel,
            args_schema=LookupExcelValueInput,
        ),
        StructuredTool.from_function(
            name="filter_excel",
            description="Filter tabular Excel rows by a column and operator. The data range must include a header row.",
            func=filter_excel,
            args_schema=FilterExcelRowsInput,
        ),
        StructuredTool.from_function(
            name="write_uploaded_excel_range",
            description="Copy an uploaded Excel workbook, write a rectangular matrix starting at one cell, and return an Excel artifact. Prefer this for contiguous output regions.",
            func=write_uploaded_excel_range,
            args_schema=WriteExcelRangeInput,
        ),
        StructuredTool.from_function(
            name="fill_uploaded_excel_formula",
            description="Copy an uploaded Excel workbook, translate and fill an Excel formula across a range, recalculate cached values, and return an Excel artifact.",
            func=fill_uploaded_excel_formula,
            args_schema=FillExcelFormulaInput,
        ),
        StructuredTool.from_function(
            name="list_pdf_tables",
            description="列出指定 PDF 中已结构化抽取到的表格编号、标题、页码和置信度。用户询问 PDF 表格数据时应先调用。",
            func=list_pdf_tables,
            args_schema=ListPdfTablesInput,
        ),
        StructuredTool.from_function(
            name="read_pdf_table",
            description="按表格编号精确读取 PDF 表格的结构化行列数据。若找不到表格，必须说明未定位到，不能编造数据。",
            func=read_pdf_table,
            args_schema=ReadPdfTableInput,
        ),
        StructuredTool.from_function(
            name="search_memory",
            description="检索用户长期记忆，例如用户偏好、项目背景、常用输出格式。",
            func=search_memory,
            args_schema=SearchInput,
        ),
        StructuredTool.from_function(
            name="save_memory",
            description="保存长期记忆。只有用户偏好、身份信息、项目背景等长期有效事实才需要保存。",
            func=save_memory,
            args_schema=SaveMemoryInput,
        ),
        StructuredTool.from_function(
            name="generate_word_report",
            description="生成 Word 报告，并返回真实下载链接。需要交付 Word 文件时必须调用这个工具。",
            func=generate_word_report,
            args_schema=GenerateWordInput,
        ),
        StructuredTool.from_function(
            name="generate_excel_table",
            description="生成 Excel 表格，并返回真实下载链接。可用 highlight_gt 标红大于阈值的数据，highlight_lt 标红小于阈值的数据；用户指定列名时必须设置 highlight_column，例如 销售额。",
            func=generate_excel_table,
            args_schema=GenerateExcelInput,
        ),
        StructuredTool.from_function(
            name="edit_uploaded_excel_cells",
            description=(
                "复制已上传的 Excel 工作簿并修改指定单元格，返回新的 Excel artifact。"
                "用户要求补公式、修复单元格、批量填充结果或修改现有工作簿时使用。"
                "updates 必须逐项给出 cell、value；需要指定工作表时传 sheet_name。"
            ),
            func=edit_uploaded_excel_cells,
            args_schema=EditExcelCellsInput,
        ),
        StructuredTool.from_function(
            name="send_email",
            description=(
                "发送电子邮件。用户明确要求给某个邮箱发送邮件时必须调用此工具。"
                "to 是收件人邮箱，subject 是主题，content 是正文。"
                "如果用户本轮选中了文件，并要求发送邮件，把这些文件 ID 放入 file_ids 作为附件发送。"
                "只有工具返回 ok=true 后，才能告诉用户邮件已发送。"
            ),
            func=send_email,
            args_schema=SendEmailInput,
        ),
        StructuredTool.from_function(
            name="fetch_unread_emails",
            description=(
                "拉取邮箱收件箱中的未读邮件。用户说收邮件、查看未读邮件、帮我读一下邮件时必须调用。"
                "返回发件人、收件人、主题、日期、正文内容，以及文本附件的内容预览。"
                "默认会在成功拉取后把这些邮件标记为已读，避免下次重复拉取。"
                "只有工具返回 ok=true 后，才能把邮件内容总结或展示给用户。"
            ),
            func=fetch_unread_emails,
            args_schema=FetchUnreadEmailsInput,
        ),
    ]


# 把数据库中的 artifact 记录转换成工具返回给 Agent 的 JSON 字符串。
# 同时提供相对下载地址和绝对下载地址；
# 如果 public_base_url 为空，就只返回相对路径。
def _excel_record(db: Session, file_id: int) -> FileRecord | None:
    record = db.get(FileRecord, file_id)
    if not record or Path(record.path).suffix.lower() not in {".xlsx", ".xlsm"}:
        return None
    return record


def _save_excel_artifact(db: Session, record: FileRecord, path: Path, public_base_url: str) -> str:
    artifact = TaskArtifact(kind="excel", file_id=record.id, path=str(path))
    db.add(artifact)
    db.commit()
    db.refresh(artifact)
    return _artifact_result(artifact, public_base_url)


def _artifact_result(artifact: TaskArtifact, public_base_url: str, metadata: dict | None = None) -> str:
    download_url = f"/api/files/artifacts/{artifact.id}/download"
    absolute_url = f"{public_base_url.rstrip('/')}{download_url}" if public_base_url else download_url
    payload = {
        "artifact": {
            "id": artifact.id,
            "kind": artifact.kind,
            "path": artifact.path,
            "download_url": download_url,
            "absolute_download_url": absolute_url,
        }
    }
    if metadata:
        payload["artifact"]["metadata"] = metadata
    return ok(payload)


def _match_pdf_table(tables: list[PdfTableRecord], table_label: str) -> PdfTableRecord | None:
    wanted = _normalize_pdf_table_label(table_label)
    for table in tables:
        if _normalize_pdf_table_label(table.label) == wanted:
            return table
    for table in tables:
        if wanted and wanted in _normalize_pdf_table_label(table.caption):
            return table
    return None


def _normalize_pdf_table_label(value: str) -> str:
    normalized = re.sub(r"\s+", " ", value.strip().lower())
    normalized = normalized.replace("table", "table ").replace("表格", "表 ").replace("表", "表 ")
    normalized = re.sub(r"\s+", " ", normalized)
    match = re.search(r"(table|表)\s*([0-9]+|[ivxlcdm]+)", normalized)
    if not match:
        return normalized
    return f"{match.group(1)} {match.group(2).upper()}"
