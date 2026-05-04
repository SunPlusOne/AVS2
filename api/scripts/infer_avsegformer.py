import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import wave
import zipfile
from pathlib import Path
from typing import List, Tuple

import cv2
import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from api.services.metrics_estimator import build_processing_metrics, estimate_metrics
from api.models.device_utils import (
    format_runtime_info,
    get_torch_runtime_info,
    model_parameter_device,
    resolve_runtime_device,
)

try:
    from api.models.avsegformer_adapter import (
        AVSEGFORMER_ROOT,
        AvSegFormerAdapter,
        detect_backbone_from_checkpoint,
    )
except Exception as exc:
    print(f"Error importing AvSegFormerAdapter: {exc}")
    traceback.print_exc()
    sys.exit(1)

try:
    from model.vggish import vggish_input
except Exception:
    vggish_input = None


def resolve_ffmpeg_exe() -> str:
    ffmpeg_bin = shutil.which("ffmpeg")
    if ffmpeg_bin:
        return ffmpeg_bin
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return ""


def detect_subset(weight_path: Path, subset_arg: str = "") -> str:
    subset = (subset_arg or os.getenv("AVS_AVSEGFORMER_SUBSET", "")).strip().lower()
    if subset in {"s4", "ms3"}:
        return subset

    weight_lower = str(weight_path).lower()
    if "ms3" in weight_lower:
        return "ms3"
    return "s4"


def choose_config_path(weight_path: Path, config_path_arg: str = "", subset_arg: str = "") -> Tuple[Path, str, str]:
    if config_path_arg:
        cfg = Path(config_path_arg).expanduser()
        if not cfg.is_absolute():
            cfg = (AVSEGFORMER_ROOT / cfg).resolve()
        subset = detect_subset(weight_path=weight_path, subset_arg=subset_arg)
        backbone = detect_backbone_from_checkpoint(str(weight_path))
        return cfg, subset, backbone

    subset = detect_subset(weight_path=weight_path, subset_arg=subset_arg)
    backbone = detect_backbone_from_checkpoint(str(weight_path))

    mapping = {
        ("s4", "pvt2"): AVSEGFORMER_ROOT / "config" / "s4" / "AVSegFormer_pvt2_s4.py",
        ("s4", "res50"): AVSEGFORMER_ROOT / "config" / "s4" / "AVSegFormer_res50_s4.py",
        ("ms3", "pvt2"): AVSEGFORMER_ROOT / "config" / "ms3" / "AVSegFormer_pvt2_ms3.py",
        ("ms3", "res50"): AVSEGFORMER_ROOT / "config" / "ms3" / "AVSegFormer_res50_ms3.py",
    }
    return mapping[(subset, backbone)], subset, backbone


def extract_frames(video_path: str) -> Tuple[List[np.ndarray], float]:
    cap = cv2.VideoCapture(video_path)
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    if fps <= 1e-6:
        fps = 25.0

    frames: List[np.ndarray] = []
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    cap.release()
    return frames, fps


def _read_wav_mono_float32(wav_path: Path) -> Tuple[np.ndarray, int]:
    with wave.open(str(wav_path), "rb") as wf:
        sample_rate = int(wf.getframerate())
        channels = int(wf.getnchannels())
        sample_width = int(wf.getsampwidth())
        nframes = int(wf.getnframes())
        pcm = wf.readframes(nframes)

    if sample_width == 1:
        data = np.frombuffer(pcm, dtype=np.uint8).astype(np.float32)
        data = (data - 128.0) / 128.0
    elif sample_width == 2:
        data = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    elif sample_width == 4:
        data = np.frombuffer(pcm, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        raise RuntimeError(f"Unsupported wav sample width: {sample_width}")

    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)

    return data, sample_rate


def _align_audio_examples(examples: np.ndarray, num_frames: int) -> np.ndarray:
    if num_frames <= 0:
        return np.zeros((0, 1, 96, 64), dtype=np.float32)
    if examples.size == 0:
        return np.zeros((num_frames, 1, 96, 64), dtype=np.float32)
    if examples.ndim == 3:
        examples = examples[:, None, :, :]

    total = int(examples.shape[0])
    if total == num_frames:
        return examples.astype(np.float32)

    idx = np.linspace(0, max(total - 1, 0), num_frames).round().astype(np.int64)
    idx = np.clip(idx, 0, max(total - 1, 0))
    return examples[idx].astype(np.float32)


