from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

import cv2
import numpy as np
import torch
from mmcv import Config
from PIL import Image
from torchvision import transforms


def _resolve_avsegformer_root() -> Path:
    adapter_path = Path(__file__).resolve()
    api_root = adapter_path.parents[1]
    project_root = adapter_path.parents[2]

    candidates: list[Path] = []

    env_root = os.getenv("AVS_AVSEGFORMER_ROOT", "").strip()
    if env_root:
        candidates.append(Path(env_root).expanduser())

    candidates.extend(
        [
            api_root / "third_party" / "AVSegFormer",
            project_root / "third_party" / "AVSegFormer",
            Path("/root/autodl-tmp/AVSegFormer"),
            Path("/root/AVSegFormer"),
        ]
    )

    for candidate in candidates:
        if (candidate / "model").is_dir() and (candidate / "config").is_dir():
            return candidate

    searched = "\n".join(f"- {p}" for p in candidates)
    raise FileNotFoundError(
        "AVSegFormer source not found. Set AVS_AVSEGFORMER_ROOT or place AVSegFormer in one of:\n"
        f"{searched}"
    )


AVSEGFORMER_ROOT = _resolve_avsegformer_root()
if str(AVSEGFORMER_ROOT) not in sys.path:
    sys.path.insert(0, str(AVSEGFORMER_ROOT))

from model import build_model


def _resolve_device() -> str:
    forced = os.getenv("AVS_FORCE_DEVICE", "auto").strip().lower()
    if forced == "cpu":
        return "cpu"
    if forced == "cuda" and torch.cuda.is_available():
        return "cuda"
    return "cuda" if torch.cuda.is_available() else "cpu"


def _looks_like_state_dict(payload: Any) -> bool:
    return isinstance(payload, Mapping) and any(isinstance(v, torch.Tensor) for v in payload.values())


def _unwrap_state_dict(payload: Any) -> Mapping[str, Any]:
    if _looks_like_state_dict(payload):
        return payload

    if isinstance(payload, Mapping):
        for key in ("state_dict", "model", "model_state_dict", "net", "params"):
            value = payload.get(key)
            if _looks_like_state_dict(value):
                return value

    raise ValueError("Unsupported AVSegFormer checkpoint format")


