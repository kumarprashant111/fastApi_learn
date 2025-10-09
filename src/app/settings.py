# src/app/settings.py
from __future__ import annotations
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # DB
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/appdb",
        alias="DATABASE_URL",
    )

    # Optional app fields (since your .env has them)
    app_name: str = Field(default="FastAPI with uv (Postgres)", alias="APP_NAME")
    debug: bool = Field(default=False, alias="DEBUG")

    # Pydantic v2 settings config
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",     # <-- ignore extra env keys we didn't model
    )


settings = Settings()
