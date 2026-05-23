from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import Base
from app.db.models import FileRecord, PdfTableRecord
from app.services import document_service
from app.services.document_service import DocumentService
from app.tools.file_reader import PdfTable


class FakeVectorStore:
    deleted_file_id: int | None = None
    segments: list[dict] = []

    def upsert_document_segments(self, file_id: int, filename: str, segments: list[dict]) -> None:
        FakeVectorStore.segments = segments

    def delete_document_chunks(self, file_id: int) -> None:
        self.deleted_file_id = file_id
        FakeVectorStore.deleted_file_id = file_id


class FakeUpload:
    filename = "paper.pdf"
    content_type = "application/pdf"

    async def read(self) -> bytes:
        return b"%PDF-1.4 fake"


def test_delete_file_removes_db_record_and_local_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(document_service, "VectorStore", FakeVectorStore)
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    file_path = tmp_path / "upload.txt"
    file_path.write_text("demo", encoding="utf-8")

    with Session(engine) as db:
        record = FileRecord(filename="upload.txt", path=str(file_path), extracted_text="demo")
        db.add(record)
        db.commit()
        db.refresh(record)
        file_id = record.id

        DocumentService(db).delete_file(file_id)

        assert db.get(FileRecord, file_id) is None

    assert not file_path.exists()
    assert FakeVectorStore.deleted_file_id == file_id


@pytest.mark.anyio
async def test_save_upload_extracts_pdf_tables(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(document_service.settings, "upload_dir", tmp_path)
    monkeypatch.setattr(document_service, "VectorStore", FakeVectorStore)
    monkeypatch.setattr(document_service, "extract_text", lambda path: "[page=2]\nTable 1: Results")
    monkeypatch.setattr(
        document_service,
        "extract_pdf_tables",
        lambda path: [
            PdfTable(
                label="Table 1",
                caption="Table 1: Results",
                page_number=2,
                rows=[["Model", "Score"], ["Ours", "0.91"]],
                raw_text="Model | Score\nOurs | 0.91",
                extraction_method="test",
                confidence=1.0,
            )
        ],
    )
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        record = await DocumentService(db).save_upload(FakeUpload())
        table = db.scalar(select(PdfTableRecord).where(PdfTableRecord.file_id == record.id))

    assert table is not None
    assert table.label == "Table 1"
    assert table.page_number == 2
    assert '"Ours"' in table.data_json
    assert FakeVectorStore.segments[0]["page"] == 2
