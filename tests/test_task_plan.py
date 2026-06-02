import json

from langchain_core.messages import AIMessage, ToolMessage

from app.agents.task_plan import TaskPlanTracker, build_task_plan


def test_build_task_plan_for_email_feedback_report_workflow() -> None:
    steps = build_task_plan("帮我读取今天未读邮件，把客户反馈整理成 Word 报告，并发给我。")

    assert [step.title for step in steps] == [
        "拉取未读邮件",
        "筛选客户反馈邮件",
        "提取邮件正文和附件内容",
        "生成 Word 报告",
        "发送邮件",
    ]


def test_task_plan_tracker_marks_tool_call_running_and_success() -> None:
    tracker = TaskPlanTracker("帮我收一下未读邮件")

    running_events = tracker.observe_message(
        AIMessage(
            content="",
            tool_calls=[{"name": "fetch_unread_emails", "args": {}, "id": "call-1", "type": "tool_call"}],
        )
    )
    success_events = tracker.observe_message(
        ToolMessage(
            content=json.dumps({"ok": True, "unread_emails": {"count": 0}}),
            name="fetch_unread_emails",
            tool_call_id="call-1",
        )
    )

    assert running_events[-1]["step"]["status"] == "running"
    assert success_events[-1]["step"]["status"] == "success"


def test_task_plan_tracker_marks_tool_error_failed() -> None:
    tracker = TaskPlanTracker("帮我发邮件")
    tracker.observe_message(
        AIMessage(
            content="",
            tool_calls=[{"name": "send_email", "args": {}, "id": "call-2", "type": "tool_call"}],
        )
    )

    events = tracker.observe_message(
        ToolMessage(
            content=json.dumps({"ok": False, "error": "SMTP authentication failed"}),
            name="send_email",
            tool_call_id="call-2",
        )
    )

    assert events[-1]["step"]["status"] == "failed"
    assert events[-1]["step"]["detail"] == "SMTP authentication failed"
