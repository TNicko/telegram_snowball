from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    postgres_dsn: str = "postgresql://snowball:snowball@127.0.0.1:5432/snowball"
    snowball_data_dir: Path = Path("./data")
    snowball_secret_key: str = ""
    log_level: str = "INFO"
    snowball_bind: str = "127.0.0.1"
    snowball_api_port: int = 8000

    @property
    def data_dir(self) -> Path:
        path = self.snowball_data_dir.expanduser().resolve()
        path.mkdir(parents=True, exist_ok=True)
        (path / "chats" / "telegram").mkdir(parents=True, exist_ok=True)
        (path / "models").mkdir(parents=True, exist_ok=True)
        (path / "blobs" / "images").mkdir(parents=True, exist_ok=True)
        (path / "cache" / "images").mkdir(parents=True, exist_ok=True)
        (path / "tmp" / "media").mkdir(parents=True, exist_ok=True)
        return path


def load_settings() -> Settings:
    return Settings()
