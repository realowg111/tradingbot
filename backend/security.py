"""Security utilities: password hashing, JWT, AES-256 encryption."""
import os
import base64
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from passlib.context import CryptContext
from jose import jwt, JWTError
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

JWT_SECRET = os.environ["JWT_SECRET_KEY"]
JWT_ALG = os.environ.get("JWT_ALGORITHM", "HS256")
JWT_EXP_MIN = int(os.environ.get("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))

# AES key derived from env secret -> ensure 32 bytes
_AES_RAW = os.environ.get("AES_SECRET_KEY_BASE64", "")
try:
    _aes_bytes = base64.b64decode(_AES_RAW)
    if len(_aes_bytes) != 32:
        raise ValueError("AES key must be 32 bytes")
    AES_KEY = _aes_bytes
except Exception:
    # Fallback: derive 32 bytes from the string
    AES_KEY = hashlib.sha256(_AES_RAW.encode("utf-8")).digest()


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:
        return False


def create_access_token(data: Dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=JWT_EXP_MIN))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALG)


def decode_access_token(token: str) -> Dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except JWTError as e:
        raise e


def encrypt_str(plaintext: str) -> Dict[str, str]:
    aesgcm = AESGCM(AES_KEY)
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return {
        "nonce": base64.b64encode(nonce).decode("utf-8"),
        "ciphertext": base64.b64encode(ct).decode("utf-8"),
    }


def decrypt_str(payload: Dict[str, str]) -> str:
    aesgcm = AESGCM(AES_KEY)
    nonce = base64.b64decode(payload["nonce"])
    ct = base64.b64decode(payload["ciphertext"])
    return aesgcm.decrypt(nonce, ct, None).decode("utf-8")
