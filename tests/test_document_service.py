from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.database import Base
from app.db.models import FileRecord
from app.services import document_service
from app.services.document_service import DocumentService


class FakeVectorStore:
    deleted_file_id: int | None = None

    def delete_document_chunks(self, file_id: int) -> None:
        self.deleted_file_id = file_id
        FakeVectorStore.deleted_file_id = file_id


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
