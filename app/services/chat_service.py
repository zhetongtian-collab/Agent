from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.office_agent import build_office_messages
from app.core.qwen_llm import get_qwen_chat_model
from app.db.models import ChatMessage, FileRecord
from app.memory.store import MemoryStore
from app.memory.vector_store import VectorStore
from app.schemas.chat import ChatRequest, ChatResponse


class ChatService:
    def __init__(self, db: Session):
        self.db = db
        self.memory = MemoryStore(db)
        self.vectors = VectorStore()

    def handle_chat(self, request: ChatRequest) -> ChatResponse:
        file_context = self._load_file_context(request.file_ids)
        memories = self.memory.search(request.message, limit=5)
        retrieved_documents = self.vectors.search_documents(request.message, limit=5)
        history = self._load_history(request.session_id, limit=8)

        llm = get_qwen_chat_model()
        result = llm.invoke(
            build_office_messages(
                user_message=request.message,
                memories=[item.content for item in memories],
                selected_files=file_context,
                retrieved_documents=retrieved_documents,
                history=history,
            )
        )
        answer = str(result.content)

        self._save_message(request.session_id, "user", request.message)
        self._save_message(request.session_id, "assistant", answer)
        self.memory.maybe_update_from_conversation(request.message, answer)

        return ChatResponse(
            answer=answer,
            session_id=request.session_id,
            used_file_ids=request.file_ids,
            memories=[item.content for item in memories],
        )

    def _load_file_context(self, file_ids: list[int]) -> list[FileRecord]:
        if not file_ids:
            return []
        return list(self.db.scalars(select(FileRecord).where(FileRecord.id.in_(file_ids))).all())

    def _load_history(self, session_id: str, limit: int) -> list[ChatMessage]:
        rows = self.db.scalars(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(limit)
        ).all()
        return list(reversed(rows))

    def _save_message(self, session_id: str, role: str, content: str) -> None:
        self.db.add(ChatMessage(session_id=session_id, role=role, content=content))
        self.db.commit()
