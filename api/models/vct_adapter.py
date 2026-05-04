from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Iterable, List

import cv2
import numpy as np
import torch

from api.models.device_utils import (
    ensure_model_on_device,
    format_runtime_info,
    get_torch_runtime_info,
    model_parameter_device,
    resolve_runtime_device,
)


def _resolve_vct_root() -> Path:
    adapter_path = Path(__file__).resolve()
    api_root = adapter_path.parents[1]  # .../api
    project_root = adapter_path.parents[2]  # .../AVS2

    candidates: list[Path] = []

    env_root = os.getenv("AVS_VCT_ROOT", "").strip()
    if env_root:
        candidates.append(Path(env_root).expanduser())

    candidates.extend(
        [
            api_root / "third_party" / "VCT_AVS",
            project_root / "third_party" / "VCT_AVS",
            Path("/root/autodl-tmp/VCT_AVS"),
            Path("/root/VCT_AVS"),
        ]
    )

    for candidate in candidates:
        if (candidate / "train_net.py").is_file() and (candidate / "configs").is_dir():
            return candidate

    searched = "\n".join(f"- {p}" for p in candidates)
    raise FileNotFoundError(
        "VCT_AVS source not found. Set AVS_VCT_ROOT or place VCT_AVS in one of:\n"
        f"{searched}"
    )


VCT_ROOT = _resolve_vct_root()
_vct_root_str = str(VCT_ROOT)
_vct_detectron2_repo = VCT_ROOT / "detectron2"
if _vct_detectron2_repo.is_dir():
    _vct_detectron2_repo_str = str(_vct_detectron2_repo)
    if _vct_detectron2_repo_str not in sys.path:
        sys.path.insert(0, _vct_detectron2_repo_str)
if _vct_root_str not in sys.path:
    sys.path.insert(0, _vct_root_str)

# Avoid importing detectron2 from COMBO-AVS only when VCT ships its own detectron2 tree.
if _vct_detectron2_repo.is_dir():
    for _idx in range(len(sys.path) - 1, -1, -1):
        _p = str(sys.path[_idx])
        if "COMBO-AVS" in _p and _p != _vct_detectron2_repo_str:
            sys.path.pop(_idx)

from detectron2.checkpoint import DetectionCheckpointer
from detectron2.config import get_cfg
from detectron2.projects.deeplab import add_deeplab_config

from models import add_audio_config, add_fuse_config, add_maskformer2_config
from train_net import Trainer


