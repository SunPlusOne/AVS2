from __future__ import annotations

import asyncio
from typing import Any

from fastapi import WebSocket


class WSManager:
    def __init__(self) -> None:
        self._by_task: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, task_id: str, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._by_task.setdefault(task_id, set()).add(ws)

    async def disconnect(self, task_id: str, ws: WebSocket) -> None:
        async with self._lock:
            conns = self._by_task.get(task_id)
            if not conns:
                return
            conns.discard(ws)
            if not conns:
                self._by_task.pop(task_id, None)

    async def broadcast(self, task_id: str, payload: dict[str, Any]) -> None:
        async with self._lock:
            conns = list(self._by_task.get(task_id, set()))
        for ws in conns:
            try:
                await ws.send_json(payload)
            except Exception:
                await self.disconnect(task_id, ws)

