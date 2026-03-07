from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Iterable, List

import cv2
import numpy as np
import torch
import torch.nn.functional as F
from detectron2.checkpoint import DetectionCheckpointer
from detectron2.config import get_cfg
from detectron2.data import MetadataCatalog
from detectron2.projects.deeplab import add_deeplab_config
from PIL import Image


def _resolve_combo_root() -> Path:
    adapter_path = Path(__file__).resolve()
    api_root = adapter_path.parents[1]       # .../api
    project_root = adapter_path.parents[2]   # .../AVS2

    candidates: list[Path] = []

    env_root = os.getenv("AVS_COMBO_ROOT", "").strip()
    if env_root:
        candidates.append(Path(env_root).expanduser())

    candidates.extend(
        [
            api_root / "third_party" / "COMBO-AVS",
            project_root / "third_party" / "COMBO-AVS",
            Path("/root/autodl-tmp/COMBO-AVS"),
            Path("/root/COMBO-AVS"),
        ]
    )

    for candidate in candidates:
        if (candidate / "train_net.py").is_file() and (candidate / "configs").is_dir():
            return candidate

    searched = "\n".join(f"- {p}" for p in candidates)
    raise FileNotFoundError(
        "COMBO-AVS source not found. Set AVS_COMBO_ROOT or place COMBO-AVS in one of:\n"
        f"{searched}"
    )


# Add COMBO-AVS to sys.path
COMBO_ROOT = _resolve_combo_root()
if str(COMBO_ROOT) not in sys.path:
    sys.path.insert(0, str(COMBO_ROOT))

# Import COMBO modules (after sys.path modification)
from models import (
    add_audio_config,
    add_fuse_config,
    add_maskformer2_config,
)
from train_net import Trainer


