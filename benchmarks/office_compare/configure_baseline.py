from __future__ import annotations

import argparse
from pathlib import Path


def _replace(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise RuntimeError(f"Expected source text was not found in {path}")
    path.write_text(text.replace(old, new), encoding="utf-8")


def configure(root: Path) -> None:
    api = root / "api"
    _replace(
        api / "chroma_utils.py",
        "embedding_function = OpenAIEmbeddings()",
        """embedding_function = OpenAIEmbeddings(
    model=os.getenv("EMBEDDING_MODEL", "text-embedding-v4"),
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    check_embedding_ctx_length=False,
)""",
    )
    _replace(
        api / "langchain_utils.py",
        """def get_rag_chain(model="gpt-4o-mini"):
    llm = ChatOpenAI(model=model)""",
        """def get_rag_chain(model="qwen-plus"):
    llm = ChatOpenAI(
        model=model,
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    )""",
    )
    _replace(
        api / "pydantic_models.py",
        """class ModelName(str, Enum):
    GPT4_O = "gpt-4o"
    GPT4_O_MINI = "gpt-4o-mini\"""",
        """class ModelName(str, Enum):
    QWEN_PLUS = "qwen-plus\"""",
    )
    _replace(
        api / "pydantic_models.py",
        "model: ModelName = Field(default=ModelName.GPT4_O_MINI)",
        "model: ModelName = Field(default=ModelName.QWEN_PLUS)",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("baseline_root", type=Path)
    args = parser.parse_args()
    configure(args.baseline_root.resolve())
    print(f"Configured baseline at {args.baseline_root.resolve()}")


if __name__ == "__main__":
    main()