def _normalize_state_dict(payload: Mapping[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for raw_key, value in payload.items():
        key = str(raw_key)
        while key.startswith("module."):
            key = key[7:]
        if key.startswith("model."):
            key = key[6:]
        normalized[key] = value
    return normalized


def _load_checkpoint_payload(weight_path: str) -> Any:
    try:
        return torch.load(weight_path, map_location="cpu")
    except Exception as exc:
        raise RuntimeError(
            "Failed to read AVSegFormer checkpoint. The file may be corrupted or incomplete: "
            f"{weight_path}"
        ) from exc


def detect_backbone_from_checkpoint(weight_path: str) -> str:
    override = os.getenv("AVS_AVSEGFORMER_BACKBONE", "").strip().lower()
    if override in {"pvt2", "res50"}:
        return override

    payload = _load_checkpoint_payload(weight_path)
    state_dict = _normalize_state_dict(_unwrap_state_dict(payload))
    keys = state_dict.keys()

    if any(k.startswith("backbone.patch_embed1") for k in keys):
        return "pvt2"
    if any(k.startswith("backbone.conv1") or k.startswith("backbone.layer1") for k in keys):
        return "res50"
    return "pvt2"


def _resolve_existing_file(candidates: Iterable[Path]) -> Path | None:
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _resolve_vggish_path() -> Path:
    env_vggish = os.getenv("AVS_AVSEGFORMER_VGGISH", "").strip()
    candidates = []
    if env_vggish:
        candidates.append(Path(env_vggish).expanduser())

    combo_root = os.getenv("AVS_COMBO_ROOT", "").strip()
    vct_root = os.getenv("AVS_VCT_ROOT", "").strip()
    candidates.extend(
        [
            AVSEGFORMER_ROOT / "pretrained" / "vggish-10086976.pth",
            Path(combo_root) / "pretrained" / "vggish-10086976.pth" if combo_root else Path(),
            Path(vct_root) / "pretrained" / "vggish-10086976.pth" if vct_root else Path(),
            Path("/root/autodl-tmp/COMBO-AVS/pretrained/vggish-10086976.pth"),
            Path("/root/autodl-tmp/VCT_AVS/pretrained/vggish-10086976.pth"),
        ]
    )

    resolved = _resolve_existing_file(candidates)
    if resolved is None:
        searched = "\n".join(f"- {p}" for p in candidates if str(p))
        raise FileNotFoundError(
            "VGGish pretrained weight not found for AVSegFormer. "
            "Set AVS_AVSEGFORMER_VGGISH or place the file in one of:\n"
            f"{searched}"
        )
    return resolved


class AvSegFormerAdapter:
    def __init__(self, config_path: str | None = None):
        if config_path is None:
            config_path = str(AVSEGFORMER_ROOT / "config" / "s4" / "AVSegFormer_pvt2_s4.py")

        self.cfg = self._setup_cfg(config_path)
        self.model = None
        self.device = _resolve_device()
        self.chunk_size = max(1, int(getattr(self.cfg.model, "T", 5) or 5))
        self._image_transform = transforms.Compose(
            [
                transforms.Resize([512, 512]),
                transforms.ToTensor(),
                transforms.Normalize((0.485, 0.456, 0.406), (0.229, 0.224, 0.225)),
            ]
        )

    def _setup_cfg(self, config_path: str) -> Config:
        cfg_path = Path(config_path).expanduser()
        if not cfg_path.is_absolute():
            cfg_path = (AVSEGFORMER_ROOT / cfg_path).resolve()
        if not cfg_path.is_file():
            raise FileNotFoundError(f"AVSegFormer config not found: {cfg_path}")

        cfg = Config.fromfile(str(cfg_path))
        cfg.model.vggish.pretrained_vggish_model_path = str(_resolve_vggish_path())

        backbone_override = os.getenv("AVS_AVSEGFORMER_BACKBONE_PRETRAIN", "").strip()
        if backbone_override:
            backbone_path = Path(backbone_override).expanduser()
            if not backbone_path.is_absolute():
                backbone_path = (AVSEGFORMER_ROOT / backbone_path).resolve()
            if not backbone_path.is_file():
                raise FileNotFoundError(f"AVSegFormer backbone init weight not found: {backbone_path}")
            cfg.model.backbone.init_weights_path = str(backbone_path)
        else:
            cfg.model.backbone.init_weights_path = None

        return cfg

    def load_weights(self, weight_path: str, device: str | None = None) -> None:
        if device:
            self.device = "cuda" if device == "cuda" and torch.cuda.is_available() else "cpu"

        checkpoint = _load_checkpoint_payload(weight_path)
        state_dict = _normalize_state_dict(_unwrap_state_dict(checkpoint))

        self.model = build_model(**self.cfg.model)
        missing, unexpected = self.model.load_state_dict(state_dict, strict=False)
        if missing or unexpected:
            details: list[str] = []
            if missing:
                details.append(f"missing={missing[:10]}")
            if unexpected:
                details.append(f"unexpected={unexpected[:10]}")
            raise RuntimeError(
                "AVSegFormer checkpoint is not compatible with the selected config: "
                + "; ".join(details)
            )

        self.model.to(self.device)
        self.model.eval()

    def infer(self, frames: list[np.ndarray], audio_feature: np.ndarray) -> Iterable[bytes]:
        if self.model is None:
            raise RuntimeError("Model not loaded. Call load_weights() first.")

        total_frames = len(frames)
        if total_frames == 0:
            return

        audio_tensor = self._prepare_audio_tensor(audio_feature=audio_feature, total_frames=total_frames)

        for start in range(0, total_frames, self.chunk_size):
            batch_frames = frames[start : start + self.chunk_size]
            if not batch_frames:
                break

            valid_count = len(batch_frames)
            if valid_count < self.chunk_size:
                batch_frames = batch_frames + [batch_frames[-1]] * (self.chunk_size - valid_count)

            image_tensors = [self._image_transform(Image.fromarray(frame)) for frame in batch_frames]
            images_tensor = torch.stack(image_tensors, dim=0).to(self.device)

            audio_chunk = audio_tensor[start : start + self.chunk_size]
            if audio_chunk.shape[0] < self.chunk_size:
                pad = audio_chunk[-1:].repeat(self.chunk_size - audio_chunk.shape[0], 1, 1, 1)
                audio_chunk = torch.cat([audio_chunk, pad], dim=0)
            audio_chunk = audio_chunk.to(self.device)

            with torch.no_grad():
                pred_mask, _ = self.model(audio_chunk, images_tensor)

            for offset, pred in enumerate(pred_mask[:valid_count]):
                raw_mask = torch.sigmoid(pred.squeeze(0)).cpu().numpy()
                mask = (raw_mask > 0.5).astype(np.uint8) * 255
                frame_h, frame_w = frames[start + offset].shape[:2]
                if mask.shape != (frame_h, frame_w):
                    mask = cv2.resize(mask, (frame_w, frame_h), interpolation=cv2.INTER_NEAREST)

                success, encoded = cv2.imencode(".png", mask)
                yield encoded.tobytes() if success else b""

    def _prepare_audio_tensor(self, *, audio_feature: np.ndarray, total_frames: int) -> torch.Tensor:
        arr = np.asarray(audio_feature)

        if arr.ndim == 4 and arr.shape[1:] == (1, 96, 64):
            out = arr.astype(np.float32)
        elif arr.ndim == 3 and arr.shape[1:] == (96, 64):
            out = arr[:, None, :, :].astype(np.float32)
        elif arr.ndim == 2 and arr.shape == (96, 64):
            out = arr[None, None, :, :].astype(np.float32)
        else:
            out = np.zeros((total_frames, 1, 96, 64), dtype=np.float32)

        if out.shape[0] <= 0:
            out = np.zeros((total_frames, 1, 96, 64), dtype=np.float32)

        if out.shape[0] == 1 and total_frames > 1:
            out = np.repeat(out, total_frames, axis=0)
        elif out.shape[0] < total_frames:
            pad = np.repeat(out[-1:, :, :, :], total_frames - out.shape[0], axis=0)
            out = np.concatenate([out, pad], axis=0)
        elif out.shape[0] > total_frames:
            out = out[:total_frames]

        return torch.from_numpy(out).float()