class VctAdapter:
    def __init__(self, config_path: str | None = None):
        if config_path is None:
            config_path = str(VCT_ROOT / "configs" / "s4_swinb_384" / "Test_COMBO_SWINB.yaml")

        self.cfg = self._setup_cfg(config_path)
        self.model = None
        self.device = resolve_runtime_device()

    def _setup_cfg(self, config_path: str):
        cfg = get_cfg()
        add_deeplab_config(cfg)
        add_audio_config(cfg)
        add_fuse_config(cfg)
        add_maskformer2_config(cfg)
        cfg.merge_from_file(config_path)

        cfg.defrost()

        def _resolve_vct_path(path_value: str) -> str:
            raw = str(path_value or "").strip()
            if not raw:
                return raw
            p = Path(raw).expanduser()
            if p.is_absolute():
                return str(p)
            return str((VCT_ROOT / p).resolve())

        cfg.MODEL.AUDIO.PRETRAINED_VGGISH_MODEL_PATH = _resolve_vct_path(
            cfg.MODEL.AUDIO.PRETRAINED_VGGISH_MODEL_PATH
        )
        cfg.MODEL.AUDIO.PRETRAINED_PCA_PARAMS_PATH = _resolve_vct_path(
            cfg.MODEL.AUDIO.PRETRAINED_PCA_PARAMS_PATH
        )
        cfg.MODEL.WEIGHTS = _resolve_vct_path(cfg.MODEL.WEIGHTS)

        vggish_path = Path(cfg.MODEL.AUDIO.PRETRAINED_VGGISH_MODEL_PATH)
        if not vggish_path.is_file():
            raise FileNotFoundError(
                f"VGGish pretrained weight not found: {vggish_path}. "
                "Please check AVS_VCT_ROOT and VCT_AVS/pretrained files."
            )

        pca_path = Path(cfg.MODEL.AUDIO.PRETRAINED_PCA_PARAMS_PATH)
        if not pca_path.is_file():
            raise FileNotFoundError(
                f"VGGish PCA params not found: {pca_path}. "
                "Please check AVS_VCT_ROOT and VCT_AVS/pretrained files."
            )

        if not torch.cuda.is_available():
            cfg.MODEL.DEVICE = "cpu"
        cfg.freeze()
        return cfg

    def load_weights(self, weight_path: str, device: str | None = None):
        self.device = resolve_runtime_device(device)
        runtime = get_torch_runtime_info(self.device)
        print(f"[vct] runtime: {format_runtime_info(runtime)}")

        self.cfg.defrost()
        self.cfg.MODEL.DEVICE = self.device
        self.cfg.freeze()

        self.model = Trainer.build_model(self.cfg)
        self.model.eval()

        checkpointer = DetectionCheckpointer(self.model)
        checkpointer.load(weight_path)
        self.model.to(self.device)
        self.model.eval()

        model_dev = ensure_model_on_device(self.model, self.device)
        print(f"[vct] model_parameter_device={model_dev}")

    def infer(self, frames: List[np.ndarray], audio_feature: np.ndarray) -> Iterable[bytes]:
        if not self.model:
            raise RuntimeError("Model not loaded. Call load_weights() first.")

        total_frames = len(frames)
        if total_frames == 0:
            return

        chunk_size = int(getattr(self.cfg.MODEL.FUSE_CONFIG, "NUM_FRAMES", 5) or 5)
        if chunk_size <= 0:
            chunk_size = 5

        infer_size = getattr(self.cfg.INPUT, "MIN_SIZE_TEST", 384)
        if isinstance(infer_size, (list, tuple)):
            infer_size = infer_size[0]
        infer_size = int(infer_size)

        use_pre_sam = bool(getattr(self.cfg.MODEL.PRE_SAM, "USE_PRE_SAM", False))
        mapper_name = str(getattr(self.cfg.INPUT, "DATASET_MAPPER_NAME", "") or "").strip()
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

            # VCT forward expects mapper-specific auxiliary keys even during inference.
            if mapper_name == "avss4_semantic":
                batch_input["category_label"] = 0
            elif mapper_name == "avss_semantic":
                batch_input["vid_temporal_mask_flag"] = torch.ones((chunk_size,), dtype=torch.float32)
                batch_input["gt_temporal_mask_flag"] = torch.ones((chunk_size,), dtype=torch.float32)

            if use_pre_sam:
                batch_input["pre_masks"] = torch.stack(pre_mask_tensors, dim=0).to(self.device)

            if i == 0:
                expected_prefix = "cuda" if self.device.startswith("cuda") else "cpu"
                model_dev = model_parameter_device(self.model)
                image_dev = str(batch_input["images"].device)
                audio_dev = str(batch_input["audio_log_mel"].device)
                print(
                    "[vct] first_batch_devices: "
                    f"model={model_dev}, images={image_dev}, audio={audio_dev}"
                )
                if (
                    not model_dev.startswith(expected_prefix)
                    or not image_dev.startswith(expected_prefix)
                    or not audio_dev.startswith(expected_prefix)
                ):
                    raise RuntimeError(
                        "Device mismatch before VCT inference: "
                        f"expected={self.device}, model={model_dev}, images={image_dev}, audio={audio_dev}"
                    )

            with torch.no_grad():
                outputs = self.model([batch_input])

            for output in outputs[:valid_count]:
                sem_seg = output["sem_seg"]
                if sem_seg.dim() == 3 and sem_seg.shape[0] > 1:
                    mask = sem_seg.argmax(dim=0).byte().cpu().numpy()
                else:
                    mask = (sem_seg.squeeze(0) > 0).byte().cpu().numpy()
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
            # Fallback placeholder to keep inference pipeline running if log-mel is unavailable.
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
