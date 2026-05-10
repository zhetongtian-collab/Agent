import json
from collections.abc import Iterator
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import wrap_model_call
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import InMemorySaver

from app.db.models import FileRecord


AGENT_SYSTEM_PROMPT = """你是一个可以自主调用工具的智能办公 Agent。
你可以处理 Word、Excel、PDF、TXT、CSV 等办公文件。
工作规则：
1. 需要了解已上传文件时，先调用 list_uploaded_files。
2. 需要读取指定文件内容时，调用 read_file。
3. 需要从历史上传文件中查找内容时，调用 search_uploaded_files。
4. 需要分析 Excel 表结构时，调用 analyze_excel。
5. 需要生成 Word 文件时，必须调用 generate_word_report，不要假装已经生成。
6. 需要生成 Excel 文件时，必须调用 generate_excel_table，不要假装已经生成。
7. 发现用户明确要求保存长期偏好、身份、项目背景时，调用 save_memory。
8. 工具返回 download_url 时，最终回答必须把下载链接告诉用户。
9. 不要编造文件中不存在的数据。信息不足时说明缺口，并提出下一步。"""


CHECKPOINTER = InMemorySaver()


@wrap_model_call
def inject_runtime_context(request: Any, handler: Any) -> Any:
    context = getattr(request.runtime, "context", None) or {}
    extra_context = str(context.get("extra_context") or "").strip()
    if extra_context:
        request = request.override(messages=_inject_context_message(request.messages, extra_context))
    return handler(request)


def run_office_agent(
    model: Any,
    tools: list[BaseTool],
    messages: list[BaseMessage],
    session_id: str,
    runtime_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    agent = create_agent(
        model=model,
        tools=tools,
        system_prompt=AGENT_SYSTEM_PROMPT,
        middleware=[inject_runtime_context],
        checkpointer=CHECKPOINTER,
    )
    result = agent.invoke(
        {"messages": messages},
        config={"configurable": {"thread_id": session_id}},
        context=runtime_context or {},
    )
    output_messages = result.get("messages", []) if isinstance(result, dict) else []
    answer = _last_ai_text(output_messages)
    artifacts = _extract_artifacts(output_messages)
    return {"answer": answer, "artifacts": artifacts, "messages": output_messages}


def stream_office_agent(
    model: Any,
    tools: list[BaseTool],
    messages: list[BaseMessage],
    session_id: str,
    runtime_context: dict[str, Any] | None = None,
) -> Iterator[dict[str, Any]]:
    agent = create_agent(
        model=model,
        tools=tools,
        system_prompt=AGENT_SYSTEM_PROMPT,
        middleware=[inject_runtime_context],
        checkpointer=CHECKPOINTER,
    )
    collected_messages: list[BaseMessage] = []
    answer_parts: list[str] = []

    for event in agent.stream(
        {"messages": messages},
        config={"configurable": {"thread_id": session_id}},
        context=runtime_context or {},
        stream_mode=["messages", "updates"],
    ):
        mode, payload = _normalize_stream_event(event)
        if mode == "messages":
            message = _message_from_payload(payload)
            if message is None:
                continue
            if isinstance(message, AIMessageChunk):
                token = _content_to_text(message.content)
                if token:
                    answer_parts.append(token)
                    yield {"type": "token", "content": token}
            elif isinstance(message, ToolMessage):
                collected_messages.append(message)
                artifact = _extract_artifact_from_text(_content_to_text(message.content))
                if artifact:
                    yield {"type": "artifact", "artifact": artifact}
            elif isinstance(message, BaseMessage):
                collected_messages.append(message)
        elif mode == "updates":
            collected_messages.extend(_messages_from_update(payload))

    artifacts = _extract_artifacts(collected_messages)
    answer = "".join(answer_parts).strip() or _last_ai_text(collected_messages)
    yield {"type": "done", "answer": answer, "artifacts": artifacts}


def build_agent_messages(user_message: str) -> list[BaseMessage]:
    return [HumanMessage(content=user_message)]


def build_runtime_context(
    memories: list[str],
    selected_files: list[FileRecord],
    retrieved_documents: list[dict],
) -> dict[str, str]:
    return {"extra_context": _build_context(memories, selected_files, retrieved_documents)}


def _build_context(memories: list[str], selected_files: list[FileRecord], retrieved_documents: list[dict]) -> str:
    parts = []
    if memories:
        parts.append("相关长期记忆：\n" + "\n".join(f"- {item}" for item in memories))
    if selected_files:
        chunks = ["用户本次选择的文件："]
        for file in selected_files:
            chunks.append(f"文件ID {file.id}，文件名：{file.filename}\n内容预览：{file.extracted_text[:4000]}")
        parts.append("\n\n".join(chunks))
    if retrieved_documents:
        chunks = ["从已上传文件中检索到的相关片段："]
        for item in retrieved_documents:
            chunks.append(f"文件ID {item.get('file_id')}，文件名：{item.get('filename')}\n{item.get('content', '')[:1200]}")
        parts.append("\n\n".join(chunks))
    return "\n\n".join(parts)


def _inject_context_message(messages: list[BaseMessage], extra_context: str) -> list[BaseMessage]:
    for index in range(len(messages) - 1, -1, -1):
        if isinstance(messages[index], HumanMessage):
            original = _content_to_text(messages[index].content)
            current_message = HumanMessage(
                content=f"本轮临时上下文：\n{extra_context}\n\n用户当前任务：\n{original}"
            )
            return [*messages[:index], current_message, *messages[index + 1 :]]
    return [HumanMessage(content=f"本轮临时上下文：\n{extra_context}"), *messages]


def _last_ai_text(messages: list[BaseMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, AIMessage) and message.content:
            return _content_to_text(message.content)
    return ""


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
            else:
                parts.append(str(item))
        return "\n".join(parts)
    return str(content)


def _extract_artifacts(messages: list[BaseMessage]) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for message in messages:
        text = _content_to_text(getattr(message, "content", ""))
        artifact = _extract_artifact_from_text(text)
        if artifact and artifact not in artifacts:
            artifacts.append(artifact)
    return artifacts


def _extract_artifact_from_text(text: str) -> dict[str, Any] | None:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(data, dict) and isinstance(data.get("artifact"), dict):
        return data["artifact"]
    return None


def _normalize_stream_event(event: Any) -> tuple[str, Any]:
    if isinstance(event, tuple) and len(event) == 2:
        first, second = event
        if first in {"messages", "updates"}:
            return str(first), second
        if isinstance(first, BaseMessage):
            return "messages", first
    if isinstance(event, dict):
        return "updates", event
    return "unknown", event


def _message_from_payload(payload: Any) -> BaseMessage | None:
    if isinstance(payload, tuple) and payload:
        candidate = payload[0]
        return candidate if isinstance(candidate, BaseMessage) else None
    return payload if isinstance(payload, BaseMessage) else None


def _messages_from_update(payload: Any) -> list[BaseMessage]:
    messages: list[BaseMessage] = []
    if not isinstance(payload, dict):
        return messages
    for value in payload.values():
        if isinstance(value, dict) and isinstance(value.get("messages"), list):
            messages.extend(item for item in value["messages"] if isinstance(item, BaseMessage))
        elif isinstance(value, list):
            messages.extend(item for item in value if isinstance(item, BaseMessage))
    return messages
