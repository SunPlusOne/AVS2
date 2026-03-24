from __future__ import annotations

from fastapi import APIRouter, Depends

from api.deps import get_algorithms_repo
from api.services.auth import user_guard
from api.services.algorithms_repo import AlgorithmsRepo


router = APIRouter()


@router.get("/algorithms")
async def list_algorithms(repo: AlgorithmsRepo = Depends(get_algorithms_repo), ok=Depends(user_guard)):
    return repo.list_all()
