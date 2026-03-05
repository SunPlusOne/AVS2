from __future__ import annotations

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from api.config import get_settings
from api.routers import admin, algorithms, health, tasks, upload, ws
from api.services.algorithms_repo import AlgorithmsRepo
from api.services.inference_service import InferenceService
from api.services.task_manager import TaskManager
from api.services.task_runner import TaskRunner
from api.services.ws_manager import WSManager
from api.utils.logger import build_logger


def create_app() -> FastAPI:
    settings = get_settings()
    logger = build_logger(settings.logs_dir / "app.log")

    ws_manager = WSManager()
    algorithms_repo = AlgorithmsRepo(settings.algorithms_file)
    task_manager = TaskManager(settings.tasks_dir, ws_manager, logger)
    inference = InferenceService(settings.uploads_dir, settings.results_dir, settings.masks_dir, logger)
    task_runner = TaskRunner(task_manager, inference, logger)

    app = FastAPI(title="AVS System", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.settings = settings
    app.state.ws_manager = ws_manager
    app.state.algorithms_repo = algorithms_repo
    app.state.task_manager = task_manager
    app.state.task_runner = task_runner

    app.include_router(health.router, prefix="/api")
    app.include_router(upload.router, prefix="/api")
    app.include_router(algorithms.router, prefix="/api")
    app.include_router(tasks.router, prefix="/api")
    app.include_router(admin.router, prefix="/api")
    app.include_router(ws.router)

    @app.get("/")
    async def _root():
        return {
            "name": app.title,
            "version": app.version,
            "docs_url": app.docs_url,
            "redoc_url": app.redoc_url,
            "openapi_url": app.openapi_url,
            "health": "/api/health",
        }

    @app.get("/favicon.ico")
    async def _favicon():
        return Response(status_code=204)

    @app.on_event("startup")
    async def _startup():
        algorithms_repo.ensure()

    return app


app = create_app()
