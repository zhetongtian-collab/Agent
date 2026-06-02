from pathlib import Path

from openpyxl import Workbook

from benchmarks.office_compare.adapters import ChatResult
from benchmarks.office_compare.generate_fixtures import FIXTURES, generate
from benchmarks.office_compare.graders import _grade_spreadsheet_golden, grade


def test_generate_benchmark_fixtures() -> None:
    generate()
    assert (FIXTURES / "project_brief.docx").exists()
    assert (FIXTURES / "inventory_policy.docx").exists()
    assert (FIXTURES / "travel_policy.pdf").read_bytes().startswith(b"%PDF")
    assert (FIXTURES / "sales.xlsx").exists()


def test_contains_all_grader_normalizes_commas(tmp_path: Path) -> None:
    result = ChatResult(answer="预算为 580,000 元。", artifacts=[], elapsed_seconds=0, raw={})
    outcome = grade(result, {"type": "contains_all", "values": ["580000"]}, "", tmp_path)
    assert outcome.passed is True


def test_contains_all_grader_normalizes_localized_dates(tmp_path: Path) -> None:
    result = ChatResult(answer="截止日期是 2026年9月30日。", artifacts=[], elapsed_seconds=0, raw={})
    outcome = grade(result, {"type": "contains_all", "values": ["2026-09-30"]}, "", tmp_path)
    assert outcome.passed is True


def test_spreadsheet_golden_grader_checks_answer_range(tmp_path: Path) -> None:
    actual = tmp_path / "actual.xlsx"
    golden = tmp_path / "golden.xlsx"
    for path in [actual, golden]:
        workbook = Workbook()
        sheet = workbook.active
        sheet["B2"] = 270
        workbook.save(path)
    outcome = _grade_spreadsheet_golden(
        actual,
        {"golden_path": str(golden), "answer_position": "B2"},
    )
    assert outcome.passed is True
