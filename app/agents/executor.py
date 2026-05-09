import json
from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.tools import BaseTool

from app.db.models import ChatMessage, FileRecord


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
9. 不要编造文件中不存在的数据。信息不足时说明缺口，并提出下一步。
"""


def run_office_agent(model: Any, tools: list[BaseTool], messages: list[BaseMessage]) -> dict[str, Any]:
    agent = create_agent(model=model, tools=tools, system_prompt=AGENT_SYSTEM_PROMPT)
    result = agent.invoke({"messages": messages})
    output_messages = result.get("messages", []) if isinstance(result, dict) else []
    answer = _last_ai_text(output_messages)
    artifacts = _extract_artifacts(output_messages)
    return {"answer": answer, "artifacts": artifacts, "messages": output_messages}


def build_agent_messages(
    user_message: str,
    memories: list[str],
    selected_files: list[FileRecord],
    retrieved_documents: list[dict],
    history: list[ChatMessage],
) -> list[BaseMessage]:
    messages: list[BaseMessage] = []
    for item in history:
        if item.role == "user":
            messages.append(HumanMessage(content=item.content))
        elif item.role == "assistant":
            messages.append(AIMessage(content=item.content))

    context = _build_context(memories, selected_files, retrieved_documents)
    if context:
        content = f"{context}\n\n用户当前任务：{user_message}"
    else:
        content = user_message
    messages.append(HumanMessage(content=content))
    return messages


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
