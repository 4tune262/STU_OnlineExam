
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _get_fernet():
    """
    Tạo bộ mã hóa Fernet từ SECRET_KEY của Django.

    SECRET_KEY phải được giữ bí mật và ổn định
    để có thể giải mã các khóa TOTP đã lưu.
    """
    django_secret = settings.SECRET_KEY.encode("utf-8")

    derived_key = hashlib.sha256(django_secret).digest()
    fernet_key = base64.urlsafe_b64encode(derived_key)

    return Fernet(fernet_key)


def encrypt_totp_secret(secret: str) -> str:
    """
    Mã hóa khóa bí mật TOTP trước khi lưu vào database.
    """
    if not secret:
        raise ValueError("Khóa bí mật TOTP không được để trống.")

    encrypted = _get_fernet().encrypt(secret.encode("utf-8"))
    return encrypted.decode("utf-8")


def decrypt_totp_secret(encrypted_secret: str) -> str:
    """
    Giải mã khóa TOTP đã lưu trong database.
    """
    if not encrypted_secret:
        raise ValueError("Chưa có khóa bí mật TOTP.")

    try:
        decrypted = _get_fernet().decrypt(
            encrypted_secret.encode("utf-8")
        )
    except InvalidToken as exc:
        raise ValueError(
            "Không thể giải mã khóa TOTP. "
            "Hãy kiểm tra SECRET_KEY và dữ liệu đã lưu."
        ) from exc

    return decrypted.decode("utf-8")
