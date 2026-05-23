from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.database import Base
from app.db.models import FileRecord
from app.schemas.chat import ChatRequest
from app.services.chat_service import ChatService


def test_chat_service_uses_file_context(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    def fake_run_office_agent(model, tools, messages, session_id, runtime_context=None):
        assert messages[0].content == "summarize file"
        assert session_id == "default"
        assert "quarterly report" in runtime_context["extra_context"]
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
        lambda model, tools, messages, session_id, runtime_context=None: {"answer": "ok", "artifacts": []},
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


def test_chat_service_stream_uses_session_checkpoint_context(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    captured = {}

    class FakeVectorStore:
        def search_documents(self, query, limit=5, file_ids=None):
            return []

    def fake_stream_office_agent(model, tools, messages, session_id, runtime_context=None):
        captured["message"] = messages[0].content
        captured["session_id"] = session_id
        captured["runtime_context"] = runtime_context
        yield {"type": "token", "content": "hello"}
        yield {"type": "token", "content": " world"}
        yield {"type": "done", "answer": "hello world", "artifacts": []}

    monkeypatch.setattr("app.services.chat_service.get_qwen_chat_model", lambda: SimpleNamespace())
    monkeypatch.setattr("app.services.chat_service.stream_office_agent", fake_stream_office_agent)
    monkeypatch.setattr("app.services.chat_service.VectorStore", FakeVectorStore)

    with Session(engine) as db:
        events = list(ChatService(db).stream_chat(ChatRequest(message="hi", session_id="thread-1")))

    assert events[-1]["type"] == "done"
    assert captured["message"] == "hi"
    assert captured["session_id"] == "thread-1"
    assert captured["runtime_context"]["extra_context"] == ""


def test_chat_service_passes_distinct_session_ids_to_agent(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    captured_session_ids = []

    class FakeVectorStore:
        def search_documents(self, query, limit=5, file_ids=None):
            return []

    def fake_run_office_agent(model, tools, messages, session_id, runtime_context=None):
        captured_session_ids.append(session_id)
        return {"answer": f"answer for {session_id}", "artifacts": []}

    monkeypatch.setattr("app.services.chat_service.get_qwen_chat_model", lambda: SimpleNamespace())
    monkeypatch.setattr("app.services.chat_service.run_office_agent", fake_run_office_agent)
    monkeypatch.setattr("app.services.chat_service.VectorStore", FakeVectorStore)

    with Session(engine) as db:
        service = ChatService(db)
        first = service.handle_chat(ChatRequest(message="hello", session_id="conversation-a"))
        second = service.handle_chat(ChatRequest(message="hello", session_id="conversation-b"))

    assert captured_session_ids == ["conversation-a", "conversation-b"]
    assert first.session_id == "conversation-a"
    assert second.session_id == "conversation-b"
