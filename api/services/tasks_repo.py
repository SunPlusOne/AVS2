from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import select

from api.database import Task, User, db_session_context, init_database, utcnow


def _to_db_status(status: str) -> str:
    mapping = {
        "queued": "pending",
        "running": "running",
        "completed": "done",
        "failed": "failed",
        "canceled": "failed",
    }
    return mapping.get(status, status)


class TasksRepo:
    def ensure(self) -> None:
        init_database()

    def create_task(
        self,
        *,
        task_uid: str,
        user_id: Optional[int],
        model_id: Optional[int],
        input_path: Optional[str],
    ) -> None:
        self.ensure()
        with db_session_context() as db:
            db.add(
                Task(
                    task_uid=task_uid,
                    user_id=user_id,
                    model_id=model_id,
                    status="pending",
                    input_path=input_path,
                    output_path=None,
                    created_at=utcnow(),
                    finished_at=None,
                )
            )

    def update_task_status(
        self,
        *,
        task_uid: str,
        status: str,
        output_path: Optional[str] = None,
        finished_at: Optional[datetime] = None,
    ) -> None:
        self.ensure()
        with db_session_context() as db:
            row = db.execute(select(Task).where(Task.task_uid == task_uid)).scalar_one_or_none()
            if row is None:
                return
            row.status = _to_db_status(status)
            if output_path is not None:
                row.output_path = output_path
            if finished_at is not None:
                row.finished_at = finished_at
            elif row.status in {"done", "failed"}:
                row.finished_at = utcnow()

    def get_owner_username(self, *, task_uid: str) -> Optional[str]:
        self.ensure()
        with db_session_context() as db:
            row = db.execute(
                select(User.username)
                .select_from(Task)
                .join(User, Task.user_id == User.id, isouter=True)
                .where(Task.task_uid == task_uid)
            ).scalar_one_or_none()
            if row is None:
                return None
            return str(row)

    def exists(self, *, task_uid: str) -> bool:
        self.ensure()
        with db_session_context() as db:
            row = db.execute(select(Task.id).where(Task.task_uid == task_uid)).scalar_one_or_none()
            return row is not None

    def list_task_rows(
        self,
        *,
        username: Optional[str] = None,
        limit: int = 500,
    ) -> list[dict[str, Optional[str]]]:
        self.ensure()
        clean_username = username.strip() if username else None
        with db_session_context() as db:
            stmt = (
                select(Task.task_uid, User.username)
                .select_from(Task)
                .join(User, Task.user_id == User.id, isouter=True)
                .order_by(Task.created_at.desc())
                .limit(max(1, min(limit, 2000)))
            )
            if clean_username:
                stmt = stmt.where(User.username == clean_username)

            rows = db.execute(stmt).all()
            return [
                {
                    "task_uid": str(task_uid),
                    "username": str(owner) if owner is not None else None,
                }
                for task_uid, owner in rows
            ]
