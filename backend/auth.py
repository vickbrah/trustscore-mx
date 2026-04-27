"""Autenticación: JWT para sesión + API keys para integración."""

import os
import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException, Header, status
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from jose import jwt, JWTError

from db import User, ApiKey, get_db

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
JWT_ALG = os.getenv("JWT_ALG", "HS256")


# === Passwords ===

def hash_password(p: str) -> str:
    return pwd_ctx.hash(p)


def verify_password(p: str, h: str) -> bool:
    return pwd_ctx.verify(p, h)


# === JWT ===

def crear_jwt(user_id: int, hours: int = 72) -> str:
    payload = {
        "sub": str(user_id),
        "exp": datetime.utcnow() + timedelta(hours=hours),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def decode_jwt(token: str) -> Optional[int]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        return int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        return None


# === API keys ===

def generar_api_key() -> tuple[str, str, str]:
    """Devuelve (api_key_completa, prefix, hash_secreta)."""
    raw = secrets.token_urlsafe(32)
    full = f"tsmx_{raw}"
    prefix = full[:12]  # tsmx_xxxxxx
    h = hashlib.sha256(full.encode()).hexdigest()
    return full, prefix, h


def verificar_api_key(full_key: str) -> str:
    return hashlib.sha256(full_key.encode()).hexdigest()


# === Dependencias FastAPI ===

def get_current_user(
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> User:
    """Acepta JWT (Bearer) o API key (X-API-Key)."""
    user: Optional[User] = None

    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
        uid = decode_jwt(token)
        if uid:
            user = db.query(User).filter(User.id == uid).first()

    if not user and x_api_key:
        h = verificar_api_key(x_api_key)
        ak = db.query(ApiKey).filter(
            ApiKey.key_hash == h, ApiKey.activa == True  # noqa
        ).first()
        if ak:
            ak.ultima_usada = datetime.utcnow()
            db.commit()
            user = db.query(User).filter(User.id == ak.user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticación requerida (Bearer JWT o X-API-Key)",
        )
    return user
