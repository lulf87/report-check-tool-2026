from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    codex_command: str = "codex"
    codex_model: str = "gpt-5.4"
    codex_reasoning_effort: str = "medium"
    codex_timeout_seconds: int = 300
    codex_use_output_schema: bool = False
    render_pages: bool = True
    ocr_enabled: bool = False


settings = Settings()
