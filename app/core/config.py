from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


# 项目统一配置类。
# 这个类负责集中管理后端运行需要的配置项，例如大模型 API Key、
# 模型名称、数据库地址、上传目录、向量库目录、导出文件目录和前端地址。
# 它继承 BaseSettings，所以这些默认值可以被 .env 文件或环境变量覆盖。
class Settings(BaseSettings):
    dashscope_api_key: str = "sk-e9d2d257c127408db95aacf0c41c0133"
    qwen_model: str = "qwen-plus"
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    database_url: str = "sqlite:///./storage/app.db"
    upload_dir: Path = Path("./storage/uploads")
    vector_dir: Path = Path("./storage/chroma")
    artifact_dir: Path = Path("./storage/artifacts")
    frontend_origin: str = "http://localhost:5173"
    email_smtp_host: str = "smtp.qq.com"
    email_smtp_port: int = 465
    email_smtp_username: str = ""
    email_smtp_password: str = ""
    email_from: str = ""
    email_use_ssl: bool = True

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
