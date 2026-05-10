from sqlalchemy import select
from sqlalchemy.orm import Session

from collections.abc import Iterator
from typing import Any

from app.agents.executor import build_agent_messages, build_runtime_context, run_office_agent, stream_office_agent
from app.core.qwen_llm import get_qwen_chat_model
from app.db.models import FileRecord
from app.memory.store import MemoryStore
from app.memory.vector_store import VectorStore
from app.schemas.chat import ChatRequest, ChatResponse
from app.tools.office_tools import build_office_tools


class ChatService:
    def __init__(self, db: Session):
        self.db = db
        self.memory = MemoryStore(db)
        self.vectors = VectorStore()

    def handle_chat(self, request: ChatRequest) -> ChatResponse:
        context = self._build_context(request)
        llm = get_qwen_chat_model()
        result = run_office_agent(
            model=llm,
            tools=build_office_tools(self.db, public_base_url="http://localhost:8000"),
            messages=context["messages"],
            session_id=request.session_id,
            runtime_context=context["runtime_context"],
        )
        answer = str(result["answer"])

        self.memory.maybe_update_from_conversation(request.message, answer)

        return ChatResponse(
            answer=answer,
            session_id=request.session_id,
            used_file_ids=request.file_ids,
            memories=context["memory_contents"],
            artifacts=result.get("artifacts", []),
        )

    def stream_chat(self, request: ChatRequest) -> Iterator[dict[str, Any]]:
        context = self._build_context(request)
        llm = get_qwen_chat_model()
        answer = ""
        artifacts: list[dict[str, Any]] = []

        try:
            for event in stream_office_agent(
                model=llm,
                tools=build_office_tools(self.db, public_base_url="http://localhost:8000"),
                messages=context["messages"],
                session_id=request.session_id,
                runtime_context=context["runtime_context"],
            ):
                if event["type"] == "token":
                    answer += str(event["content"])
                elif event["type"] == "artifact":
                    artifact = event["artifact"]
                    if artifact not in artifacts:
                        artifacts.append(artifact)
                elif event["type"] == "done":
                    answer = str(event.get("answer") or answer)
                    for artifact in event.get("artifacts", []):
                        if artifact not in artifacts:
                            artifacts.append(artifact)
                yield event
        finally:
            if answer.strip():
                self.memory.maybe_update_from_conversation(request.message, answer)

    def _build_context(self, request: ChatRequest) -> dict[str, Any]:
        file_context = self._load_file_context(request.file_ids)
        memories = self.memory.search(request.message, limit=5)
        retrieved_documents = self.vectors.search_documents(request.message, limit=5, file_ids=request.file_ids)
        memory_contents = [item.content for item in memories]
        return {
            "memory_contents": memory_contents,
            "messages": build_agent_messages(user_message=request.message),
            "runtime_context": build_runtime_context(
                memories=memory_contents,
                selected_files=file_context,
                retrieved_documents=retrieved_documents,
            ),
        }

    def _load_file_context(self, file_ids: list[int]) -> list[FileRecord]:
        if not file_ids:
            return []
        return list(self.db.scalars(select(FileRecord).where(FileRecord.id.in_(file_ids))).all())
