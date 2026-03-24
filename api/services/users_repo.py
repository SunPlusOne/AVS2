from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from pathlib import Path
from threading import RLock
from typing import Any, Dict, Optional


def _hash_password(password: str, salt: str) -> str:
    raw = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
    return raw.hex()


class UsersRepo:
    def __init__(self, users_file: Path):
        self.users_file = users_file
        self._lock = RLock()

    def ensure(self) -> None:
        self.users_file.parent.mkdir(parents=True, exist_ok=True)
        if self.users_file.exists():
            return
        self.users_file.write_text("[]\n", encoding="utf-8")

    def _read_all(self) -> list[Dict[str, Any]]:
        self.ensure()
        try:
            data = json.loads(self.users_file.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [x for x in data if isinstance(x, dict)]
        except Exception:
            pass
        return []

    def _write_all(self, users: list[Dict[str, Any]]) -> None:
        self.users_file.write_text(json.dumps(users, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def exists(self, username: str) -> bool:
        target = username.strip()
        if not target:
            return False
        with self._lock:
            return any(str(u.get("username", "")) == target for u in self._read_all())

    def create_user(self, username: str, password: str) -> None:
        clean_username = username.strip()
        if not clean_username:
            raise ValueError("username required")
        if len(password) < 6:
            raise ValueError("password too short")

        with self._lock:
            users = self._read_all()
            if any(str(u.get("username", "")) == clean_username for u in users):
                raise ValueError("username exists")

            salt = secrets.token_hex(16)
            users.append(
                {
                    "username": clean_username,
                    "role": "user",
                    "salt": salt,
                    "password_hash": _hash_password(password, salt),
                }
            )
            self._write_all(users)

    def verify_user(self, username: str, password: str) -> Optional[Dict[str, str]]:
        clean_username = username.strip()
        if not clean_username:
            return None

        with self._lock:
            users = self._read_all()
            for user in users:
                if str(user.get("username", "")) != clean_username:
                    continue
                if str(user.get("role", "user")) != "user":
                    continue
                salt = str(user.get("salt", ""))
                expected = str(user.get("password_hash", ""))
                actual = _hash_password(password, salt)
                if hmac.compare_digest(expected, actual):
                    return {"username": clean_username, "role": "user"}
                return None
        return None
