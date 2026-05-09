from langchain_core.messages import HumanMessage, SystemMessage

from app.db.models import ChatMessage, FileRecord


SYSTEM_PROMPT = """你是一个智能体自动办公助手。
你需要帮助用户处理 Word、Excel、PDF、TXT、CSV 等办公文件。
回答要直接、可执行；当用户提供文件内容或检索片段时，优先基于这些内容完成任务。
如果发现用户偏好、业务背景、长期有效事实，可以简短提取为长期记忆。
不要编造文件中不存在的数据；信息不足时说明缺口并给出下一步。"""


def build_office_messages(
    user_message: str,
    memories: list[str],
    selected_files: list[FileRecord],
    retrieved_documents: list[dict],
    history: list[ChatMessage],
) -> list[SystemMessage | HumanMessage]:
    context = [
        SYSTEM_PROMPT,
        _format_memories(memories),
        _format_files(selected_files),
        _format_retrieved_documents(retrieved_documents),
        _format_history(history),
    ]
    return [
        SystemMessage(content="\n\n".join(item for item in context if item)),
        HumanMessage(content=user_message),
    ]


def _format_memories(memories: list[str]) -> str:
    if not memories:
        return ""
    return "相关长期记忆：\n" + "\n".join(f"- {item}" for item in memories)


def _format_files(files: list[FileRecord]) -> str:
    if not files:
        return ""
    chunks = ["用户指定的文件全文或摘要内容："]
    for file in files:
        chunks.append(f"文件ID {file.id}，文件名：{file.filename}\n{file.extracted_text[:12000]}")
    return "\n\n".join(chunks)


def _format_retrieved_documents(documents: list[dict]) -> str:
    if not documents:
        return ""
    chunks = ["从已上传文件中检索到的相关片段："]
    for item in documents:
        chunks.append(f"文件ID {item.get('file_id')}，文件名：{item.get('filename')}\n{item.get('content', '')[:1800]}")
    return "\n\n".join(chunks)


def _format_history(history: list[ChatMessage]) -> str:
    if not history:
        return ""
    return "最近对话：\n" + "\n".join(f"{item.role}: {item.content}" for item in history)
