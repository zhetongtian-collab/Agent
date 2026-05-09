import json

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage

from app.agents.executor import _extract_artifacts, _message_from_payload, _normalize_stream_event, build_agent_messages
from app.db.models import FileRecord


def test_build_agent_messages_includes_context() -> None:
    messages = build_agent_messages(
        user_message="生成报告",
        memories=["用户喜欢表格"],
        selected_files=[FileRecord(id=1, filename="demo.txt", path="demo.txt", extracted_text="季度报告")],
        retrieved_documents=[{"file_id": 1, "filename": "demo.txt", "content": "收入增长"}],
        history=[],
    )

    assert isinstance(messages[-1], HumanMessage)
    assert "季度报告" in messages[-1].content
    assert "用户喜欢表格" in messages[-1].content


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
    artifacts = _extract_artifacts([ToolMessage(content=content, tool_call_id="1"), AIMessage(content="完成")])
    assert artifacts[0]["kind"] == "word"


def test_stream_event_normalization_for_message_chunks() -> None:
    chunk = AIMessageChunk(content="hello")
    mode, payload = _normalize_stream_event(("messages", (chunk, {"node": "model"})))
    assert mode == "messages"
    assert _message_from_payload(payload) == chunk
