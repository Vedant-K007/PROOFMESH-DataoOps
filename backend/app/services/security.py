"""Local authentication primitives without exposing secrets to the frontend."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, status

from app.services.platform import _connect, _now, init_db


def _hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 210_000)
    return f"{base64.urlsafe_b64encode(salt).decode()}:{base64.urlsafe_b64encode(derived).decode()}"


def _verify_password(password: str, encoded: str) -> bool:
    try:
        salt_text, digest_text = encoded.split(":", 1)
        salt = base64.urlsafe_b64decode(salt_text)
        expected = base64.urlsafe_b64decode(digest_text)
    except (ValueError, TypeError):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 210_000)
    return hmac.compare_digest(actual, expected)


def init_auth_db() -> None:
    init_db()
    with _connect() as connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
                display_name TEXT NOT NULL, role TEXT NOT NULL, created_at TEXT NOT NULL
            )"""
        )


def register_user(email: str, password: str, display_name: str, role: str = "investigator") -> dict:
    init_auth_db()
    if len(password) < 8:
        raise HTTPException(status_code=422, detail="Password must be at least 8 characters.")
    if role not in {"administrator", "investigator", "reviewer"}:
        raise HTTPException(status_code=422, detail="Unsupported user role.")
    user = {"id": str(uuid4()), "email": email.strip().lower(), "display_name": display_name.strip(), "role": role, "created_at": _now()}
    try:
        with _connect() as connection:
            connection.execute(
                "INSERT INTO users VALUES (?, ?, ?, ?, ?, ?)",
                (user["id"], user["email"], _hash_password(password), user["display_name"], role, user["created_at"]),
            )
    except sqlite3.IntegrityError as error:
        raise HTTPException(status_code=409, detail="An account with this email already exists.") from error
    return user


def _token(user: dict) -> str:
    secret = os.environ.get("PROOFMESH_AUTH_SECRET", "local-development-secret-change-me").encode()
    payload = {"sub": user["id"], "email": user["email"], "role": user["role"], "exp": int((datetime.now(timezone.utc) + timedelta(hours=8)).timestamp())}
    encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    signature = hmac.new(secret, encoded.encode(), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def login_user(email: str, password: str) -> dict:
    init_auth_db()
    with _connect() as connection:
        row = connection.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),)).fetchone()
    if row is None or not _verify_password(password, row["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")
    user = {key: row[key] for key in ("id", "email", "display_name", "role", "created_at")}
    return {"access_token": _token(user), "token_type": "bearer", "user": user}


def current_user(token: str) -> dict:
    secret = os.environ.get("PROOFMESH_AUTH_SECRET", "local-development-secret-change-me").encode()
    try:
        encoded, signature = token.split(".", 1)
        expected = hmac.new(secret, encoded.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError
        payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        if int(payload["exp"]) < int(datetime.now(timezone.utc).timestamp()):
            raise ValueError
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise HTTPException(status_code=401, detail="Invalid or expired access token.")
    return payload
