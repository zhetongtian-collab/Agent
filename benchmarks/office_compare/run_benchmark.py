from __future__ import annotations

import argparse
import csv
from datetime import datetime
import json
from pathlib import Path
from statistics import mean
from typing import Any

from benchmarks.office_compare.adapters import BaselineAdapter, LongChainAdapter
from benchmarks.office_compare.generate_fixtures import FIXTURES, generate
from benchmarks.office_compare.graders import grade
from benchmarks.office_compare.public_data import PublicDataRoots, prepare_public_data
from benchmarks.office_compare.public_suites import load_officebench_subset, load_spreadsheetbench_subset


ROOT = Path(__file__).resolve().parent
CASES = ROOT / "cases"
RESULTS = ROOT / "results"


def _load_cases(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def _run_task(adapter: Any, task: dict[str, Any], artifact_dir: Path) -> dict[str, Any]:
    adapter.reset_session(task["id"])
    file_ids = [adapter.upload(_upload_path(filename)) for filename in task["uploads"]]
    steps = []
    for index, step in enumerate(task["steps"], start=1):
        result = adapter.chat(step["prompt"], file_ids)
        outcome = grade(result, step["grader"], adapter.base_url, artifact_dir / task["id"])
        steps.append(
            {
                "step": index,
                "prompt": step["prompt"],
                "answer": result.answer,
                "artifacts": result.artifacts,
                "elapsed_seconds": round(result.elapsed_seconds, 3),
                "passed": outcome.passed,
                "detail": outcome.detail,
            }
        )
    return {
        "system": adapter.name,
        "task_id": task["id"],
        "source_task": task.get("source_task", task["id"]),
        "group": task["group"],
        "title": task["title"],
        "status": "passed" if all(item["passed"] for item in steps) else "failed",
        "passed": all(item["passed"] for item in steps),
        "elapsed_seconds": round(sum(item["elapsed_seconds"] for item in steps), 3),
        "steps": steps,
    }


def _summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries = []
    for system in sorted({row["system"] for row in rows}):
        system_rows = [row for row in rows if row["system"] == system]
        total_passed = sum(1 for row in system_rows if row["passed"])
        summaries.append(
            {
                "system": system,
                "group": "overall",
                "passed": total_passed,
                "total": len(system_rows),
                "pass_rate": round(total_passed / len(system_rows), 4) if system_rows else 0,
                "average_seconds": round(mean(row["elapsed_seconds"] for row in system_rows), 3) if system_rows else 0,
            }
        )
        for group in sorted({row["group"] for row in system_rows}):
            group_rows = [row for row in system_rows if row["group"] == group]
            passed = sum(1 for row in group_rows if row["passed"])
            summaries.append(
                {
                    "system": system,
                    "group": group,
                    "passed": passed,
                    "total": len(group_rows),
                    "pass_rate": round(passed / len(group_rows), 4) if group_rows else 0,
                    "average_seconds": round(mean(row["elapsed_seconds"] for row in group_rows), 3) if group_rows else 0,
                }
            )
    return summaries


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["system", "task_id", "source_task", "group", "title", "status", "elapsed_seconds", "detail"],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "system": row["system"],
                    "task_id": row["task_id"],
                    "source_task": row.get("source_task", row["task_id"]),
                    "group": row["group"],
                    "title": row["title"],
                    "status": row["status"],
                    "elapsed_seconds": row["elapsed_seconds"],
                    "detail": " | ".join(step["detail"] for step in row["steps"]),
                }
            )


