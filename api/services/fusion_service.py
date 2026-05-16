from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Sequence

from sqlalchemy import select

from api.database import Task, db_session_context


_DIGITS_RE = re.compile(r"(\d+)")


def _frame_sort_key(name: str) -> tuple[int, str]:
    base = name.rsplit("/", 1)[-1]
    m = _DIGITS_RE.search(base)
    if m:
        return (int(m.group(1)), base)
    return (10**12, base)


class FusionService:
    def __init__(self, *, data_dir: Path, tasks_dir: Path, uploads_dir: Path, masks_dir: Path, results_dir: Path, logger) -> None:
        self._data_dir = data_dir
        self._tasks_dir = tasks_dir
        self._uploads_dir = uploads_dir
        self._masks_dir = masks_dir
        self._results_dir = results_dir
        self._logger = logger

    def _task_json_path(self, task_id: str) -> Path:
        return self._tasks_dir / task_id / "task.json"

    def _load_task_payload(self, task_id: str) -> dict:
        p = self._task_json_path(task_id)
        if not p.exists():
            raise FileNotFoundError(f"task not found: {task_id}")
        try:
            payload = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            raise RuntimeError(f"task payload parse failed: {task_id}") from exc
        if not isinstance(payload, dict):
            raise RuntimeError(f"invalid task payload: {task_id}")
        return payload

    def _find_upload_path(self, file_id: str) -> Path:
        matches = list(self._uploads_dir.glob(f"{file_id}__*"))
        if not matches:
            raise FileNotFoundError(f"source upload not found: {file_id}")
        return matches[0]

    def _resolve_file_id(self, *, task_id: str, payload: dict) -> str:
        raw = str(payload.get("file_id", "")).strip()
        if raw:
            return raw

        with db_session_context() as db:
            input_path = db.execute(select(Task.input_path).where(Task.task_uid == task_id)).scalar_one_or_none()

        if input_path:
            base = Path(str(input_path)).name
            if "__" in base:
                candidate = base.split("__", 1)[0].strip()
                if candidate:
                    return candidate

        raise ValueError(f"cannot resolve source file for task: {task_id}")

    def _build_cache_key(self, task_ids: Sequence[str]) -> str:
        parts: list[str] = []
        for task_id in task_ids:
            mask_zip = self._masks_dir / f"{task_id}.zip"
            if not mask_zip.exists():
                raise FileNotFoundError(f"mask zip not found: {task_id}")
            stat = mask_zip.stat()
            parts.append(f"{task_id}:{stat.st_size}:{stat.st_mtime_ns}")
        raw = "|".join(parts)
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]

    def _extract_zip_as_sequence(self, zip_path: Path, out_dir: Path) -> int:
        out_dir.mkdir(parents=True, exist_ok=True)
        names: list[str] = []
        with zipfile.ZipFile(zip_path, "r") as zf:
            for name in zf.namelist():
                low = name.lower()
                if low.endswith(".png") and not low.endswith("/"):
                    names.append(name)
            names.sort(key=_frame_sort_key)
            for i, name in enumerate(names, start=1):
                target = out_dir / f"{i:06d}.png"
                target.write_bytes(zf.read(name))
        return len(names)

    def _build_filter_complex(self, mask_inputs: int) -> str:
        if mask_inputs < 2:
            raise ValueError("need at least two mask streams")

        lines: list[str] = []
        for i in range(mask_inputs):
            idx = i + 1
            lines.append(f"[{idx}:v][0:v]scale2ref=flags=neighbor[m{idx}s][vref{idx}]")
            lines.append(f"[vref{idx}]nullsink")
            lines.append(f"[m{idx}s]format=gray[m{idx}]")

        current = "m1"
        for i in range(2, mask_inputs + 1):
            out = f"mi{i}"
            lines.append(f"[{current}][m{i}]blend=all_mode=multiply[{out}]")
            current = out

        lines.append(f"[{current}]format=gray[mgray]")
        lines.append("[mgray]split=2[mgray_rgb][mgray_alpha]")
        lines.append("[mgray_rgb]format=rgb24[mrgb]")
        lines.append("[mrgb][mgray_alpha]alphamerge[mrgba]")
        lines.append("[mrgba]colorchannelmixer=rr=0:rg=0:rb=0:gr=0:gg=1:gb=0:br=0:bg=0:bb=0:aa=0.5[maskov]")
        lines.append("[0:v][maskov]overlay=shortest=1[outv]")
        return ";".join(lines)

    def _resolve_ffmpeg_executable(self) -> str:
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            return ffmpeg
        try:
            import imageio_ffmpeg  # type: ignore

            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
            if ffmpeg and Path(ffmpeg).exists():
                return ffmpeg
        except Exception:
            pass
        raise RuntimeError("ffmpeg not found in PATH; install ffmpeg or pip install imageio-ffmpeg")

    def _run_ffmpeg(self, *, source_video: Path, mask_dirs: Sequence[Path], fps: float, output_path: Path) -> None:
        ffmpeg = self._resolve_ffmpeg_executable()
        filter_complex = self._build_filter_complex(len(mask_dirs))

        cmd: list[str] = [ffmpeg, "-y", "-i", str(source_video)]
        for d in mask_dirs:
            cmd += ["-framerate", f"{fps:.6f}", "-i", str(d / "%06d.png")]

        cmd += [
            "-filter_complex",
            filter_complex,
            "-map",
            "[outv]",
            "-map",
            "0:a?",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            str(output_path),
        ]

        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            tail = (proc.stderr or "")[-4000:]
            raise RuntimeError(f"ffmpeg failed: {tail}")

    def get_or_build_intersection_video(self, *, task_ids: Sequence[str]) -> Path:
        uniq = [str(x).strip() for x in task_ids if str(x).strip()]
        if len(uniq) < 2:
            raise ValueError("need at least two task ids")

        payloads = [self._load_task_payload(task_id) for task_id in uniq]
        file_ids = {self._resolve_file_id(task_id=task_id, payload=payload) for task_id, payload in zip(uniq, payloads)}
        if len(file_ids) != 1:
            raise ValueError("tasks must belong to the same source video")

        for task_id, payload in zip(uniq, payloads):
            status = str(payload.get("status", "")).strip().lower()
            if status != "completed":
                raise ValueError(f"task is not completed: {task_id}")
            if not (self._masks_dir / f"{task_id}.zip").exists():
                raise FileNotFoundError(f"mask zip not found: {task_id}")

        file_id = next(iter(file_ids))
        source_video = self._find_upload_path(file_id)

        fps_candidates = []
        for payload in payloads:
            raw_fps = payload.get("fps")
            try:
                f = float(raw_fps)
            except Exception:
                continue
            if f > 0:
                fps_candidates.append(f)
        fps = fps_candidates[0] if fps_candidates else 25.0

        cache_key = self._build_cache_key(uniq)
        fusion_name = f"fusion_intersection_{cache_key}.mp4"
        output_path = self._results_dir / fusion_name
        if output_path.exists() and output_path.stat().st_size > 0:
            return output_path

        tmp_root = Path(tempfile.mkdtemp(prefix="fusion_", dir=str(self._data_dir)))
        try:
            mask_dirs: list[Path] = []
            min_count: int | None = None

            for i, task_id in enumerate(uniq, start=1):
                mask_zip = self._masks_dir / f"{task_id}.zip"
                out_dir = tmp_root / f"m{i}"
                count = self._extract_zip_as_sequence(mask_zip, out_dir)
                if count <= 0:
                    raise RuntimeError(f"no png masks in archive: {task_id}")
                if min_count is None or count < min_count:
                    min_count = count
                mask_dirs.append(out_dir)

            if not min_count or min_count <= 0:
                raise RuntimeError("no valid mask frames")

            for d in mask_dirs:
                for p in sorted(d.glob("*.png")):
                    idx = int(p.stem)
                    if idx > min_count:
                        p.unlink(missing_ok=True)

            self._results_dir.mkdir(parents=True, exist_ok=True)
            temp_output = tmp_root / fusion_name
            self._run_ffmpeg(source_video=source_video, mask_dirs=mask_dirs, fps=fps, output_path=temp_output)
            output_path.write_bytes(temp_output.read_bytes())
            return output_path
        finally:
            shutil.rmtree(tmp_root, ignore_errors=True)
