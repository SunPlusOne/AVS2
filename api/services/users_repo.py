from __future__ import annotations

from typing import Optional

import bcrypt
from sqlalchemy import select

from api.database import User, db_session_context, init_database, utcnow


class UsersRepo:
    def __init__(self, users_file=None):
        # Keep constructor signature compatible with existing wiring.
        self._users_file = users_file

    def ensure(self) -> None:
        init_database()

    def ensure_admin(self, *, username: str, password: str) -> None:
        clean_username = username.strip()
        if not clean_username:
            return
        self.ensure()
        with db_session_context() as db:
            user = db.execute(select(User).where(User.username == clean_username)).scalar_one_or_none()
            if user is None:
                user = User(
                    username=clean_username,
                    password_hash=self._hash_password(password),
                    role="admin",
                    created_at=utcnow(),
                    last_login=None,
                )
                db.add(user)
                return
            if user.role != "admin":
                user.role = "admin"

    def exists(self, username: str) -> bool:
        clean_username = username.strip()
        if not clean_username:
            return False
        self.ensure()
        with db_session_context() as db:
            user = db.execute(select(User.id).where(User.username == clean_username)).scalar_one_or_none()
            return user is not None

    def create_user(self, username: str, password: str, role: str = "user") -> None:
        clean_username = username.strip()
        if not clean_username:
            raise ValueError("username required")
        if len(password) < 6:
            raise ValueError("password too short")
        if role not in {"admin", "user"}:
            raise ValueError("invalid role")

        self.ensure()
        with db_session_context() as db:
            exists = db.execute(select(User.id).where(User.username == clean_username)).scalar_one_or_none()
            if exists is not None:
                raise ValueError("username exists")

            db.add(
                User(
                    username=clean_username,
                    password_hash=self._hash_password(password),
                    role=role,
                    created_at=utcnow(),
                    last_login=None,
                )
            )

    def verify_user(self, username: str, password: str, role: Optional[str] = None) -> Optional[dict[str, str]]:
        clean_username = username.strip()
        if not clean_username:
            return None

        self.ensure()
        with db_session_context() as db:
            user = db.execute(select(User).where(User.username == clean_username)).scalar_one_or_none()
            if user is None:
                return None
            if role and user.role != role:
                return None
            if not self._verify_password(password, user.password_hash):
                return None

            user.last_login = utcnow()
            return {"id": str(user.id), "username": user.username, "role": user.role}

    def get_by_username(self, username: str) -> Optional[dict[str, str]]:
        clean_username = username.strip()
        if not clean_username:
            return None
        self.ensure()
        with db_session_context() as db:
            user = db.execute(select(User).where(User.username == clean_username)).scalar_one_or_none()
            if user is None:
                return None
            return {"id": str(user.id), "username": user.username, "role": user.role}

    @staticmethod
    def _hash_password(password: str) -> str:
        hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
        return hashed.decode("utf-8")

    @staticmethod
    def _verify_password(password: str, password_hash: str) -> bool:
        try:
            return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
        except Exception:
            return False
