import json

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage

from app.agents.executor import (
    AGENT_SYSTEM_PROMPT,
    _extract_artifacts,
    _inject_context_message,
    _message_from_payload,
    _normalize_stream_event,
    build_agent_messages,
    build_runtime_context,
)
from app.db.models import FileRecord


def test_build_agent_messages_only_includes_current_user_message() -> None:
    messages = build_agent_messages(user_message="generate report")

    assert len(messages) == 1
    assert isinstance(messages[0], HumanMessage)
    assert messages[0].content == "generate report"


def test_agent_prompt_requires_pdf_table_tools() -> None:
    assert "read_pdf_table" in AGENT_SYSTEM_PROMPT
    assert "不要猜测" in AGENT_SYSTEM_PROMPT


def test_agent_prompt_explains_excel_highlight_rule() -> None:
    assert "highlight_gt" in AGENT_SYSTEM_PROMPT
    assert "highlight_lt" in AGENT_SYSTEM_PROMPT
    assert "highlight_column" in AGENT_SYSTEM_PROMPT
    assert "highlight_scope" in AGENT_SYSTEM_PROMPT


def test_agent_prompt_requires_excel_chart_tool() -> None:
    assert "generate_excel_chart" in AGENT_SYSTEM_PROMPT
    assert "不要回答“不支持生成图表”" in AGENT_SYSTEM_PROMPT
    assert "对话窗口直接展示" in AGENT_SYSTEM_PROMPT


def test_agent_prompt_requires_send_email_tool() -> None:
    assert "send_email" in AGENT_SYSTEM_PROMPT
    assert "file_ids" in AGENT_SYSTEM_PROMPT
    assert "邮件已发送" in AGENT_SYSTEM_PROMPT


def test_agent_prompt_requires_fetch_unread_emails_tool() -> None:
    assert "fetch_unread_emails" in AGENT_SYSTEM_PROMPT
    assert "mark_read=true" in AGENT_SYSTEM_PROMPT
    assert "未读邮件" in AGENT_SYSTEM_PROMPT


def test_build_runtime_context_includes_memory_and_file_context() -> None:
    context = build_runtime_context(
        memories=["user prefers tables"],
        selected_files=[FileRecord(id=1, filename="demo.txt", path="demo.txt", extracted_text="quarterly report")],
        retrieved_documents=[{"file_id": 1, "filename": "demo.txt", "content": "revenue increased"}],
    )

    assert "user prefers tables" in context["extra_context"]
    assert "quarterly report" in context["extra_context"]
    assert "revenue increased" in context["extra_context"]


def test_inject_context_message_binds_context_to_current_user_message() -> None:
    messages = build_agent_messages(user_message="summarize this")

    injected = _inject_context_message(messages, "selected file content")

    assert len(injected) == 1
    assert isinstance(injected[0], HumanMessage)
    assert "selected file content" in injected[0].content
    assert "summarize this" in injected[0].content


def test_extract_artifacts_from_tool_messages() -> None:
    content = json.dumps(
        {
            "ok": True,
            "artifact": {
                "id": 1,
                "kind": "word",
                "download_url": "/api/files/artifacts/1/download",
            },
        },
        ensure_ascii=False,
    )
    artifacts = _extract_artifacts([ToolMessage(content=content, tool_call_id="1"), AIMessage(content="done")])
    assert artifacts[0]["kind"] == "word"


def test_stream_event_normalization_for_message_chunks() -> None:
    chunk = AIMessageChunk(content="hello")
    mode, payload = _normalize_stream_event(("messages", (chunk, {"node": "model"})))
    assert mode == "messages"
    assert _message_from_payload(payload) == chunk
