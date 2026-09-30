from __future__ import annotations

from pathlib import Path

from telegram_snowball.config import Settings


def _settings(tmp_path: Path, **kwargs: str) -> Settings:
    return Settings(snowball_data_dir=tmp_path, postgres_dsn="postgresql://unused", **kwargs)


def test_env_telegram_api_requires_id_and_hash(tmp_path: Path) -> None:
    assert _settings(tmp_path).env_telegram_api() is None
    assert _settings(tmp_path, telegram_api_id="12345").env_telegram_api() is None
    assert _settings(tmp_path, telegram_api_hash="abcd1234").env_telegram_api() is None


def test_env_telegram_api_parses_valid_pair(tmp_path: Path) -> None:
    settings = _settings(tmp_path, telegram_api_id=" 12345 ", telegram_api_hash=" abcd1234 ")
    assert settings.env_telegram_api() == (12345, "abcd1234")


def test_env_telegram_api_rejects_invalid_id(tmp_path: Path) -> None:
    assert (
        _settings(tmp_path, telegram_api_id="nope", telegram_api_hash="abcd1234").env_telegram_api()
        is None
    )
    assert (
        _settings(tmp_path, telegram_api_id="0", telegram_api_hash="abcd1234").env_telegram_api()
        is None
    )
    assert (
        _settings(tmp_path, telegram_api_id="12", telegram_api_hash="short").env_telegram_api() is None
    )


def test_env_telegram_phone_strips(tmp_path: Path) -> None:
    assert _settings(tmp_path).env_telegram_phone() == ""
    assert _settings(tmp_path, telegram_phone=" +15551234567 ").env_telegram_phone() == "+15551234567"
