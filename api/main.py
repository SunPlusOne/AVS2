from __future__ import annotations

import os
from pathlib import Path
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

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

    @app.on_event("startup")
    async def _startup():
        algorithms_repo.ensure()
        
    # --- Static Files Hosting (Frontend) ---
    # Check if 'dist' folder exists (Frontend build artifact)
    # It should be located at project_root/dist
    project_root = Path(__file__).resolve().parent.parent
    dist_dir = project_root / "dist"
    
    if dist_dir.exists() and dist_dir.is_dir():
        # Mount static assets
        app.mount("/assets", StaticFiles(directory=str(dist_dir / "assets")), name="assets")
        
        # Serve index.html for root and SPA fallback
        @app.get("/")
        async def serve_spa_root():
            return FileResponse(dist_dir / "index.html")
            
        @app.get("/{full_path:path}")
        async def serve_spa_fallback(full_path: str):
            # If path starts with /api or /ws, let FastAPI handle it (but routers are already included above, so 404)
            # If file exists in dist, serve it (e.g. favicon.svg)
            file_path = dist_dir / full_path
            if file_path.exists() and file_path.is_file():
                return FileResponse(file_path)
            
            # Otherwise return index.html for client-side routing
            return FileResponse(dist_dir / "index.html")
    else:
        # Fallback for API-only mode
        @app.get("/")
        async def _root():
            return {
                "name": app.title,
                "version": app.version,
                "docs_url": app.docs_url,
                "mode": "api_only (frontend build not found in /dist)"
            }

    return app


app = create_app()
