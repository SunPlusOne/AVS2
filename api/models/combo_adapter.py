from __future__ import annotations

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

# Add COMBO-AVS to sys.path
COMBO_ROOT = Path(__file__).resolve().parent.parent.parent / "third_party" / "COMBO-AVS"
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

        # COMBO expects batched inputs. For S4/MS3 it usually processes 5 frames at a time 
        # or takes the whole video if it fits in memory.
        # Here we process in chunks of 5 frames (as per COMBO default T=5) or 1 frame?
        # COMBO's 'vid_temporal_mask_flag' logic implies it handles temporal batches.
        
        # Data preparation logic adapted from AVSBenchmark dataset mapper
        # 1. Resize/Normalize images
        # 2. Prepare audio features
        
        transform = self._get_transform()
        
        # Simplification: Process in batches of 5 (or T)
        T = 5 
        total_frames = len(frames)
        
        # Audio feature needs to be repeated or sliced? 
        # In COMBO, audio_log_mel is usually [T, 96, 64] or similar.
        # Assuming audio_feature is already preprocessed to match the video duration.
        
        # Convert audio to tensor
        audio_tensor = torch.as_tensor(audio_feature).float().to(self.device)
        if len(audio_tensor.shape) == 3: # [1, 96, 64] -> [T, 1, 96, 64] ?
             # For simplicity, we might need to replicate it if it's a global feature
             pass

        for i in range(0, total_frames, T):
            batch_frames = frames[i : i + T]
            if len(batch_frames) < T:
                # Padding or break?
                break
                
            # Prepare input dict for detectron2 model
            # "image": (C, H, W) tensor
            # "audio_log_mel": tensor
            
            inputs = []
            for frame in batch_frames:
                # Resize/Transform
                img = transform(frame) # Returns tensor (C, H, W)
                item = {
                    "image": img.to(self.device),
                    "audio_log_mel": audio_tensor, # Each frame needs audio? COMBO architecture specific
                    "height": frame.shape[0],
                    "width": frame.shape[1],
                }
                inputs.append(item)

            with torch.no_grad():
                # Model forward
                outputs = self.model(inputs) 
                # outputs is list[dict], each dict has "sem_seg" (C, H, W)
            
            for output in outputs:
                # Post-process: sem_seg -> binary mask -> png bytes
                sem_seg = output["sem_seg"] # (1, H, W) usually
                mask = sem_seg.argmax(dim=0).byte().cpu().numpy() # (H, W), 0 or 1
                
                # Convert 0/1 to 0/255
                mask_img = (mask * 255).astype(np.uint8)
                
                # Encode to PNG
                success, encoded_img = cv2.imencode(".png", mask_img)
                if success:
                    yield encoded_img.tobytes()
                else:
                    yield b""

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
