from __future__ import annotations

from fastapi import Request

from api.config import Settings
from api.services.algorithms_repo import AlgorithmsRepo
from api.services.task_manager import TaskManager
from api.services.task_runner import TaskRunner
from api.services.ws_manager import WSManager


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_algorithms_repo(request: Request) -> AlgorithmsRepo:
    return request.app.state.algorithms_repo


def get_ws_manager(request: Request) -> WSManager:
    return request.app.state.ws_manager


def get_task_manager(request: Request) -> TaskManager:
    return request.app.state.task_manager


def get_task_runner(request: Request) -> TaskRunner:
    return request.app.state.task_runner