def build_audio_feature(video_path: str, num_frames: int) -> np.ndarray:
    zero_fallback = np.zeros((num_frames, 1, 96, 64), dtype=np.float32)

    if vggish_input is None:
        print("Warning: vggish_input import failed, using zero audio feature")
        return zero_fallback

    ffmpeg_bin = resolve_ffmpeg_exe()
    if not ffmpeg_bin:
        print("Warning: ffmpeg not found, using zero audio feature")
        return zero_fallback

    tmp_wav = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
            tmp_wav = Path(handle.name)

        cmd = [
            ffmpeg_bin,
            "-y",
            "-i",
            video_path,
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            str(tmp_wav),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0 or not tmp_wav.exists() or tmp_wav.stat().st_size == 0:
            print("Warning: ffmpeg audio extraction failed, using zero audio feature")
            return zero_fallback

        waveform, sample_rate = _read_wav_mono_float32(tmp_wav)
        examples = vggish_input.waveform_to_examples(waveform, sample_rate, return_tensor=False)
        aligned = _align_audio_examples(np.asarray(examples), num_frames)
        print(f"Audio feature prepared: {aligned.shape}")
        return aligned
    except Exception as exc:
        print(f"Warning: audio feature build failed ({exc}), using zero audio feature")
        return zero_fallback
    finally:
        if tmp_wav and tmp_wav.exists():
            try:
                os.remove(tmp_wav)
            except OSError:
                pass


def transcode_browser_mp4(overlay_mp4: Path, source_video: str, out_mp4: Path) -> bool:
    ffmpeg_bin = resolve_ffmpeg_exe()
    if not ffmpeg_bin:
        return False

    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg_bin,
        "-y",
        "-i",
        str(overlay_mp4),
        "-i",
        str(source_video),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0?",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        "-c:a",
        "aac",
        "-shortest",
        str(out_mp4),
    ]

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not out_mp4.exists() or out_mp4.stat().st_size == 0:
        print("Warning: ffmpeg transcode failed, fallback to mp4v output")
        return False
    return True


def _decode_mask(mask_bytes: bytes, target_size: Tuple[int, int]) -> np.ndarray:
    raw = np.frombuffer(mask_bytes, dtype=np.uint8)
    mask = cv2.imdecode(raw, cv2.IMREAD_GRAYSCALE)
    if mask is None:
        return np.zeros((target_size[1], target_size[0]), dtype=np.uint8)
    if (mask.shape[1], mask.shape[0]) != target_size:
        mask = cv2.resize(mask, target_size, interpolation=cv2.INTER_NEAREST)
    return mask


def render_overlay_video(
    frames_rgb: List[np.ndarray],
    masks_bytes: List[bytes],
    out_path: Path,
    fps: float,
) -> Tuple[int, List[float]]:
    if not frames_rgb:
        raise RuntimeError("No frames extracted from input video")

    height, width = frames_rgb[0].shape[:2]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    if not writer.isOpened():
        raise RuntimeError(f"Failed to open video writer: {out_path}")

    non_empty_masks = 0
    coverage_pct_by_frame: List[float] = []
    for idx, frame_rgb in enumerate(frames_rgb):
        frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
        frame_cov = 0.0
        if idx < len(masks_bytes):
            mask = _decode_mask(masks_bytes[idx], (width, height))
            mask_bool = mask > 127
            frame_cov = float(mask_bool.mean() * 100.0)
            if np.any(mask_bool):
                non_empty_masks += 1

                red_layer = np.zeros_like(frame_bgr)
                red_layer[:, :, 2] = 255
                frame_bgr = np.where(
                    mask_bool[:, :, None],
                    cv2.addWeighted(frame_bgr, 0.4, red_layer, 0.6, 0.0),
                    frame_bgr,
                )

                contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                cv2.drawContours(frame_bgr, contours, -1, (0, 255, 255), 2)

        coverage_pct_by_frame.append(round(frame_cov, 2))
        writer.write(frame_bgr)

    writer.release()
    return non_empty_masks, coverage_pct_by_frame


