import json
from pathlib import Path

from openpyxl import Workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.database import Base
from app.db.models import FileRecord, PdfTableRecord
from app.tools import output_tools
from app.tools.office_tools import build_office_tools


def _tool_by_name(tools, name):
    return next(tool for tool in tools if tool.name == name)


def test_office_tools_read_file_and_generate_word(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(output_tools.settings, "artifact_dir", tmp_path)
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        record = FileRecord(filename="demo.txt", path="demo.txt", extracted_text="项目背景：智能办公")
        db.add(record)
        db.commit()
        db.refresh(record)

        tools = build_office_tools(db, public_base_url="http://localhost:8000")
        read_result = json.loads(_tool_by_name(tools, "read_file").invoke({"file_id": record.id}))
        assert read_result["ok"] is True
        assert "智能办公" in read_result["file"]["content"]

        word_result = json.loads(
            _tool_by_name(tools, "generate_word_report").invoke({"title": "报告", "content": "正文"})
        )
        assert word_result["ok"] is True
        assert word_result["artifact"]["download_url"].startswith("/api/files/artifacts/")


def test_analyze_excel_tool(tmp_path: Path) -> None:
    xlsx = tmp_path / "sales.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "销售"
    sheet.append(["区域", "销售额"])
    sheet.append(["华东", 100])
    workbook.save(xlsx)

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        record = FileRecord(filename="sales.xlsx", path=str(xlsx), extracted_text="区域 | 销售额")
        db.add(record)
        db.commit()
        db.refresh(record)

        result = json.loads(_tool_by_name(build_office_tools(db), "analyze_excel").invoke({"file_id": record.id}))

    assert result["ok"] is True
    assert result["analysis"]["sheets"][0]["sheet_name"] == "销售"
    assert result["analysis"]["sheets"][0]["headers"] == ["区域", "销售额"]


def test_pdf_table_tools_return_structured_table() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        record = FileRecord(filename="paper.pdf", path="paper.pdf", extracted_text="[page=5]\nTable 1")
        db.add(record)
        db.commit()
        db.refresh(record)
        db.add(
            PdfTableRecord(
                file_id=record.id,
                label="Table 1",
                caption="Table 1: Main results",
                page_number=5,
                data_json=json.dumps([["Model", "Score"], ["Ours", "0.91"]]),
                raw_text="Model | Score\nOurs | 0.91",
                extraction_method="test",
                confidence=1.0,
            )
        )
        db.commit()

        tools = build_office_tools(db)
        list_result = json.loads(_tool_by_name(tools, "list_pdf_tables").invoke({"file_id": record.id}))
        read_result = json.loads(
            _tool_by_name(tools, "read_pdf_table").invoke({"file_id": record.id, "table_label": "Table 1"})
        )
        missing_result = json.loads(
            _tool_by_name(tools, "read_pdf_table").invoke({"file_id": record.id, "table_label": "Table 2"})
        )

    assert list_result["ok"] is True
    assert list_result["tables"][0]["page"] == 5
    assert read_result["ok"] is True
    assert read_result["table"]["rows"][1] == ["Ours", "0.91"]
    assert missing_result["ok"] is False
    assert "available_tables" in missing_result
