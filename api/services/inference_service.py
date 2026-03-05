from __future__ import annotations

import json
import shutil
import time
import zipfile
import subprocess
import os
import requests
from datetime import datetime, timezone
from pathlib import Path

from api.models.placeholder import PlaceholderModel
from api.utils.logger import log_json
from api.config import get_settings


_ONE_BY_ONE_PNG = bytes(
    [
        0x89,
        0x50,
        0x4E,
        0x47,
        0x0D,
        0x0A,
        0x1A,
        0x0A,
        0x00,
        0x00,
        0x00,
        0x0D,
        0x49,
        0x48,
        0x44,
        0x52,
        0x00,
        0x00,
        0x00,
        0x01,
        0x00,
        0x00,
        0x00,
        0x01,
        0x08,
        0x06,
        0x00,
        0x00,
        0x00,
        0x1F,
        0x15,
        0xC4,
        0x89,
        0x00,
        0x00,
        0x00,
        0x0A,
        0x49,
        0x44,
        0x41,
        0x54,
        0x78,
        0x9C,
        0x63,
        0x00,
        0x01,
        0x00,
        0x00,
        0x05,
        0x00,
        0x01,
        0x0D,
        0x0A,
        0x2D,
        0xB4,
        0x00,
        0x00,
        0x00,
        0x00,
        0x49,
        0x45,
        0x4E,
        0x44,
        0xAE,
        0x42,
        0x60,
        0x82,
    ]
)


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