def main() -> None:
    started = time.time()
    parser = argparse.ArgumentParser(description="Run AVSegFormer inference")
    parser.add_argument("--task_id", required=True, help="Task ID")
    parser.add_argument("--file_id", required=True, help="Uploaded file ID")
    parser.add_argument("--weight_path", required=True, help="Path to model weights")
    parser.add_argument("--uploads_dir", required=True, help="Uploads directory")
    parser.add_argument("--results_dir", required=True, help="Results directory")
    parser.add_argument("--masks_dir", required=True, help="Masks directory")
    parser.add_argument("--config_path", default="", help="Optional AVSegFormer config path")
    parser.add_argument("--subset", default="", help="Subset in {s4, ms3}")
    args = parser.parse_args()

    weight_path = Path(args.weight_path).expanduser()
    if not weight_path.is_file():
        print(f"Error: weight file not found: {weight_path}")
        sys.exit(1)

    runtime_device = resolve_runtime_device()
    runtime_info = get_torch_runtime_info(runtime_device)
    print(f"[runtime] {format_runtime_info(runtime_info)}")

    config_path, subset, backbone = choose_config_path(
        weight_path=weight_path,
        config_path_arg=args.config_path,
        subset_arg=args.subset,
    )
    if not config_path.is_file():
        print(f"Error: AVSegFormer config not found: {config_path}")
        sys.exit(1)

    uploads_dir = Path(args.uploads_dir)
    results_dir = Path(args.results_dir)
    masks_dir = Path(args.masks_dir)

    matches = list(uploads_dir.glob(f"{args.file_id}__*"))
    if not matches:
        print(f"Error: File {args.file_id} not found")
        sys.exit(1)
    video_path = str(matches[0])

    print(f"Loading AVSegFormer model from {weight_path} with config {config_path}...")
    try:
        adapter = AvSegFormerAdapter(config_path=str(config_path))
        adapter.load_weights(str(weight_path), device=runtime_device)

        model_dev = model_parameter_device(adapter.model)
        print(f"[avsegformer] loaded_model_device={model_dev}")
        if runtime_device.startswith("cuda") and not model_dev.startswith("cuda"):
            raise RuntimeError(
                "AVSegFormer model is not on CUDA after load. "
                f"expected={runtime_device}, actual={model_dev}"
            )
    except Exception as exc:
        print(f"Failed to load model: {exc}")
        traceback.print_exc()
        sys.exit(1)

    print(f"Extracting frames from {video_path}...")
    frames, fps = extract_frames(video_path)
    audio_feat = build_audio_feature(video_path, len(frames))

    print(f"Running AVSegFormer inference on {len(frames)} frames...")
    masks_bytes: List[bytes] = []
    try:
        for idx, mask_png in enumerate(adapter.infer(frames, audio_feat)):
            masks_bytes.append(mask_png)
            if idx % 10 == 0:
                print(f"Processed {idx}/{len(frames)} frames")
    except Exception as exc:
        print(f"Inference error: {exc}")
        traceback.print_exc()
        sys.exit(1)

    masks_zip_path = masks_dir / f"{args.task_id}.zip"
    print(f"Saving masks to {masks_zip_path}...")
    with zipfile.ZipFile(masks_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for idx, mask_data in enumerate(masks_bytes):
            zf.writestr(f"mask_{idx + 1:04d}.png", mask_data)

    result_path = results_dir / f"{args.task_id}.mp4"
    overlay_tmp_path = results_dir / f"{args.task_id}.overlay_tmp.mp4"
    non_empty_masks, coverage_pct_by_frame = render_overlay_video(frames, masks_bytes, overlay_tmp_path, fps)

    if transcode_browser_mp4(overlay_tmp_path, video_path, result_path):
        try:
            os.remove(overlay_tmp_path)
        except OSError:
            pass
        print(f"Overlay video saved (h264): {result_path}, non-empty masks: {non_empty_masks}/{len(frames)}")
    else:
        if result_path.exists():
            result_path.unlink()
        overlay_tmp_path.rename(result_path)
        print(f"Overlay video saved (mp4v fallback): {result_path}, non-empty masks: {non_empty_masks}/{len(frames)}")

    report_path = results_dir / f"{args.task_id}.report.json"
    total_ms = int((time.time() - started) * 1000)
    processing = build_processing_metrics(total_ms, len(frames))
    metrics = estimate_metrics(
        algorithm="avsegformer",
        subset=subset,
        coverage_pct_by_frame=coverage_pct_by_frame,
    )
    report = {
        "task_id": args.task_id,
        "algorithm": "avsegformer",
        "subset": subset,
        "backbone": backbone,
        "frames": len(frames),
        "fps": round(float(fps), 3) if fps else None,
        "duration_seconds": round(float(len(frames) / fps), 3) if fps else None,
        "width": int(frames[0].shape[1]) if frames else None,
        "height": int(frames[0].shape[0]) if frames else None,
        "metrics": metrics,
        "processing": {
            "total_ms": processing["total_inference_ms"],
            "avg_frame_ms": processing["avg_frame_ms"],
            "processed_frames": processing["processed_frames"],
        },
        "mask_coverage_pct_by_frame": coverage_pct_by_frame,
        "note": f"AVSegFormer inference done with config={config_path.name}; 指标为论文固定值。",
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Done.")


if __name__ == "__main__":
    main()