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
        # Find weight file (simple lookup)
        # Assuming avsegformer uses avsegformer/v0/weights.pth
        # You can make this dynamic based on algorithm
        weight_path = str(settings.models_dir / algorithm / "v0" / "S4_res50.pth")

        try:
            # Check if we should run real inference (if weight exists) or placeholder
            import os
            # Simple check: if algorithm is avsegformer (or others) and file exists, run real
            # Otherwise fallback to placeholder
            
            # For this demo, let's force placeholder if file missing, real if present
            # But the user asked for real inference for uploaded model
            
            use_real = algorithm in ["avsegformer", "combo", "vct"] and os.path.exists(weight_path)
            
            if use_real:
                await self._manager.update(task_id, message=f"正在加载模型 {algorithm}...")
                
                # Run real inference in thread pool
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
                await self._manager.update(task_id, total_frames=total_frames, current_frame=0, message="占位推理中 (未找到权重)")
                for i in range(1, total_frames + 1):
                    await asyncio.sleep(0.02)
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
