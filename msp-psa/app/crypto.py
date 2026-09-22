"""Field-level encryption for stored credentials.

Fernet (symmetric, authenticated) with a key that lives only in the
environment, never in the database or the git repo. Losing the key means
losing every stored password — back it up somewhere separate from the
database dump, e.g. a password manager, not the same Azure Blob container.
"""

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


class EncryptionNotConfigured(Exception):
    pass


@lru_cache
def _fernet() -> Fernet:
    key = settings.credential_encryption_key
    if not key:
        raise EncryptionNotConfigured(
            "CREDENTIAL_ENCRYPTION_KEY is not set. Generate one with:\n"
            '  python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"\n'
            "and add it to the environment before storing credentials."
        )
    return Fernet(key.encode())


def encrypt_secret(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def decrypt_secret(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("Could not decrypt — wrong key or corrupted value") from exc
