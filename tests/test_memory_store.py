from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.database import Base
from app.memory.store import MemoryStore
from app.memory.vector_store import VectorStore


def test_memory_store_add_and_search(tmp_path) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        store = MemoryStore(db, vector_store=VectorStore(tmp_path / "memory-chroma"))
        store.add("用户偏好：周报使用表格格式")
        results = store.search("周报 表格")
        assert len(results) == 1
        assert "周报" in results[0].content


def test_vector_store_indexes_document_chunks(tmp_path) -> None:
    store = VectorStore(tmp_path / "chroma")
    store.upsert_document_chunks(1, "demo.txt", ["销售额增长明显", "会议纪要"])
    results = store.search_documents("销售额")
    assert results
    assert results[0]["file_id"] == 1


def test_vector_store_can_filter_document_chunks_by_file_id(tmp_path) -> None:
    store = VectorStore(tmp_path / "filtered-chroma")
    store.upsert_document_chunks(1, "first.txt", ["项目名称：第一个文件"])
    store.upsert_document_chunks(2, "second.txt", ["项目名称：第二个文件"])

    results = store.search_documents("项目名称", file_ids=[2])

    assert results
    assert all(item["file_id"] == 2 for item in results)
