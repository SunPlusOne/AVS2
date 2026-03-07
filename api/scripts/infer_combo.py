import argparse
import os
import sys
import json
import shutil
import subprocess
import tempfile
import zipfile
import traceback
from typing import List, Tuple
import wave
import numpy as np
import cv2
from pathlib import Path

# Add project root to sys.path to import modules
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import adapter (this script runs in the correct Conda env, so imports should work)
try:
    from api.models.combo_adapter import ComboAdapter
except Exception as e:
    print(f"Error importing ComboAdapter: {e}")
    traceback.print_exc()
    sys.exit(1)

try:
    # Imported after ComboAdapter so COMBO_ROOT is already injected into sys.path.
    from models.modeling.audio_backbone.torchvggish import vggish_input
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

def extract_frames(video_path: str) -> Tuple[List[np.ndarray], float]:
    cap = cv2.VideoCapture(video_path)
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    if fps <= 1e-6:
        fps = 25.0
    frames = []
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frames.append(frame)
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

    # Evenly sample/expand audio windows to match frame count.
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
            return zero_fallback

        waveform, sample_rate = _read_wav_mono_float32(tmp_wav)
        examples = vggish_input.waveform_to_examples(waveform, sample_rate, return_tensor=False)
        aligned = _align_audio_examples(np.asarray(examples), num_frames)
        print(f"Audio feature prepared: {aligned.shape}")
        return aligned
    except Exception as e:
        print(f"Warning: audio feature build failed ({e}), using zero audio feature")
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
) -> int:
    if not frames_rgb:
        raise RuntimeError("No frames extracted from input video")

    height, width = frames_rgb[0].shape[:2]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    if not writer.isOpened():
        raise RuntimeError(f"Failed to open video writer: {out_path}")

    non_empty_masks = 0
    for idx, frame_rgb in enumerate(frames_rgb):
        frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
        if idx < len(masks_bytes):
            mask = _decode_mask(masks_bytes[idx], (width, height))
            mask_bool = mask > 127
            if np.any(mask_bool):
                non_empty_masks += 1

                # Red alpha overlay for segmented pixels.
                red_layer = np.zeros_like(frame_bgr)
                red_layer[:, :, 2] = 255
                frame_bgr = np.where(
                    mask_bool[:, :, None],
                    cv2.addWeighted(frame_bgr, 0.4, red_layer, 0.6, 0.0),
                    frame_bgr,
                )

                # Draw yellow contour to make mask boundaries visible.
                contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                cv2.drawContours(frame_bgr, contours, -1, (0, 255, 255), 2)

        writer.write(frame_bgr)

    writer.release()
    return non_empty_masks

def main():
    parser = argparse.ArgumentParser(description="Run COMBO inference")
    parser.add_argument("--task_id", required=True, help="Task ID")
    parser.add_argument("--file_id", required=True, help="Uploaded file ID")
    parser.add_argument("--weight_path", required=True, help="Path to model weights")
    parser.add_argument("--uploads_dir", required=True, help="Uploads directory")
    parser.add_argument("--results_dir", required=True, help="Results directory")
    parser.add_argument("--masks_dir", required=True, help="Masks directory")
    
    args = parser.parse_args()

    weight_path = Path(args.weight_path).expanduser()
    if not weight_path.exists() or not weight_path.is_file():
        print(f"Error: weight file not found: {weight_path}")
        sys.exit(1)
    
    uploads_dir = Path(args.uploads_dir)
    results_dir = Path(args.results_dir)
    masks_dir = Path(args.masks_dir)
    
    # Find upload
    matches = list(uploads_dir.glob(f"{args.file_id}__*"))
    if not matches:
        print(f"Error: File {args.file_id} not found")
        sys.exit(1)
    video_path = str(matches[0])
    
    print(f"Loading model from {weight_path}...")
    try:
        adapter = ComboAdapter()
        adapter.load_weights(str(weight_path))
    except Exception as e:
        print(f"Failed to load model: {e}")
        traceback.print_exc()
        sys.exit(1)
        
    print(f"Extracting frames from {video_path}...")
    frames, fps = extract_frames(video_path)
    
    # Build audio log-mel feature from source video when possible.
    audio_feat = build_audio_feature(video_path, len(frames))
    
    print(f"Running inference on {len(frames)} frames...")
    masks_bytes = []
    try:
        for i, mask_png in enumerate(adapter.infer(frames, audio_feat)):
            masks_bytes.append(mask_png)
            if i % 10 == 0:
                print(f"Processed {i}/{len(frames)} frames")
    except Exception as e:
        print(f"Inference error: {e}")
        traceback.print_exc()
        sys.exit(1)
        
    # Save results
    masks_zip_path = masks_dir / f"{args.task_id}.zip"
    print(f"Saving masks to {masks_zip_path}...")
    with zipfile.ZipFile(masks_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for i, mask_data in enumerate(masks_bytes):
            zf.writestr(f"mask_{i+1:04d}.png", mask_data)

    # Build visualization video with segmentation overlay.
    result_path = results_dir / f"{args.task_id}.mp4"
    overlay_tmp_path = results_dir / f"{args.task_id}.overlay_tmp.mp4"
    non_empty_masks = render_overlay_video(frames, masks_bytes, overlay_tmp_path, fps)

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
    
    print("Done.")

if __name__ == "__main__":
    main()
