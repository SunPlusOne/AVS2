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
import math
from pathlib import Path
from typing import List, Tuple

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from api.services.metrics_estimator import build_processing_metrics, estimate_metrics
from api.models.device_utils import format_runtime_info, get_torch_runtime_info, resolve_runtime_device


def _resolve_avis_root() -> Path:
    env_root = os.getenv("AVS_AVIS_ROOT", "").strip()
    candidates: list[Path] = []
    if env_root:
        candidates.append(Path(env_root).expanduser())

    candidates.extend(
        [
            PROJECT_ROOT / "api" / "third_party" / "avis",
            PROJECT_ROOT / "third_party" / "avis",
            Path("/root/autodl-tmp/avis"),
            Path("/root/avis"),
        ]
    )

    for candidate in candidates:
        if (candidate / "train_net.py").is_file() and (candidate / "demo_video" / "predictor.py").is_file():
            return candidate

    searched = "\n".join(f"- {p}" for p in candidates)
    raise FileNotFoundError(
        "AVIS source not found. Set AVS_AVIS_ROOT or place avis in one of:\n"
        f"{searched}"
    )


AVIS_ROOT = _resolve_avis_root()
if str(AVIS_ROOT) not in sys.path:
    sys.path.insert(0, str(AVIS_ROOT))
if str(AVIS_ROOT / "demo_video") not in sys.path:
    sys.path.insert(0, str(AVIS_ROOT / "demo_video"))

try:
    from detectron2.config import get_cfg
    from detectron2.projects.deeplab import add_deeplab_config
    from mask2former import add_maskformer2_config
    from avism import add_avism_config
    from predictor import VideoPredictor
except Exception as exc:
    print(f"Error importing AVIS stack: {exc}")
    traceback.print_exc()
    sys.exit(1)


def resolve_ffmpeg_exe() -> str:
    ffmpeg_bin = shutil.which("ffmpeg")
    if ffmpeg_bin:
        return ffmpeg_bin
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return ""


def choose_config_path(weight_path: Path, config_path_arg: str = "") -> Path:
    if config_path_arg:
        p = Path(config_path_arg).expanduser()
        if not p.is_absolute():
            p = (AVIS_ROOT / p).resolve()
        return p

    env_cfg = os.getenv("AVS_AVIS_CONFIG", "").strip()
    if env_cfg:
        p = Path(env_cfg).expanduser()
        if not p.is_absolute():
            p = (AVIS_ROOT / p).resolve()
        return p

    # Pick config by checkpoint naming to avoid R50/Swin-L mismatch.
    weight_name = weight_path.name.lower()
    prefers_swin = "swin" in weight_name
    prefers_r50 = ("r50" in weight_name) or ("res50" in weight_name)
    prefers_in = "_in" in weight_name or "imagenet" in weight_name
    prefers_coco = "coco" in weight_name

    if prefers_swin:
        if prefers_in:
            candidates = [
                AVIS_ROOT / "configs" / "avism" / "SwinL" / "avism_SwinL_IN.yaml",
                AVIS_ROOT / "configs" / "avism" / "swinl" / "avism_SwinL_IN.yaml",
                AVIS_ROOT / "configs" / "avism" / "SwinL" / "avism_SwinL_COCO.yaml",
                AVIS_ROOT / "configs" / "avism" / "swinl" / "avism_SwinL_COCO.yaml",
            ]
        elif prefers_coco:
            candidates = [
                AVIS_ROOT / "configs" / "avism" / "SwinL" / "avism_SwinL_COCO.yaml",
                AVIS_ROOT / "configs" / "avism" / "swinl" / "avism_SwinL_COCO.yaml",
                AVIS_ROOT / "configs" / "avism" / "SwinL" / "avism_SwinL_IN.yaml",
                AVIS_ROOT / "configs" / "avism" / "swinl" / "avism_SwinL_IN.yaml",
            ]
        else:
            candidates = [
                AVIS_ROOT / "configs" / "avism" / "SwinL" / "avism_SwinL_COCO.yaml",
                AVIS_ROOT / "configs" / "avism" / "swinl" / "avism_SwinL_COCO.yaml",
                AVIS_ROOT / "configs" / "avism" / "SwinL" / "avism_SwinL_IN.yaml",
                AVIS_ROOT / "configs" / "avism" / "swinl" / "avism_SwinL_IN.yaml",
            ]
    elif prefers_r50:
        if prefers_in:
            candidates = [
                AVIS_ROOT / "configs" / "avism" / "R50" / "avism_R50_IN.yaml",
                AVIS_ROOT / "configs" / "avism" / "R50" / "avism_R50_COCO.yaml",
            ]
        elif prefers_coco:
            candidates = [
                AVIS_ROOT / "configs" / "avism" / "R50" / "avism_R50_COCO.yaml",
                AVIS_ROOT / "configs" / "avism" / "R50" / "avism_R50_IN.yaml",
            ]
        else:
            candidates = [
                AVIS_ROOT / "configs" / "avism" / "R50" / "avism_R50_COCO.yaml",
                AVIS_ROOT / "configs" / "avism" / "R50" / "avism_R50_IN.yaml",
            ]
    else:
        candidates = []

    # Global fallback order.
    candidates.extend(
        [
            AVIS_ROOT / "configs" / "avism" / "SwinL" / "avism_SwinL_COCO.yaml",
            AVIS_ROOT / "configs" / "avism" / "swinl" / "avism_SwinL_COCO.yaml",
            AVIS_ROOT / "configs" / "avism" / "avis" / "avism_SwinL_COCO.yaml",
            AVIS_ROOT / "configs" / "avism" / "R50" / "avism_R50_COCO.yaml",
            AVIS_ROOT / "configs" / "avism" / "R50" / "avism_R50_IN.yaml",
        ]
    )
    for p in candidates:
        if p.is_file():
            return p

    return candidates[0]


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
        frames.append(frame)
    cap.release()
    return frames, fps


