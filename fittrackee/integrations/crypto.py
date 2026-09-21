import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from flask import current_app


class IntegrationTokenError(Exception):
    pass


def _fernet() -> Fernet:
    secret = current_app.config.get("SECRET_KEY")
    if not secret:
        raise IntegrationTokenError("APP_SECRET_KEY is not configured")
    digest = hashlib.sha256(str(secret).encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_token(token: str) -> str:
    return _fernet().encrypt(token.encode("utf-8")).decode("ascii")


def decrypt_token(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise IntegrationTokenError(
            "stored MyWhoosh token can not be decrypted; reconnect the account"
        ) from exc
