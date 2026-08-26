import hashlib
import hmac
import time

from cryptography.fernet import Fernet


def _get_fernet() -> Fernet:
    from webhook_relay.config import settings

    return Fernet(settings.secret_encryption_key.get_secret_value())


def encrypt_secret(plain_secret: str) -> str:
    return _get_fernet().encrypt(plain_secret.encode()).decode()


def decrypt_secret(encrypted_secret: str) -> str:
    return _get_fernet().decrypt(encrypted_secret.encode()).decode()


def sign(secret: str, timestamp: str, raw_body: bytes) -> str:
    message = timestamp.encode() + b"." + raw_body
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def verify(
    secret: str, timestamp: str, raw_body: bytes, signature: str, max_age_seconds: int = 300
) -> bool:
    try:
        sent_at = int(timestamp)
    except ValueError:
        return False

    if abs(time.time() - sent_at) > max_age_seconds:
        return False

    expected_signature = sign(secret, timestamp, raw_body)
    return hmac.compare_digest(expected_signature, signature)
