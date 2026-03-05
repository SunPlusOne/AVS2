from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_ALGORITHMS: list[dict[str, Any]] = [
    {
        "id": "avsegformer",
        "name": "AVSegFormer",
        "version": "builtin",
        "description": "基于 Transformer 的视听分割算法（占位权重）。",
        "input_size": "384x384",
        "enabled": True,
    },
    {
        "id": "vct",
        "name": "VCT",
        "version": "builtin",
        "description": "Vision-Centric Transformer（占位权重）。",
        "input_size": "384x384",
        "enabled": True,
    },
    {
        "id": "combo",
        "name": "COMBO",
        "version": "builtin",
        "description": "多阶双边关系融合算法（占位权重）。",
        "input_size": "384x384",
        "enabled": True,
    },
]


class AlgorithmsRepo:
    def __init__(self, file_path: Path):
        self._file_path = file_path

    def ensure(self) -> None:
        if self._file_path.exists():
            return
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        self._file_path.write_text(json.dumps(DEFAULT_ALGORITHMS, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_all(self) -> list[dict[str, Any]]:
        self.ensure()
        raw = self._file_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, list):
            return []
        return [x for x in data if isinstance(x, dict)]

    def upsert(self, algo: dict[str, Any]) -> None:
        items = self.list_all()
        idx = next((i for i, a in enumerate(items) if a.get("id") == algo.get("id")), None)
        if idx is None:
            items.append(algo)
        else:
            items[idx] = {**items[idx], **algo}
        self._file_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")

