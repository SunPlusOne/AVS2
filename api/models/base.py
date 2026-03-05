from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable


class BaseAVSModel(ABC):
    name: str

    @abstractmethod
    def load_weights(self, weight_path: str, device: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def infer(self, *, total_frames: int) -> Iterable[bytes]:
        raise NotImplementedError

