from __future__ import annotations

import time
from typing import Iterable

from api.models.base import BaseAVSModel


class PlaceholderModel(BaseAVSModel):
    def __init__(self, name: str) -> None:
        self.name = name

    def load_weights(self, weight_path: str, device: str) -> None:
        return

    def infer(self, *, total_frames: int) -> Iterable[bytes]:
        for _ in range(total_frames):
            time.sleep(0.02)
            yield b""

