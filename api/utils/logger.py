from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_logger(log_file: Path) -> logging.Logger:
    logger = logging.getLogger("avs")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_file, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    return logger


def log_json(logger: logging.Logger, level: str, message: str, extra: dict[str, Any] | None = None) -> None:
    payload: dict[str, Any] = {"ts": _ts(), "level": level, "message": message}
    if extra:
        payload.update(extra)
    line = json.dumps(payload, ensure_ascii=False)
    if level.upper() == "ERROR":
        logger.error(line)
    elif level.upper() == "WARNING":
        logger.warning(line)
    else:
        logger.info(line)

