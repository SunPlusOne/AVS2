from __future__ import annotations

from fastapi import APIRouter, Depends, WebSocket
from starlette.websockets import WebSocket as StarletteWebSocket

from api.deps import get_task_manager, get_ws_manager
from api.services.task_manager import TaskManager
from api.services.ws_manager import WSManager


router = APIRouter()


@router.websocket("/ws/tasks/{task_id}/progress")
async def ws_progress(
    task_id: str,
    websocket: WebSocket,
):
    # Manually resolve dependencies because WebSocket routes don't support Request-based Depends well in all versions
    # or the Request object is different.
    # The 'websocket' object itself is a Request-like object (HTTPConnection).
    
    # Access app state directly from websocket
    ws_manager: WSManager = websocket.app.state.ws_manager
    task_manager: TaskManager = websocket.app.state.task_manager
    
    await ws_manager.connect(task_id, websocket)
    try:
        try:
            current = await task_manager.get(task_id)
            await websocket.send_json(current.model_dump(mode="json"))
        except Exception:
            pass
        while True:
            await websocket.receive_text()
    except Exception:
        pass
    finally:
        await ws_manager.disconnect(task_id, websocket)