class ComboAdapter:
    def __init__(self, config_path: str = None):
        if config_path is None:
            # Default to S4 config (ResNet50)
            config_path = str(COMBO_ROOT / "configs" / "avs_s4" / "COMBO_R50_bs8_90k.yaml")
        
        self.cfg = self._setup_cfg(config_path)
        self.model = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

    def _setup_cfg(self, config_path: str):
        cfg = get_cfg()
        add_deeplab_config(cfg)
        add_audio_config(cfg)
        add_fuse_config(cfg)
        add_maskformer2_config(cfg)
        cfg.merge_from_file(config_path)

        cfg.defrost()

        def _resolve_combo_path(path_value: str) -> str:
            raw = str(path_value or "").strip()
            if not raw:
                return raw
            p = Path(raw).expanduser()
            if p.is_absolute():
                return str(p)
            return str((COMBO_ROOT / p).resolve())

        cfg.MODEL.AUDIO.PRETRAINED_VGGISH_MODEL_PATH = _resolve_combo_path(
            cfg.MODEL.AUDIO.PRETRAINED_VGGISH_MODEL_PATH
        )
        cfg.MODEL.AUDIO.PRETRAINED_PCA_PARAMS_PATH = _resolve_combo_path(
            cfg.MODEL.AUDIO.PRETRAINED_PCA_PARAMS_PATH
        )
        cfg.MODEL.WEIGHTS = _resolve_combo_path(cfg.MODEL.WEIGHTS)

        vggish_path = Path(cfg.MODEL.AUDIO.PRETRAINED_VGGISH_MODEL_PATH)
        if not vggish_path.is_file():
            raise FileNotFoundError(
                f"VGGish pretrained weight not found: {vggish_path}. "
                "Please check AVS_COMBO_ROOT and COMBO-AVS/pretrained files."
            )

        pca_path = Path(cfg.MODEL.AUDIO.PRETRAINED_PCA_PARAMS_PATH)
        if not pca_path.is_file():
            raise FileNotFoundError(
                f"VGGish PCA params not found: {pca_path}. "
                "Please check AVS_COMBO_ROOT and COMBO-AVS/pretrained files."
            )

        # Force CPU if CUDA not available
        if not torch.cuda.is_available():
            cfg.MODEL.DEVICE = "cpu"
        cfg.freeze()
        return cfg

    def load_weights(self, weight_path: str, device: str = None):
        if device:
            self.device = device
            # Note: cfg.MODEL.DEVICE is frozen, so we might need to rely on model.to(device)
        
        self.model = Trainer.build_model(self.cfg)
        self.model.eval()
        
        checkpointer = DetectionCheckpointer(self.model)
        checkpointer.load(weight_path)
        self.model.to(self.device)

    def infer(self, frames: List[np.ndarray], audio_feature: np.ndarray) -> Iterable[bytes]:
        """
        Args:
            frames: List of numpy images (H, W, 3) in RGB
            audio_feature: Log-Mel spectrogram (1, 96, 64) or similar
        Yields:
            PNG bytes of the mask for each frame
        """
        if not self.model:
            raise RuntimeError("Model not loaded. Call load_weights() first.")

        total_frames = len(frames)
        if total_frames == 0:
            return

        # COMBO config defaults to 5-frame chunks for AVSS4/MS3.
        chunk_size = int(getattr(self.cfg.MODEL.FUSE_CONFIG, "NUM_FRAMES", 5) or 5)
        if chunk_size <= 0:
            chunk_size = 5

        # Keep mapper-compatible resolution for inference by default.
        infer_size = getattr(self.cfg.INPUT, "MIN_SIZE_TEST", 224)
        if isinstance(infer_size, (list, tuple)):
            infer_size = infer_size[0]
        infer_size = int(infer_size)

        use_pre_sam = bool(getattr(self.cfg.MODEL.PRE_SAM, "USE_PRE_SAM", False))
        audio_tensor = self._prepare_audio_tensor(audio_feature=audio_feature, total_frames=total_frames)

        for i in range(0, total_frames, chunk_size):
            batch_frames = frames[i : i + chunk_size]
            if not batch_frames:
                break

            valid_count = len(batch_frames)
            if valid_count < chunk_size:
                batch_frames = batch_frames + [batch_frames[-1]] * (chunk_size - valid_count)

            image_tensors: list[torch.Tensor] = []
            pre_mask_tensors: list[torch.Tensor] = []
            for frame in batch_frames:
                img = cv2.resize(frame, (infer_size, infer_size), interpolation=cv2.INTER_LINEAR)
                img_tensor = torch.as_tensor(np.ascontiguousarray(img.transpose(2, 0, 1))).float()
                image_tensors.append(img_tensor)
                if use_pre_sam:
                    # In deployment we may not have external SAM masks, use visual frame as fallback input.
                    pre_mask_tensors.append(img_tensor.clone())

            images_tensor = torch.stack(image_tensors, dim=0)

            audio_chunk = audio_tensor[i : i + chunk_size]
            if audio_chunk.shape[0] < chunk_size:
                pad = audio_chunk[-1:].repeat(chunk_size - audio_chunk.shape[0], 1, 1, 1)
                audio_chunk = torch.cat([audio_chunk, pad], dim=0)

            first_h, first_w = batch_frames[0].shape[0], batch_frames[0].shape[1]
            batch_input = {
                "images": images_tensor.to(self.device),
                "audio_log_mel": audio_chunk.to(self.device),
                "height": int(first_h),
                "width": int(first_w),
            }
            if use_pre_sam:
                batch_input["pre_masks"] = torch.stack(pre_mask_tensors, dim=0).to(self.device)

            with torch.no_grad():
                outputs = self.model([batch_input])

            for output in outputs[:valid_count]:
                sem_seg = output["sem_seg"]
                mask = sem_seg.argmax(dim=0).byte().cpu().numpy()
                mask_img = (mask * 255).astype(np.uint8)

                success, encoded_img = cv2.imencode(".png", mask_img)
                if success:
                    yield encoded_img.tobytes()
                else:
                    yield b""

    def _prepare_audio_tensor(self, *, audio_feature: np.ndarray, total_frames: int) -> torch.Tensor:
        arr = np.asarray(audio_feature)

        if arr.ndim == 4 and arr.shape[1:] == (1, 96, 64):
            out = arr.astype(np.float32)
        elif arr.ndim == 3 and arr.shape[1:] == (96, 64):
            out = arr[:, None, :, :].astype(np.float32)
        else:
            # Fallback placeholder to keep inference pipeline running in deployment environments
            # where true audio log-mel is not precomputed.
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

    def _get_transform(self):
        # Helper to create the image transformation pipeline consistent with COMBO training
        import detectron2.data.transforms as T
        
        # Default resize to 384x384 or whatever config says
        # For simplicity, we implement a basic one
        def transform(img_np):
            # img_np is HxWxC, RGB
            # Resize
            img = cv2.resize(img_np, (384, 384))
            # To Tensor (C, H, W)
            tensor = torch.as_tensor(img.transpose(2, 0, 1).astype("float32"))
            return tensor
            
        return transform
