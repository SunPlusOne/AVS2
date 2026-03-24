from __future__ import annotations

from fastapi import Request

from api.config import Settings
from api.services.algorithms_repo import AlgorithmsRepo
from api.services.logs_repo import LogsRepo
from api.services.task_manager import TaskManager
from api.services.tasks_repo import TasksRepo
from api.services.task_runner import TaskRunner
from api.services.users_repo import UsersRepo
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


def get_users_repo(request: Request) -> UsersRepo:
    return request.app.state.users_repo


def get_logs_repo(request: Request) -> LogsRepo:
    return request.app.state.logs_repo


def get_tasks_repo(request: Request) -> TasksRepo:
    return request.app.state.tasks_repo

