from pathlib import Path

from app.tools import output_tools


def test_generate_word_and_excel(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(output_tools.settings, "artifact_dir", tmp_path)

    word = output_tools.generate_word("报告.docx", "第一段\n第二段")
    excel = output_tools.generate_excel("表格.xlsx", "产品,金额\nA,100")

    assert word.exists()
    assert word.suffix == ".docx"
    assert excel.exists()
    assert excel.suffix == ".xlsx"