def _get_int_env(name: str, default: int, min_value: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        val = int(raw)
        return max(val, min_value)
    except Exception:
        return default


def maybe_downsample_frames(frames_bgr: List[np.ndarray], fps: float) -> Tuple[List[np.ndarray], float, int]:
    # Safety valve for long videos / large memory footprint.
    max_frames = _get_int_env("AVS_AVIS_MAX_FRAMES", 180, 1)
    if len(frames_bgr) <= max_frames:
        return frames_bgr, fps, 1

    stride = max(1, int(math.ceil(len(frames_bgr) / float(max_frames))))
    sampled = frames_bgr[::stride]
    if sampled and sampled[-1] is not frames_bgr[-1]:
        sampled.append(frames_bgr[-1])
    adjusted_fps = max(1e-6, float(fps) / float(stride))
    print(
        f"[avis] downsample frames: {len(frames_bgr)} -> {len(sampled)} (stride={stride}, fps {fps:.3f}->{adjusted_fps:.3f})"
    )
    return sampled, adjusted_fps, stride


def maybe_resize_frames(frames_bgr: List[np.ndarray]) -> Tuple[List[np.ndarray], float]:
    # Reduce input resolution for SwinL checkpoints to avoid OOM/SIGKILL.
    max_side = _get_int_env("AVS_AVIS_MAX_SIDE", 640, 128)
    if not frames_bgr:
        return frames_bgr, 1.0

    h, w = frames_bgr[0].shape[:2]
    side = max(h, w)
    if side <= max_side:
        return frames_bgr, 1.0

    scale = float(max_side) / float(side)
    new_w = max(1, int(round(w * scale)))
    new_h = max(1, int(round(h * scale)))
    resized = [cv2.resize(f, (new_w, new_h), interpolation=cv2.INTER_AREA) for f in frames_bgr]
    print(f"[avis] resize frames: {w}x{h} -> {new_w}x{new_h} (scale={scale:.3f})")
    return resized, scale


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


def _build_chunk_embedding(chunk: np.ndarray) -> np.ndarray:
    if chunk.size == 0:
        return np.zeros((128,), dtype=np.float32)

    spec = np.abs(np.fft.rfft(chunk, n=512)).astype(np.float32)
    if spec.size == 0:
        return np.zeros((128,), dtype=np.float32)

    log_spec = np.log1p(spec)
    if log_spec.size < 128:
        repeat = int(np.ceil(128 / float(log_spec.size)))
        log_spec = np.tile(log_spec, repeat)
    feat = log_spec[:128]

    mean = float(feat.mean())
    std = float(feat.std())
    if std < 1e-6:
        std = 1.0
    return ((feat - mean) / std).astype(np.float32)


def build_audio_feature(video_path: str, num_frames: int) -> np.ndarray:
    if num_frames <= 0:
        return np.zeros((0, 128), dtype=np.float32)

    ffmpeg_bin = resolve_ffmpeg_exe()
    if not ffmpeg_bin:
        print("Warning: ffmpeg not found, using zero audio feature")
        return np.zeros((num_frames, 128), dtype=np.float32)

    tmp_wav = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp_wav = Path(f.name)

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
            return np.zeros((num_frames, 128), dtype=np.float32)

        waveform, _sample_rate = _read_wav_mono_float32(tmp_wav)
        if waveform.size == 0:
            return np.zeros((num_frames, 128), dtype=np.float32)

        split_points = np.linspace(0, waveform.shape[0], num_frames + 1).astype(np.int64)
        features = []
        for i in range(num_frames):
            left, right = int(split_points[i]), int(split_points[i + 1])
            chunk = waveform[left:right]
            features.append(_build_chunk_embedding(chunk))

        out = np.stack(features, axis=0).astype(np.float32)
        print(f"Audio feature prepared: {out.shape}")
        return out
    except Exception as exc:
        print(f"Warning: audio feature build failed ({exc}), using zero audio feature")
        return np.zeros((num_frames, 128), dtype=np.float32)
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


def encode_png_mask(mask_u8: np.ndarray) -> bytes:
    ok, encoded = cv2.imencode(".png", mask_u8)
    if not ok:
        return b""
    return bytes(encoded)


def _decode_mask(mask_bytes: bytes, target_size: Tuple[int, int]) -> np.ndarray:
    raw = np.frombuffer(mask_bytes, dtype=np.uint8)
    mask = cv2.imdecode(raw, cv2.IMREAD_GRAYSCALE)
    if mask is None:
        return np.zeros((target_size[1], target_size[0]), dtype=np.uint8)
    if (mask.shape[1], mask.shape[0]) != target_size:
        mask = cv2.resize(mask, target_size, interpolation=cv2.INTER_NEAREST)
    return mask


def render_overlay_video(
    frames_bgr: List[np.ndarray],
    masks_bytes: List[bytes],
    out_path: Path,
    fps: float,
) -> Tuple[int, List[float]]:
    if not frames_bgr:
        raise RuntimeError("No frames extracted from input video")

    height, width = frames_bgr[0].shape[:2]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    if not writer.isOpened():
        raise RuntimeError(f"Failed to open video writer: {out_path}")

    non_empty_masks = 0
    coverage_pct_by_frame: List[float] = []

    for idx, frame_bgr in enumerate(frames_bgr):
        frame = frame_bgr.copy()
        frame_cov = 0.0

        if idx < len(masks_bytes):
            mask = _decode_mask(masks_bytes[idx], (width, height))
            mask_bool = mask > 127
            frame_cov = float(mask_bool.mean() * 100.0)

            if np.any(mask_bool):
                non_empty_masks += 1
                red_layer = np.zeros_like(frame)
                red_layer[:, :, 2] = 255
                frame = np.where(
                    mask_bool[:, :, None],
                    cv2.addWeighted(frame, 0.4, red_layer, 0.6, 0.0),
                    frame,
                )
                contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                cv2.drawContours(frame, contours, -1, (0, 255, 255), 2)

        coverage_pct_by_frame.append(round(frame_cov, 2))
        writer.write(frame)

    writer.release()
    return non_empty_masks, coverage_pct_by_frame


def setup_cfg(config_path: Path, weight_path: Path, runtime_device: str):
    cfg = get_cfg()
    add_deeplab_config(cfg)
    add_maskformer2_config(cfg)
    add_avism_config(cfg)
    cfg.merge_from_file(str(config_path))
    cfg.MODEL.WEIGHTS = str(weight_path)
    cfg.MODEL.DEVICE = "cuda" if str(runtime_device).startswith("cuda") else "cpu"

    cfg.freeze()
    return cfg


def predict_masks(frames_bgr: List[np.ndarray], audio_features: np.ndarray, cfg) -> List[bytes]:
    predictor = VideoPredictor(cfg)
    predictions = predictor({"frames": frames_bgr, "audio_feats": audio_features})

    h, w = frames_bgr[0].shape[:2]
    frame_masks = [np.zeros((h, w), dtype=np.uint8) for _ in range(len(frames_bgr))]

    pred_masks = predictions.get("pred_masks") if isinstance(predictions, dict) else None
    has_pred_masks = False
    if pred_masks is not None:
        try:
            has_pred_masks = len(pred_masks) > 0
        except Exception:
            try:
                has_pred_masks = bool(getattr(pred_masks, "numel", lambda: 0)() > 0)
            except Exception:
                has_pred_masks = False

    if has_pred_masks:
        for instance_masks in pred_masks:
            arr = instance_masks
            try:
                arr = arr.detach().cpu().numpy()
            except Exception:
                arr = np.asarray(arr)

            if arr.ndim == 3:
                max_t = min(arr.shape[0], len(frame_masks))
                for t in range(max_t):
                    m = arr[t]
                    if m.dtype != np.uint8:
                        m = (m > 0).astype(np.uint8)
                    if m.shape[:2] != (h, w):
                        m = cv2.resize(m, (w, h), interpolation=cv2.INTER_NEAREST)
                    frame_masks[t] = np.maximum(frame_masks[t], (m > 0).astype(np.uint8) * 255)

    return [encode_png_mask(m) for m in frame_masks]


def main() -> None:
    started = time.time()
    parser = argparse.ArgumentParser(description="Run AVIS inference")
    parser.add_argument("--task_id", required=True, help="Task ID")
    parser.add_argument("--file_id", required=True, help="Uploaded file ID")
    parser.add_argument("--weight_path", required=True, help="Path to model weights")
    parser.add_argument("--uploads_dir", required=True, help="Uploads directory")
    parser.add_argument("--results_dir", required=True, help="Results directory")
    parser.add_argument("--masks_dir", required=True, help="Masks directory")
    parser.add_argument("--config_path", default="", help="Optional AVIS config path")
    args = parser.parse_args()

    weight_path = Path(args.weight_path).expanduser()
    if not weight_path.exists() or not weight_path.is_file():
        print(f"Error: weight file not found: {weight_path}")
        sys.exit(1)

    requested_avis_device = os.getenv("AVS_AVIS_DEVICE", "auto").strip() or "auto"
    runtime_device = resolve_runtime_device(requested_device=requested_avis_device)
    runtime_info = get_torch_runtime_info(runtime_device)
    print(f"[runtime] {format_runtime_info(runtime_info)}")
    print(f"[avis] requested_device: {requested_avis_device}")
    print(f"[avis] root: {AVIS_ROOT}")

    config_path = choose_config_path(weight_path=weight_path, config_path_arg=args.config_path)
    if not config_path.exists():
        print(f"Error: AVIS config not found: {config_path}")
        sys.exit(1)

    uploads_dir = Path(args.uploads_dir)
    results_dir = Path(args.results_dir)
    masks_dir = Path(args.masks_dir)

    matches = list(uploads_dir.glob(f"{args.file_id}__*"))
    if not matches:
        print(f"Error: File {args.file_id} not found")
        sys.exit(1)
    video_path = str(matches[0])

    print(f"Loading AVIS model from {weight_path} with config {config_path}...")
    try:
        cfg = setup_cfg(config_path=config_path, weight_path=weight_path, runtime_device=runtime_device)
    except Exception as exc:
        print(f"Failed to setup cfg: {exc}")
        traceback.print_exc()
        sys.exit(1)

    print(f"Extracting frames from {video_path}...")
    frames_bgr, fps = extract_frames(video_path)
    if not frames_bgr:
        print("Error: no frames extracted")
        sys.exit(1)

    frames_bgr, fps, _stride = maybe_downsample_frames(frames_bgr, fps)
    frames_bgr, _resize_scale = maybe_resize_frames(frames_bgr)

    audio_feat = build_audio_feature(video_path, len(frames_bgr))

    print(f"Running AVIS inference on {len(frames_bgr)} frames...")
    try:
        masks_bytes = predict_masks(frames_bgr=frames_bgr, audio_features=audio_feat, cfg=cfg)
    except Exception as exc:
        msg = str(exc)
        mismatch_sig = "indices should be either on cpu or on the same device"
        if mismatch_sig in msg.lower() and str(runtime_device).startswith("cuda"):
            print("[avis] detected device mismatch on CUDA path, retrying once on CPU...")
            try:
                cfg_cpu = setup_cfg(config_path=config_path, weight_path=weight_path, runtime_device="cpu")
                masks_bytes = predict_masks(frames_bgr=frames_bgr, audio_features=audio_feat, cfg=cfg_cpu)
                print("[avis] CPU retry succeeded.")
            except Exception as retry_exc:
                print(f"Inference error after CPU retry: {retry_exc}")
                traceback.print_exc()
                sys.exit(1)
        else:
            print(f"Inference error: {exc}")
            traceback.print_exc()
            sys.exit(1)

    masks_zip_path = masks_dir / f"{args.task_id}.zip"
    print(f"Saving masks to {masks_zip_path}...")
    with zipfile.ZipFile(masks_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for i, mask_data in enumerate(masks_bytes):
            zf.writestr(f"mask_{i + 1:04d}.png", mask_data)

    result_path = results_dir / f"{args.task_id}.mp4"
    overlay_tmp_path = results_dir / f"{args.task_id}.overlay_tmp.mp4"
    non_empty_masks, coverage_pct_by_frame = render_overlay_video(frames_bgr, masks_bytes, overlay_tmp_path, fps)

    if transcode_browser_mp4(overlay_tmp_path, video_path, result_path):
        try:
            os.remove(overlay_tmp_path)
        except OSError:
            pass
        print(f"Overlay video saved (h264): {result_path}, non-empty masks: {non_empty_masks}/{len(frames_bgr)}")
    else:
        if result_path.exists():
            result_path.unlink()
        overlay_tmp_path.rename(result_path)
        print(
            f"Overlay video saved (mp4v fallback): {result_path}, "
            f"non-empty masks: {non_empty_masks}/{len(frames_bgr)}"
        )

    report_path = results_dir / f"{args.task_id}.report.json"
    total_ms = int((time.time() - started) * 1000)
    processing = build_processing_metrics(total_ms, len(frames_bgr))
    metrics = estimate_metrics(algorithm="avis", subset="coco", coverage_pct_by_frame=coverage_pct_by_frame)
    report = {
        "task_id": args.task_id,
        "algorithm": "avis",
        "subset": "coco",
        "frames": len(frames_bgr),
        "fps": round(float(fps), 3) if fps else None,
        "duration_seconds": round(float(len(frames_bgr) / fps), 3) if fps else None,
        "width": int(frames_bgr[0].shape[1]) if frames_bgr else None,
        "height": int(frames_bgr[0].shape[0]) if frames_bgr else None,
        "metrics": metrics,
        "processing": {
            "total_ms": processing["total_inference_ms"],
            "avg_frame_ms": processing["avg_frame_ms"],
            "processed_frames": processing["processed_frames"],
        },
        "mask_coverage_pct_by_frame": coverage_pct_by_frame,
        "note": f"AVIS inference done with config={config_path.name}; 指标为论文固定值。",
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("Done.")


if __name__ == "__main__":
    main()
