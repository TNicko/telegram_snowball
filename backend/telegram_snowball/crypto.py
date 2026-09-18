from __future__ import annotations

from pathlib import Path

from cryptography.fernet import Fernet

from telegram_snowball.config import Settings


def _secret_path(settings: Settings) -> Path:
    return settings.data_dir / "secret.key"


def load_fernet(settings: Settings) -> Fernet:
    if settings.snowball_secret_key.strip():
        return Fernet(settings.snowball_secret_key.strip().encode("ascii"))
    path = _secret_path(settings)
    if path.exists():
        return Fernet(path.read_text(encoding="ascii").strip().encode("ascii"))
    key = Fernet.generate_key()
    path.write_text(key.decode("ascii"), encoding="ascii")
    path.chmod(0o600)
    return Fernet(key)


def encrypt_text(fernet: Fernet, value: str) -> str:
    return fernet.encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_text(fernet: Fernet, value: str) -> str:
    return fernet.decrypt(value.encode("ascii")).decode("utf-8")
