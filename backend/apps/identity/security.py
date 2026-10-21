import base64
import hashlib
import pyotp
from cryptography.fernet import Fernet
from django.conf import settings


def _get_fernet() -> Fernet:
    """Derives a deterministic 32-byte Fernet key from Django's SECRET_KEY."""
    raw_key = hashlib.sha256(settings.SECRET_KEY.encode('utf-8')).digest()
    return Fernet(base64.urlsafe_b64encode(raw_key))


def encrypt_totp_secret(plain_secret: str) -> str:
    """Encrypts a plaintext base32 TOTP secret string."""
    if not plain_secret:
        return ""
    fernet = _get_fernet()
    return fernet.encrypt(plain_secret.encode('utf-8')).decode('utf-8')


def decrypt_totp_secret(cipher_secret: str) -> str:
    """Decrypts an encrypted TOTP secret ciphertext back to base32 plaintext."""
    if not cipher_secret:
        return ""
    fernet = _get_fernet()
    return fernet.decrypt(cipher_secret.encode('utf-8')).decode('utf-8')


def generate_new_totp_secret() -> str:
    """Generates a random base32 secret suitable for TOTP authenticators."""
    return pyotp.random_base32()


def get_totp_provisioning_uri(secret: str, email: str, issuer: str = "DriverXtra") -> str:
    """Generates the standard otpauth:// URI for QR codes."""
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=email, issuer_name=issuer)


def verify_totp_code(secret: str, code: str) -> bool:
    """Verifies a 6-digit TOTP code against a plaintext secret with a 1-step window."""
    if not secret or not code:
        return False
    clean_code = str(code).strip().replace(" ", "")
    totp = pyotp.TOTP(secret)
    return bool(totp.verify(clean_code, valid_window=1))
