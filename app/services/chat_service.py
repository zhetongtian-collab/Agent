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
    # 初始化聊天服务。
    # 每个 ChatService 绑定一个数据库会话，并创建记忆管理器和向量检索器，
    # 后续处理聊天时会用它们查长期记忆、查文档片段和保存新记忆。
    def __init__(self, db: Session):
        self.db = db
        self.memory = MemoryStore(db)
        self.vectors = VectorStore()

    # 处理一次普通非流式聊天请求。
    # 流程是：构建上下文 -> 创建千问模型 -> 构建办公工具 -> 运行 Agent。
    # Agent 返回后，把答案、用到的文件、命中的记忆和生成的 artifact 一起封装给前端。
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

    # 处理一次流式聊天请求。
    # 这个函数本身是生成器，会一边接收 Agent 的 token/artifact/done 事件，
    # 一边把事件继续 yield 给 API 层；最后如果有完整答案，会尝试更新长期记忆。
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

    # 为当前聊天请求准备 Agent 需要的所有上下文。
    # 包括用户本轮选择的文件、和问题相关的长期记忆、
    # 以及从文档向量库里检索到的相关片段。
    # 返回的是一个字典，里面包含消息列表、运行时上下文和记忆文本。
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

    # 根据前端传来的 file_ids 读取文件记录。
    # 如果用户没有选择文件，就返回空列表；
    # 如果选择了文件，就从数据库中取出这些 FileRecord 供 Agent 上下文使用。
    def _load_file_context(self, file_ids: list[int]) -> list[FileRecord]:
        if not file_ids:
            return []
        return list(self.db.scalars(select(FileRecord).where(FileRecord.id.in_(file_ids))).all())
