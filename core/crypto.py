"""Encrypts users' saved API keys.

Keys are encrypted with Fernet (AES + HMAC) using ENCRYPTION_KEY, which lives
only in the server's secrets. The database never contains a readable key.
"""
from cryptography.fernet import Fernet, InvalidToken

import config


class CryptoNotConfigured(RuntimeError):
    pass


def _fernet() -> Fernet:
    if not config.ENCRYPTION_KEY:
        raise CryptoNotConfigured("ENCRYPTION_KEY is not set - saving keys is disabled.")
    return Fernet(config.ENCRYPTION_KEY.encode())


def is_configured() -> bool:
    try:
        _fernet()
        return True
    except Exception:  # noqa: BLE001
        return False


def encrypt(text: str) -> str:
    return _fernet().encrypt(text.encode()).decode()


def decrypt(token: str) -> str | None:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, CryptoNotConfigured, ValueError):
        return None


def mask(key: str) -> str:
    return f"{key[:4]}…{key[-4:]}" if key and len(key) > 10 else "••••"


def generate_key() -> str:
    return Fernet.generate_key().decode()