def _write_markdown(path: Path, summaries: list[dict[str, Any]], rows: list[dict[str, Any]]) -> None:
    lines = [
        "# LongChain 与 conversational-rag-chatbot 对比实验报告",
        "",
        f"生成时间：{datetime.now().isoformat(timespec='seconds')}",
        "",
        "## 汇总",
        "",
        "| 系统 | 任务组 | 通过数 | 总数 | 任务完成率 | 平均耗时（秒） |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for item in summaries:
        lines.append(
            f"| {item['system']} | {item['group']} | {item['passed']} | {item['total']} | "
            f"{item['pass_rate']:.2%} | {item['average_seconds']:.3f} |"
        )
    lines.extend(
        [
            "",
            "## 逐项结果",
            "",
            "| 系统 | 编号 | 来源任务 | 任务组 | 任务 | 结果 | 耗时（秒） |",
            "| --- | --- | --- | --- | --- | --- | ---: |",
        ]
    )
    for row in rows:
        lines.append(
            f"| {row['system']} | {row['task_id']} | {row.get('source_task', row['task_id'])} | {row['group']} | {row['title']} | "
            f"{row['status']} | {row['elapsed_seconds']:.3f} |"
        )
    lines.extend(
        [
            "",
            "## 说明",
            "",
            "- `shared` 是双方都支持的文档 RAG 能力，用于公平比较。",
            "- `longchain_extension` 是 LongChain 办公 Agent 的扩展能力，不计入 baseline 基础问答准确率。",
            "- `officebench_adapted` 是从 OfficeBench 官方任务中选取并适配到 LongChain HTTP 工具边界的 20 条任务，不代表 OfficeBench 官方 Docker 环境总分。",
            "- `spreadsheetbench_verified` 是 SpreadsheetBench Verified 官方子集 20 条，使用初始工作簿和 golden 指定区域自动评分。",
            "- baseline 为公开仓库 `aryanmahawar205/conversational-rag-chatbot`，通过 `configure_baseline.py` 切换为 DashScope 兼容配置。",
            "- 两套系统统一使用 `qwen-plus` 作为生成模型；baseline 使用 DashScope `text-embedding-v4`，LongChain 保持项目内置 HashEmbedding。",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--longchain-url", default="http://localhost:8000")
    parser.add_argument("--baseline-url", default="http://localhost:8001")
    parser.add_argument("--skip-baseline", action="store_true")
    parser.add_argument("--baseline-full", action="store_true", help="Run the baseline against all selected task groups")
    parser.add_argument("--skip-public", action="store_true")
    parser.add_argument("--public-cache", type=Path)
    parser.add_argument("--officebench-root", type=Path)
    parser.add_argument("--spreadsheetbench-root", type=Path)
    parser.add_argument("--task-ids", help="Comma-separated benchmark task IDs to run, for example O19,P17")
    parser.add_argument("--resume-latest", action="store_true", help="Replace selected tasks in the existing latest report")
    args = parser.parse_args()

    generate()
    RESULTS.mkdir(parents=True, exist_ok=True)
    artifact_dir = RESULTS / "artifacts"
    shared = _load_cases(CASES / "shared_tasks.json")
    extensions = _load_cases(CASES / "longchain_tasks.json")
    rows: list[dict[str, Any]] = _existing_rows() if args.resume_latest else []
    selected_ids = {item.strip() for item in (args.task_ids or "").split(",") if item.strip()}
    longchain_tasks = [*shared, *extensions]
    if not args.skip_public:
        roots = _public_data_roots(args)
        longchain_tasks.extend(load_officebench_subset(roots))
        longchain_tasks.extend(load_spreadsheetbench_subset(roots))
    adapters: list[tuple[Any, list[dict[str, Any]]]] = [(LongChainAdapter(args.longchain_url), longchain_tasks)]
    if not args.skip_baseline:
        adapters.append((BaselineAdapter(args.baseline_url), longchain_tasks if args.baseline_full else shared))

    for adapter, tasks in adapters:
        for task in tasks:
            if selected_ids and task["id"] not in selected_ids:
                continue
            print(f"[{adapter.name}] running {task['id']} {task['title']}", flush=True)
            try:
                _upsert(rows, _run_task(adapter, task, artifact_dir / adapter.name))
            except Exception as exc:
                _upsert(
                    rows,
                    {
                        "system": adapter.name,
                        "task_id": task["id"],
                        "source_task": task.get("source_task", task["id"]),
                        "group": task["group"],
                        "title": task["title"],
                        "status": "error",
                        "passed": False,
                        "elapsed_seconds": 0,
                        "steps": [{"detail": str(exc)}],
                    }
                )

    summaries = _summary(rows)
    (RESULTS / "latest.json").write_text(
        json.dumps({"summary": summaries, "results": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_csv(RESULTS / "latest.csv", rows)
    _write_markdown(RESULTS / "latest.md", summaries, rows)
    print(json.dumps(summaries, ensure_ascii=False, indent=2))


def _upload_path(filename: str) -> Path:
    path = Path(filename)
    return path if path.is_absolute() else FIXTURES / path


def _public_data_roots(args: argparse.Namespace) -> PublicDataRoots:
    if args.officebench_root and args.spreadsheetbench_root:
        return PublicDataRoots(
            officebench=args.officebench_root.resolve(),
            spreadsheetbench=args.spreadsheetbench_root.resolve(),
        )
    if args.officebench_root or args.spreadsheetbench_root:
        raise RuntimeError("Pass both --officebench-root and --spreadsheetbench-root, or neither")
    return prepare_public_data(args.public_cache)


def _existing_rows() -> list[dict[str, Any]]:
    path = RESULTS / "latest.json"
    if not path.exists():
        return []
    return list(json.loads(path.read_text(encoding="utf-8")).get("results", []))


def _upsert(rows: list[dict[str, Any]], incoming: dict[str, Any]) -> None:
    key = (incoming["system"], incoming["task_id"])
    rows[:] = [row for row in rows if (row["system"], row["task_id"]) != key]
    rows.append(incoming)


if __name__ == "__main__":
    main()
