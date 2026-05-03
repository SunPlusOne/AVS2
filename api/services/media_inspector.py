from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class MediaMetadata:
    duration_seconds: Optional[float]
    width: Optional[int]
    height: Optional[int]
    fps: Optional[float]
    total_frames: Optional[int]
    audio_energy: Optional[float]


def _parse_fps(raw: str) -> Optional[float]:
    value = str(raw or "").strip()
    if not value:
        return None
    if "/" in value:
        left, right = value.split("/", 1)
        try:
            num = float(left)
            den = float(right)
            if den == 0:
                return None
            fps = num / den
            if not math.isfinite(fps) or fps <= 0:
                return None
            return fps
        except Exception:
            return None
    try:
        fps = float(value)
        if not math.isfinite(fps) or fps <= 0:
            return None
        return fps
    except Exception:
        return None


def _to_float(raw: object) -> Optional[float]:
    if raw is None:
        return None
    try:
        value = float(raw)
    except Exception:
        return None
    if not math.isfinite(value):
        return None
    return value


def _to_int(raw: object) -> Optional[int]:
    if raw is None:
        return None
    try:
        value = int(raw)
    except Exception:
        return None
    if value <= 0:
        return None
    return value


def _extract_audio_energy(video_path: Path) -> Optional[float]:
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        return None

    cmd = [
        ffmpeg_bin,
        "-v",
        "error",
        "-i",
        str(video_path),
        "-map",
        "0:a:0",
        "-af",
        "volumedetect",
        "-f",
        "null",
        "-",
    ]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except Exception:
        return None

    stderr = str(proc.stderr or "")
    match = re.search(r"mean_volume:\s*(-?[0-9]+(?:\.[0-9]+)?)\s*dB", stderr)
    if not match:
        return None

    try:
        mean_db = float(match.group(1))
    except Exception:
        return None

    # Map [-60dB, 0dB] to [0, 1].
    energy = (mean_db + 60.0) / 60.0
    return max(0.0, min(1.0, energy))


def probe_video_metadata(video_path: Path) -> MediaMetadata:
    ffprobe_bin = shutil.which("ffprobe")
    duration_seconds: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None
    total_frames: Optional[int] = None

    if ffprobe_bin:
        cmd = [
            ffprobe_bin,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(video_path),
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            if proc.returncode == 0 and proc.stdout:
                payload = json.loads(proc.stdout)
                streams = payload.get("streams", [])
                fmt = payload.get("format", {})

                video_stream = None
                for stream in streams:
                    if str(stream.get("codec_type", "")).lower() == "video":
                        video_stream = stream
                        break

                if video_stream is not None:
                    width = _to_int(video_stream.get("width"))
                    height = _to_int(video_stream.get("height"))
                    fps = _parse_fps(str(video_stream.get("avg_frame_rate") or video_stream.get("r_frame_rate") or ""))
                    total_frames = _to_int(video_stream.get("nb_frames"))
                    duration_seconds = _to_float(video_stream.get("duration"))

                if duration_seconds is None:
                    duration_seconds = _to_float(fmt.get("duration"))

                if total_frames is None and duration_seconds and fps:
                    total_frames = max(1, int(round(duration_seconds * fps)))
        except Exception:
            pass

    audio_energy = _extract_audio_energy(video_path)

    return MediaMetadata(
        duration_seconds=duration_seconds,
        width=width,
        height=height,
        fps=fps,
        total_frames=total_frames,
        audio_energy=audio_energy,
    )
