from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.database import Base
from app.db.models import MemoryRecord
from app.memory.store import MemoryStore
from app.memory.vector_store import VectorStore


def test_memory_store_add_and_search(tmp_path) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        store = MemoryStore(db, vector_store=VectorStore(tmp_path / "memory-chroma"))
        store.add("user preference: weekly report table format")
        results = store.search("weekly report table")
        assert len(results) == 1
        assert "weekly report" in results[0].content


def test_vector_store_indexes_document_chunks(tmp_path) -> None:
    store = VectorStore(tmp_path / "chroma")
    store.upsert_document_chunks(1, "demo.txt", ["sales amount increased", "meeting notes"])
    results = store.search_documents("sales amount")
    assert results
    assert results[0]["file_id"] == 1


def test_vector_store_can_filter_document_chunks_by_file_id(tmp_path) -> None:
    store = VectorStore(tmp_path / "filtered-chroma")
    store.upsert_document_chunks(1, "first.txt", ["project name: first file"])
    store.upsert_document_chunks(2, "second.txt", ["project name: second file"])

    results = store.search_documents("project name", file_ids=[2])

    assert results
    assert all(item["file_id"] == 2 for item in results)


def test_vector_store_can_delete_document_chunks(tmp_path) -> None:
    store = VectorStore(tmp_path / "delete-chroma")
    store.upsert_document_chunks(1, "first.txt", ["project name: first file"])
    store.delete_document_chunks(1)

    results = store.search_documents("first file")

    assert results == []


def test_memory_store_delete_removes_db_record_and_vector(tmp_path) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    vector_store = VectorStore(tmp_path / "delete-memory-chroma")

    with Session(engine) as db:
        store = MemoryStore(db, vector_store=vector_store)
        record = store.add("user preference: generate report")
        memory_id = record.id

        store.delete(memory_id)

        assert db.get(MemoryRecord, memory_id) is None
        assert vector_store.search_memories("generate report") == []
