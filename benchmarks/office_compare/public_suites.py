from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from benchmarks.office_compare.public_data import PublicDataRoots


ROOT = Path(__file__).resolve().parent
CASES = ROOT / "cases"


def load_officebench_subset(data_roots: PublicDataRoots) -> list[dict[str, Any]]:
    manifest = json.loads((CASES / "officebench_subset.json").read_text(encoding="utf-8"))
    tasks = []
    for item in manifest:
        family, subtask = item["source_task"].split("/")
        source = data_roots.officebench / "tasks" / family / "subtasks" / f"{subtask}.json"
        official = json.loads(source.read_text(encoding="utf-8"))
        keywords = _officebench_keywords(official["evaluation"])
        artifact_kind = item.get("artifact_kind")
        prompt = official["task"]
        grader: dict[str, Any] = {"type": "contains_all", "values": keywords}
        if artifact_kind:
            prompt += (
                "\n请将最终结果生成一个可下载的 Word artifact。"
                "如果原题要求修改已有文档，请生成包含修改后最终内容的新 Word 文件。"
            )
            grader = {"type": "artifact_word", "kind": artifact_kind, "values": keywords}
        tasks.append(
            {
                "id": item["id"],
                "source_task": item["source_task"],
                "group": "officebench_adapted",
                "title": official["task"],
                "uploads": [str(data_roots.officebench / path) for path in item["uploads"]],
                "steps": [{"prompt": prompt, "grader": grader}],
            }
        )
    return tasks


def load_spreadsheetbench_subset(data_roots: PublicDataRoots) -> list[dict[str, Any]]:
    selected_ids = {
        str(item)
        for item in json.loads((CASES / "spreadsheetbench_verified_subset.json").read_text(encoding="utf-8"))
    }
    dataset = json.loads((data_roots.spreadsheetbench / "dataset.json").read_text(encoding="utf-8"))
    by_id = {str(item["id"]): item for item in dataset}
    tasks = []
    for item_id in json.loads((CASES / "spreadsheetbench_verified_subset.json").read_text(encoding="utf-8")):
        metadata = by_id[str(item_id)]
        folder = data_roots.spreadsheetbench / metadata["spreadsheet_path"]
        initial = next(folder.glob("*_init.xlsx"))
        golden = next(folder.glob("*_golden.xlsx"))
        prompt = (
            f"{metadata['instruction']}\n"
            "请直接修改选中的 Excel 工作簿来完成任务。"
            f"将结果写入区域 {metadata['answer_position']}。"
            "必须调用 write_uploaded_excel_range、fill_uploaded_excel_formula 或 edit_uploaded_excel_cells 返回修改后的 Excel artifact。"
            "连续结果区域优先批量写入；明确要求公式时优先使用公式填充工具。"
        )
        tasks.append(
            {
                "id": f"P{len(tasks) + 1:02d}",
                "source_task": str(item_id),
                "group": "spreadsheetbench_verified",
                "title": f"SpreadsheetBench Verified {item_id}",
                "uploads": [str(initial)],
                "steps": [
                    {
                        "prompt": prompt,
                        "grader": {
                            "type": "artifact_spreadsheet_golden",
                            "kind": "excel",
                            "golden_path": str(golden),
                            "answer_position": metadata["answer_position"],
                            "answer_sheet": metadata.get("answer_sheet"),
                        },
                    }
                ],
            }
        )
    if len(tasks) != len(selected_ids):
        raise RuntimeError("SpreadsheetBench subset contains duplicate IDs")
    return tasks


def _officebench_keywords(evaluations: list[dict[str, Any]]) -> list[str]:
    keywords: list[str] = []
    for evaluation in evaluations:
        if evaluation["function"] == "evaluate_contain":
            keywords.extend(str(item) for item in evaluation["args"].get("keywords", []))
    if not keywords:
        raise RuntimeError("OfficeBench adapted task must provide evaluate_contain keywords")
    return keywords
