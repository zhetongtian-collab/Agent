from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.database import Base
from app.db.models import ChatMessage, FileRecord
from app.schemas.chat import ChatRequest
from app.services.chat_service import ChatService


def test_chat_service_uses_file_context(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    def fake_run_office_agent(model, tools, messages):
        content = "\n".join(message.content for message in messages)
        assert "quarterly report" in content
        return {"answer": "analyzed from file", "artifacts": []}

    monkeypatch.setattr("app.services.chat_service.get_qwen_chat_model", lambda: SimpleNamespace())
    monkeypatch.setattr("app.services.chat_service.run_office_agent", fake_run_office_agent)

    with Session(engine) as db:
        record = FileRecord(filename="report.txt", path="report.txt", extracted_text="quarterly report: revenue up")
        db.add(record)
        db.commit()
        db.refresh(record)
        record_id = record.id

        response = ChatService(db).handle_chat(ChatRequest(message="summarize file", file_ids=[record_id]))

    assert response.answer == "analyzed from file"
    assert response.used_file_ids == [record_id]


def test_chat_service_limits_vector_search_to_selected_files(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    captured = {}

    class FakeVectorStore:
        def search_documents(self, query, limit=5, file_ids=None):
            captured["file_ids"] = file_ids
            return []

    monkeypatch.setattr("app.services.chat_service.get_qwen_chat_model", lambda: SimpleNamespace())
    monkeypatch.setattr(
        "app.services.chat_service.run_office_agent",
        lambda model, tools, messages: {"answer": "ok", "artifacts": []},
    )
    monkeypatch.setattr("app.services.chat_service.VectorStore", FakeVectorStore)

    with Session(engine) as db:
        first = FileRecord(filename="first.txt", path="first.txt", extracted_text="first file")
        second = FileRecord(filename="second.txt", path="second.txt", extracted_text="second file")
        db.add_all([first, second])
        db.commit()
        db.refresh(second)
        second_id = second.id

        ChatService(db).handle_chat(ChatRequest(message="summarize", file_ids=[second_id]))

    assert captured["file_ids"] == [second_id]


def test_chat_service_stream_saves_final_answer(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    def fake_stream_office_agent(model, tools, messages):
        yield {"type": "token", "content": "hello"}
        yield {"type": "token", "content": " world"}
        yield {"type": "done", "answer": "hello world", "artifacts": []}

    monkeypatch.setattr("app.services.chat_service.get_qwen_chat_model", lambda: SimpleNamespace())
    monkeypatch.setattr("app.services.chat_service.stream_office_agent", fake_stream_office_agent)

    with Session(engine) as db:
        events = list(ChatService(db).stream_chat(ChatRequest(message="hi")))
        saved = db.query(ChatMessage).all()

    assert events[-1]["type"] == "done"
    assert [item.content for item in saved] == ["hi", "hello world"]
