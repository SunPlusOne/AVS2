from __future__ import annotations

from datetime import timezone
from typing import Optional

from sqlalchemy import desc, select

from api.database import LogEntry, db_session_context, init_database, utcnow


class LogsRepo:
    def ensure(self) -> None:
        init_database()

    def add(self, *, user_id: Optional[int], action: str, ip: Optional[str]) -> None:
        if not action.strip():
            return
        self.ensure()
        with db_session_context() as db:
            db.add(
                LogEntry(
                    user_id=user_id,
                    action=action.strip(),
                    ip=(ip or "").strip() or None,
                    created_at=utcnow(),
                )
            )

    def list_latest(self, limit: int = 200) -> list[dict[str, str]]:
        self.ensure()
        max_limit = max(1, min(limit, 1000))
        with db_session_context() as db:
            rows = db.execute(
                select(LogEntry).order_by(desc(LogEntry.created_at)).limit(max_limit)
            ).scalars().all()

        out: list[dict[str, str]] = []
        for row in rows:
            created_at = row.created_at
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            out.append(
                {
                    "ts": created_at.isoformat(),
                    "level": "INFO",
                    "message": row.action,
                }
            )
        return out
