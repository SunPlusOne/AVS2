from __future__ import annotations

from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocket as StarletteWebSocket

from api.services.auth import _decode_authorized_user
from api.services.task_manager import TaskManager
from api.services.tasks_repo import TasksRepo
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
    tasks_repo: TasksRepo = websocket.app.state.tasks_repo
    settings = websocket.app.state.settings

    token = websocket.query_params.get("token")
    auth_header = websocket.headers.get("authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()

    if not token:
        await websocket.close(code=1008, reason="missing token")
        return

    try:
        ok = _decode_authorized_user(settings, token, {"admin", "user"})
    except Exception:
        await websocket.close(code=1008, reason="invalid token")
        return

    role = str(ok.get("role", ""))
    username = str(ok.get("username", ""))
    if role != "admin":
        owner = tasks_repo.get_owner_username(task_uid=task_id)
        if owner != username:
            await websocket.close(code=1008, reason="forbidden")
            return
    elif not tasks_repo.exists(task_uid=task_id):
        await websocket.close(code=1008, reason="task not found")
        return
    
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