class InferenceService:
    def __init__(self, uploads_dir: Path, results_dir: Path, masks_dir: Path, logger) -> None:
        self._uploads_dir = uploads_dir
        self._results_dir = results_dir
        self._masks_dir = masks_dir
        self._logger = logger

    def _find_upload(self, file_id: str) -> Path:
        matches = list(self._uploads_dir.glob(f"{file_id}__*"))
        if not matches:
            raise FileNotFoundError(file_id)
        return matches[0]

    def run_placeholder(self, *, task_id: str, file_id: str, algorithm: str) -> dict[str, str]:
        upload_path = self._find_upload(file_id)
        self._results_dir.mkdir(parents=True, exist_ok=True)
        self._masks_dir.mkdir(parents=True, exist_ok=True)

        result_path = self._results_dir / f"{task_id}.mp4"
        masks_zip_path = self._masks_dir / f"{task_id}.zip"
        report_path = self._results_dir / f"{task_id}.report.json"

        shutil.copyfile(upload_path, result_path)

        with zipfile.ZipFile(masks_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for i in range(1, 11):
                zf.writestr(f"mask_{i:04d}.png", _ONE_BY_ONE_PNG)

        report = {
            "task_id": task_id,
            "algorithm": algorithm,
            "frames": 0,
            "created_at": _ts(),
            "metrics": {"J&F": None},
            "note": "占位推理：待接入真实模型后输出逐帧掩码与叠加视频。",
        }
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

        log_json(self._logger, "INFO", "task_outputs_ready", {"task_id": task_id, "result": str(result_path)})
        return {
            "result_video": str(result_path),
            "masks_zip": str(masks_zip_path),
            "report": str(report_path),
        }
    
    def run_remote_inference(self, *, task_id: str, file_id: str, algorithm: str, remote_url: str, token: str) -> dict[str, str]:
        """Runs inference by calling a remote API (e.g. Colab/HuggingFace)"""
        upload_path = self._find_upload(file_id)
        self._results_dir.mkdir(parents=True, exist_ok=True)
        self._masks_dir.mkdir(parents=True, exist_ok=True)

        result_path = self._results_dir / f"{task_id}.mp4"
        masks_zip_path = self._masks_dir / f"{task_id}.zip"
        report_path = self._results_dir / f"{task_id}.report.json"

        # 1. Upload file to remote worker
        self._logger.info(f"Uploading file to remote: {remote_url}")
        try:
            with open(upload_path, "rb") as f:
                files = {"file": (upload_path.name, f)}
                # Assuming remote API has /predict endpoint
                # Payload: algorithm, etc.
                data = {"algorithm": algorithm, "task_id": task_id}
                headers = {"Authorization": f"Bearer {token}"} if token else {}
                
                resp = requests.post(f"{remote_url}/predict", files=files, data=data, headers=headers, timeout=600)
                resp.raise_for_status()
                
                # Remote should return ZIP with masks and maybe result video
                # For simplicity, assume it returns the ZIP file of masks
                
                with open(masks_zip_path, "wb") as f_out:
                    f_out.write(resp.content)
                    
        except Exception as e:
            self._logger.error(f"Remote inference failed: {e}")
            raise RuntimeError(f"Remote inference failed: {e}")

        # 2. Generate result video locally (if not returned by remote)
        # Just copy original for now (overlay needs cv2)
        shutil.copyfile(upload_path, result_path)

        report = {
            "task_id": task_id,
            "algorithm": algorithm,
            "frames": 0, # Unknown unless parsed from zip
            "created_at": _ts(),
            "metrics": {"J&F": None},
            "note": f"远程推理完成 ({remote_url})",
        }
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

        log_json(self._logger, "INFO", "task_outputs_ready", {"task_id": task_id, "result": str(result_path)})
        return {
            "result_video": str(result_path),
            "masks_zip": str(masks_zip_path),
            "report": str(report_path),
        }

    def run_inference(self, *, task_id: str, file_id: str, algorithm: str, weight_path: str) -> dict[str, str]:
        """Runs real inference via subprocess in specific Conda environment"""
        settings = get_settings()
        
        # Check if remote inference is configured
        if settings.remote_inference_url:
            return self.run_remote_inference(
                task_id=task_id, 
                file_id=file_id, 
                algorithm=algorithm, 
                remote_url=settings.remote_inference_url,
                token=settings.remote_inference_token
            )

        # Determine python executable based on algorithm
        env_path = ""
        script_path = ""
        
        if algorithm == "combo":
            env_path = settings.env_combo
            script_path = "api/scripts/infer_combo.py"
        # Add other algorithms here
        # elif algorithm == "avsegformer": ...
        
        if not env_path:
            raise ValueError(f"Conda environment for {algorithm} is not configured (AVS_ENV_{algorithm.upper()})")
            
        python_exe = os.path.join(env_path, "python.exe") if os.name == 'nt' else os.path.join(env_path, "bin", "python")
        
        if not os.path.exists(python_exe):
             # Try fallback to just "python" if env_path looks like a raw command
             # But strictly we expect a path.
             raise FileNotFoundError(f"Python executable not found at {python_exe}")

        # Construct command
        cmd = [
            python_exe,
            script_path,
            "--task_id", task_id,
            "--file_id", file_id,
            "--weight_path", weight_path,
            "--uploads_dir", str(self._uploads_dir),
            "--results_dir", str(self._results_dir),
            "--masks_dir", str(self._masks_dir),
        ]
        
        self._logger.info(f"Starting subprocess: {' '.join(cmd)}")
        
        # Run subprocess
        # We capture output to log it
        try:
            result = subprocess.run(
                cmd, 
                cwd=str(Path(__file__).resolve().parent.parent.parent), # Project root
                capture_output=True, 
                text=True, 
                check=True
            )
            self._logger.info(f"Subprocess output: {result.stdout}")
        except subprocess.CalledProcessError as e:
            self._logger.error(f"Subprocess failed: {e.stderr}")
            raise RuntimeError(f"Inference script failed: {e.stderr}")

        # If successful, the script should have created the files.
        # We verify and return paths.
        
        result_path = self._results_dir / f"{task_id}.mp4"
        masks_zip_path = self._masks_dir / f"{task_id}.zip"
        report_path = self._results_dir / f"{task_id}.report.json"
        
        if not result_path.exists() or not masks_zip_path.exists():
             raise RuntimeError("Inference script finished but output files are missing")

        log_json(self._logger, "INFO", "task_outputs_ready", {"task_id": task_id, "result": str(result_path)})
        return {
            "result_video": str(result_path),
            "masks_zip": str(masks_zip_path),
            "report": str(report_path),
        }

    def simulate_model_steps(self, algorithm: str, total_frames: int) -> None:
        model = PlaceholderModel(algorithm)
        for _ in model.infer(total_frames=total_frames):
            continue
