from __future__ import annotations

import asyncio
import functools
import os
import time
from pathlib import Path
from typing import Any

from api.config import Settings, get_settings
from api.services.algorithms_repo import AlgorithmsRepo
from api.services.inference_service import InferenceService
from api.services.task_manager import TaskManager
from api.utils.logger import log_json


class TaskRunner:
    def __init__(
        self,
        manager: TaskManager,
        inference: InferenceService,
        algorithms_repo: AlgorithmsRepo,
        logger,
    ) -> None:
        self._manager = manager
        self._inference = inference
        self._algorithms_repo = algorithms_repo
        self._logger = logger

    async def _to_thread(self, fn, /, *args, **kwargs):
        if hasattr(asyncio, "to_thread"):
            return await asyncio.to_thread(fn, *args, **kwargs)
        loop = asyncio.get_running_loop()
        task = functools.partial(fn, *args, **kwargs)
        return await loop.run_in_executor(None, task)

    def _get_algo_meta(self, algorithm: str) -> dict[str, Any]:
        try:
            items = self._algorithms_repo.list_all()
        except Exception:
            return {}
        for item in items:
            if str(item.get("id", "")).strip().lower() == algorithm.lower():
                return item
        return {}

    def _build_weight_candidates(self, *, algorithm: str, settings: Settings) -> list[str]:
        algo_meta = self._get_algo_meta(algorithm)
        version = str(algo_meta.get("version", "")).strip() or "v0"
        meta_weight_path = str(algo_meta.get("weight_path", "")).strip()

        candidates: list[str] = []
        seen: set[str] = set()

        def add(path_value: str) -> None:
            value = str(path_value or "").strip()
            if not value or value in seen:
                return
            seen.add(value)
            candidates.append(value)

        # Env var overrides have highest priority.
        add(os.getenv(f"AVS_WEIGHT_{algorithm.upper()}", ""))
        add(os.getenv("AVS_WEIGHT_PATH", ""))

        # Metadata path from algorithms.json.
        add(meta_weight_path)
        if meta_weight_path:
            basename = Path(meta_weight_path.replace("\\", "/")).name
            if basename:
                add(str(settings.models_dir / algorithm / version / basename))
                add(str(settings.models_dir / algorithm / "v0" / basename))

        # Conventional local locations.
        add(str(settings.models_dir / algorithm / version / "S4_res50.pth"))
        add(str(settings.models_dir / algorithm / "v0" / "S4_res50.pth"))
        add(str(settings.models_dir / algorithm / "builtin" / "S4_res50.pth"))
        add(str(settings.models_dir / algorithm / version / "model_best.pth"))
        add(str(settings.models_dir / algorithm / "v0" / "model_best.pth"))

        if algorithm == "combo":
            # Common AutoDL paths.
            add("/root/autodl-tmp/S4_res50.pth")
            add("/root/S4_res50.pth")
            add("/root/autodl-tmp/COMBO-AVS/checkpoints/avs_s4/COMBO_R50_bs8_80k/model_best.pth")
            add("/root/autodl-tmp/COMBO-AVS/checkpoints/avs_s4/COMBO_PVTV2B5_bs8_80k/model_best.pth")

        algo_model_dir = settings.models_dir / algorithm
        if algo_model_dir.exists():
            for p in sorted(algo_model_dir.rglob("*.pth")):
                add(str(p))

        return candidates

    def _expand_candidate(self, *, raw_path: str, settings: Settings) -> list[str]:
        expanded = os.path.expandvars(os.path.expanduser(raw_path.strip()))
        out: list[str] = []
        seen: set[str] = set()

        def push(path_value: str) -> None:
            normalized = str(Path(path_value))
            if normalized in seen:
                return
            seen.add(normalized)
            out.append(normalized)

        if not expanded:
            return out

        push(expanded)
        if not os.path.isabs(expanded):
            project_root = Path(__file__).resolve().parent.parent.parent
            push(str(project_root / expanded))
            push(str(settings.data_dir / expanded))

        return out

    def _resolve_weight_path(self, *, algorithm: str, settings: Settings) -> tuple[str, list[str]]:
        checked_paths: list[str] = []
        seen_checked: set[str] = set()

        for raw_candidate in self._build_weight_candidates(algorithm=algorithm, settings=settings):
            for candidate in self._expand_candidate(raw_path=raw_candidate, settings=settings):
                if candidate in seen_checked:
                    continue
                seen_checked.add(candidate)
                checked_paths.append(candidate)
                if os.path.isfile(candidate):
                    return candidate, checked_paths

        return "", checked_paths

    async def _run_local_with_heartbeat(
        self,
        *,
        task_id: str,
        file_id: str,
        algorithm: str,
        weight_path: str,
    ) -> None:
        """Run local inference and keep task progress moving while subprocess works."""
        infer_task = asyncio.create_task(
            self._to_thread(
                self._inference.run_inference,
                task_id=task_id,
                file_id=file_id,
                algorithm=algorithm,
                weight_path=weight_path,
            )
        )

        start_ts = time.time()
        while not infer_task.done():
            elapsed = int(time.time() - start_ts)
            if elapsed < 15:
                progress = min(10, 2 + elapsed // 2)
                msg = f"正在加载本地模型 {algorithm}..."
            elif elapsed < 45:
                progress = min(30, 10 + (elapsed - 15))
                msg = f"正在提取视频帧与音频特征 ({elapsed}s)..."
            else:
                progress = min(95, 30 + (elapsed - 45) // 2)
                msg = f"正在执行分割推理 ({elapsed}s)..."

            await self._manager.update(task_id, progress=progress, message=msg)
            await asyncio.sleep(2)

        await infer_task

    async def run(self, *, task_id: str, file_id: str, algorithm: str) -> None:
        await self._manager.update(task_id, status="running", progress=0, message="开始预处理")
        start = time.time()
        
        settings = get_settings()

        weight_path, checked_weight_paths = self._resolve_weight_path(algorithm=algorithm, settings=settings)

        try:
            # Logic:
            # 1. If remote_inference_url is set, ALWAYS try remote inference (regardless of local weight existence)
            # 2. Else, check local weight. If exists, run local subprocess.
            # 3. Else, fallback to placeholder simulation.
            
            should_use_remote = bool(settings.remote_inference_url)
            has_local_weight = bool(weight_path) and os.path.isfile(weight_path)
            supports_local_inference = algorithm == "combo"
            
            if should_use_remote:
                await self._manager.update(task_id, message=f"正在请求远程推理 ({algorithm})...")
                await self._to_thread(
                    self._inference.run_inference,
                    task_id=task_id,
                    file_id=file_id,
                    algorithm=algorithm,
                    weight_path=weight_path # Passed but might be ignored by remote logic
                )
                
            elif supports_local_inference and has_local_weight:
                await self._manager.update(task_id, progress=2, message=f"正在加载本地模型 {algorithm}...")
                await self._run_local_with_heartbeat(
                    task_id=task_id,
                    file_id=file_id,
                    algorithm=algorithm,
                    weight_path=weight_path,
                )

            elif supports_local_inference and not has_local_weight:
                checked_preview = "\n".join(f"- {p}" for p in checked_weight_paths[:8])
                raise FileNotFoundError(
                    f"未找到 {algorithm} 本地权重文件。请在管理员后台上传 .pth，"
                    f"或设置 AVS_WEIGHT_{algorithm.upper()}。\n"
                    f"已尝试路径:\n{checked_preview}"
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
                await self._to_thread(
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
