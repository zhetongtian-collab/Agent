from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    dashscope_api_key: str = "sk-e9d2d257c127408db95aacf0c41c0133"
    qwen_model: str = "qwen-plus"
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    database_url: str = "sqlite:///./storage/app.db"
    upload_dir: Path = Path("./storage/uploads")
    vector_dir: Path = Path("./storage/chroma")
    artifact_dir: Path = Path("./storage/artifacts")
    frontend_origin: str = "http://localhost:5173"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
