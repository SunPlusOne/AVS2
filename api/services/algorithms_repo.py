from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import desc, select

from api.database import ModelMeta, db_session_context, init_database, utcnow


DEFAULT_ALGORITHMS: list[dict[str, Any]] = [
    {
        "id": "avsegformer",
        "name": "AVSegFormer",
        "version": "builtin",
        "description": "基于 Transformer 的视听分割算法，支持 S4/MS3 本地推理。",
        "input_size": "512x512",
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
        init_database()
        self._migrate_from_json_once()
        with db_session_context() as db:
            count = db.execute(select(ModelMeta.id).limit(1)).scalar_one_or_none()
            if count is not None:
                return
            for item in DEFAULT_ALGORITHMS:
                db.add(
                    ModelMeta(
                        algorithm_id=str(item["id"]),
                        name=str(item["name"]),
                        version=str(item.get("version") or "builtin"),
                        input_size=str(item.get("input_size") or ""),
                        description=str(item.get("description") or ""),
                        enabled=bool(item.get("enabled", True)),
                        file_path=str(item.get("weight_path") or ""),
                        uploaded_by=None,
                        created_at=utcnow(),
                    )
                )

    def _migrate_from_json_once(self) -> None:
        if not self._file_path.exists():
            return
        try:
            raw = self._file_path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except Exception:
            return
        if not isinstance(data, list):
            return

        with db_session_context() as db:
            has_rows = db.execute(select(ModelMeta.id).limit(1)).scalar_one_or_none()
            if has_rows is not None:
                return
            for item in data:
                if not isinstance(item, dict):
                    continue
                algo_id = str(item.get("id", "")).strip()
                if not algo_id:
                    continue
                db.add(
                    ModelMeta(
                        algorithm_id=algo_id,
                        name=str(item.get("name") or algo_id),
                        version=str(item.get("version") or "builtin"),
                        input_size=str(item.get("input_size") or ""),
                        description=str(item.get("description") or ""),
                        enabled=bool(item.get("enabled", True)),
                        file_path=str(item.get("weight_path") or ""),
                        uploaded_by=None,
                        created_at=utcnow(),
                    )
                )

    def list_all(self) -> list[dict[str, Any]]:
        self.ensure()
        with db_session_context() as db:
            rows = db.execute(
                select(ModelMeta).order_by(ModelMeta.algorithm_id.asc(), desc(ModelMeta.created_at))
            ).scalars().all()

        # Keep one active row per algorithm for frontend compatibility.
        latest_by_algo: dict[str, ModelMeta] = {}
        for row in rows:
            key = row.algorithm_id.strip().lower()
            if key and key not in latest_by_algo:
                latest_by_algo[key] = row

        out: list[dict[str, Any]] = []
        for row in latest_by_algo.values():
            out.append(
                {
                    "id": row.algorithm_id,
                    "name": row.name,
                    "version": row.version,
                    "description": row.description or "",
                    "input_size": row.input_size or "",
                    "enabled": bool(row.enabled),
                    "weight_path": row.file_path or "",
                }
            )
        return out

    def upsert(self, algo: dict[str, Any], uploaded_by: Optional[int] = None) -> int:
        self.ensure()
        algorithm_id = str(algo.get("id") or algo.get("algorithm_id") or "").strip()
        if not algorithm_id:
            raise ValueError("algorithm id required")

        with db_session_context() as db:
            existing = db.execute(
                select(ModelMeta)
                .where(ModelMeta.algorithm_id == algorithm_id)
                .order_by(desc(ModelMeta.created_at))
            ).scalars().first()

            version = str(algo.get("version") or (existing.version if existing else "builtin"))
            row = ModelMeta(
                algorithm_id=algorithm_id,
                name=str(algo.get("name") or (existing.name if existing else algorithm_id)),
                version=version,
                description=str(algo.get("description") or (existing.description if existing else "")),
                input_size=str(algo.get("input_size") or (existing.input_size if existing else "")),
                enabled=bool(algo.get("enabled", True)),
                file_path=str(algo.get("weight_path") or (existing.file_path if existing else "")),
                uploaded_by=uploaded_by,
                created_at=utcnow(),
            )
            db.add(row)
            db.flush()
            return int(row.id)

    def find_model_id(self, algorithm_id: str) -> Optional[int]:
        self.ensure()
        key = algorithm_id.strip()
        if not key:
            return None
        with db_session_context() as db:
            row = db.execute(
                select(ModelMeta)
                .where(ModelMeta.algorithm_id == key)
                .order_by(desc(ModelMeta.created_at))
            ).scalars().first()
            if not row:
                return None
            return int(row.id)
