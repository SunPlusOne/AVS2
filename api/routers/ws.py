from __future__ import annotations

from fastapi import APIRouter, Depends, WebSocket

from api.deps import get_task_manager, get_ws_manager
from api.services.task_manager import TaskManager
from api.services.ws_manager import WSManager


router = APIRouter()


@router.websocket("/ws/tasks/{task_id}/progress")
async def ws_progress(
    task_id: str,
    websocket: WebSocket,
    ws: WSManager = Depends(get_ws_manager),
    manager: TaskManager = Depends(get_task_manager),
):
    await ws.connect(task_id, websocket)
    try:
        try:
            current = await manager.get(task_id)
            await websocket.send_json(current.model_dump(mode="json"))
        except Exception:
            pass
        while True:
            await websocket.receive_text()
    except Exception:
        pass
    finally:
        await ws.disconnect(task_id, websocket)
