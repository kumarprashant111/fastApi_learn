from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "FastAPI with uv"
    debug: bool = True
    database_url: str  # e.g. "postgresql+asyncpg://app:app@localhost:5432/appdb"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()
