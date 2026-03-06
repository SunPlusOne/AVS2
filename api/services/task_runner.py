from __future__ import annotations

import asyncio
import time
from typing import Optional

from api.services.inference_service import InferenceService
from api.services.task_manager import TaskManager
from api.utils.logger import log_json
from api.config import get_settings


class TaskRunner:
    def __init__(self, manager: TaskManager, inference: InferenceService, logger) -> None:
        self._manager = manager
        self._inference = inference
        self._logger = logger

    async def run(self, *, task_id: str, file_id: str, algorithm: str) -> None:
        await self._manager.update(task_id, status="running", progress=0, message="开始预处理")
        start = time.time()
        
        settings = get_settings()
        
        # Determine weight path (only used for LOCAL inference)
        # For remote inference, this path might not matter or is handled by remote server
        # But we still need a placeholder to pass to run_inference signature
        
        import os
        from pathlib import Path
        
        # Default path
        weight_path = str(settings.models_dir / algorithm / "v0" / "S4_res50.pth")

        # --- AutoDL Specific Weight Logic ---
        # If on AutoDL (check common paths), try to find weight automatically
        # Common user paths: /root/autodl-tmp/S4_res50.pth, /root/S4_res50.pth
        # Or user mentioned: /root/autodl-tmp/COMBO-AVS/checkpoints/avs_s4/COMBO_R50_bs8_80k/model_best.pth
        
        if algorithm == "combo":
            potential_paths = [
                weight_path, # Standard API path
                "/root/autodl-tmp/S4_res50.pth", # Root of data disk
                "/root/S4_res50.pth", # Root
                "/root/autodl-tmp/COMBO-AVS/checkpoints/avs_s4/COMBO_R50_bs8_80k/model_best.pth", # User specific path
                "/root/autodl-tmp/COMBO-AVS/checkpoints/avs_s4/COMBO_PVTV2B5_bs8_80k/model_best.pth",
            ]
            
            for p in potential_paths:
                if os.path.exists(p):
                    weight_path = p
                    break
        # ------------------------------------

        try:
            # Logic:
            # 1. If remote_inference_url is set, ALWAYS try remote inference (regardless of local weight existence)
            # 2. Else, check local weight. If exists, run local subprocess.
            # 3. Else, fallback to placeholder simulation.
            
            should_use_remote = bool(settings.remote_inference_url)
            has_local_weight = os.path.exists(weight_path)
            
            if should_use_remote:
                await self._manager.update(task_id, message=f"正在请求远程推理 ({algorithm})...")
                await asyncio.to_thread(
                    self._inference.run_inference,
                    task_id=task_id,
                    file_id=file_id,
                    algorithm=algorithm,
                    weight_path=weight_path # Passed but might be ignored by remote logic
                )
                
            elif algorithm in ["avsegformer", "combo", "vct"] and has_local_weight:
                await self._manager.update(task_id, message=f"正在加载本地模型 {algorithm}...")
                await asyncio.to_thread(
                    self._inference.run_inference,
                    task_id=task_id,
                    file_id=file_id,
                    algorithm=algorithm,
                    weight_path=weight_path
                )
                
            else:
                # Fallback to placeholder loop
                total_frames = 200
                msg = "占位推理中 (未配置远程且无本地权重)"
                await self._manager.update(task_id, total_frames=total_frames, current_frame=0, message=msg)
                
                # Simulate progress
                for i in range(1, total_frames + 1, 5): # speed up simulation
                    await asyncio.sleep(0.05)
                    p = int(i * 100 / total_frames)
                    await self._manager.update(task_id, progress=p, current_frame=i)
                
                await self._manager.update(task_id, message="生成结果文件")
                await asyncio.to_thread(
                    self._inference.run_placeholder,
                    task_id=task_id,
                    file_id=file_id,
                    algorithm=algorithm,
                )

        except asyncio.CancelledError:
            return
        except Exception as e:
            await self._manager.update(task_id, status="failed", message=str(e), progress=0)
            log_json(self._logger, "ERROR", "task_failed", {"task_id": task_id, "error": str(e)})
            return

        cost_ms = int((time.time() - start) * 1000)
        msg = f"完成耗时 {cost_ms}ms"
        await self._manager.update(task_id, status="completed", progress=100, message=msg)
        log_json(self._logger, "INFO", "task_completed", {"task_id": task_id, "ms": cost_ms})
