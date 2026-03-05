from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    uploads_dir: Path
    tasks_dir: Path
    results_dir: Path
    masks_dir: Path
    models_dir: Path
    logs_dir: Path
    algorithms_file: Path
    admin_password: str
    admin_jwt_secret: str
    admin_jwt_issuer: str
    # Conda env paths (local inference)
    env_combo: str
    env_avsegformer: str
    env_vct: str
    # Remote inference config
    remote_inference_url: str
    remote_inference_token: str


def get_settings() -> Settings:
    root = Path(__file__).resolve().parent
    data_dir = Path(os.getenv("AVS_DATA_DIR", str(root / "data"))).resolve()

    uploads_dir = data_dir / "uploads"
    tasks_dir = data_dir / "tasks"
    results_dir = data_dir / "results"
    masks_dir = data_dir / "masks"
    models_dir = data_dir / "models"
    logs_dir = data_dir / "logs"

    for p in [uploads_dir, tasks_dir, results_dir, masks_dir, models_dir, logs_dir]:
        p.mkdir(parents=True, exist_ok=True)

    algorithms_file = data_dir / "algorithms.json"

    admin_password = os.getenv("AVS_ADMIN_PASSWORD", "admin")
    admin_jwt_secret = os.getenv("AVS_ADMIN_JWT_SECRET", "dev-secret-change")
    admin_jwt_issuer = os.getenv("AVS_ADMIN_JWT_ISS", "avs-system")

    # Conda environments
    env_combo = os.getenv("AVS_ENV_COMBO", "")
    env_avsegformer = os.getenv("AVS_ENV_AVSEGFORMER", "")
    env_vct = os.getenv("AVS_ENV_VCT", "")
    
    # Remote inference
    remote_inference_url = os.getenv("AVS_REMOTE_URL", "") # e.g., https://your-colab-url.ngrok.io
    remote_inference_token = os.getenv("AVS_REMOTE_TOKEN", "")

    return Settings(
        data_dir=data_dir,
        uploads_dir=uploads_dir,
        tasks_dir=tasks_dir,
        results_dir=results_dir,
        masks_dir=masks_dir,
        models_dir=models_dir,
        logs_dir=logs_dir,
        algorithms_file=algorithms_file,
        admin_password=admin_password,
        admin_jwt_secret=admin_jwt_secret,
        admin_jwt_issuer=admin_jwt_issuer,
        env_combo=env_combo,
        env_avsegformer=env_avsegformer,
        env_vct=env_vct,
        remote_inference_url=remote_inference_url,
        remote_inference_token=remote_inference_token,
    )
