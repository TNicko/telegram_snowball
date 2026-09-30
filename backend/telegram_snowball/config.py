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
    snowball_embed_url: str = "http://127.0.0.1:8001"
    snowball_embed_bind: str = "127.0.0.1"
    snowball_embed_port: int = 8001
    snowball_worker_kind: str = "scrape"
    snowball_http_port: int = 8080
    telegram_api_id: str = ""
    telegram_api_hash: str = ""
    telegram_phone: str = ""

    def env_telegram_api(self) -> tuple[int, str] | None:
        raw_id = self.telegram_api_id.strip()
        raw_hash = self.telegram_api_hash.strip()
        if not raw_id or not raw_hash:
            return None
        try:
            api_id = int(raw_id)
        except ValueError:
            return None
        if api_id <= 0 or len(raw_hash) < 8:
            return None
        return api_id, raw_hash

    def env_telegram_phone(self) -> str:
        return self.telegram_phone.strip()

    @property
    def data_dir(self) -> Path:
        path = self.snowball_data_dir.expanduser().resolve()
        path.mkdir(parents=True, exist_ok=True)
        (path / "chats" / "telegram").mkdir(parents=True, exist_ok=True)
        (path / "models").mkdir(parents=True, exist_ok=True)
        (path / "blobs" / "images").mkdir(parents=True, exist_ok=True)
        (path / "cache" / "images").mkdir(parents=True, exist_ok=True)
        (path / "tmp" / "media").mkdir(parents=True, exist_ok=True)
        (path / "scope").mkdir(parents=True, exist_ok=True)
        return path


def load_settings() -> Settings:
    return Settings()
