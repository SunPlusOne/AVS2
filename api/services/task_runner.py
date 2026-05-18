from __future__ import annotations

import asyncio
import functools
import json
import math
import os
import time
from pathlib import Path
from typing import Any, Optional

from api.config import Settings, get_settings
from api.schemas.contracts import TaskMetrics
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

    @staticmethod
    def _scene_to_subset(scene: Optional[str]) -> str:
        key = str(scene or "").strip().lower()
        if key == "multi_source":
            return "ms3"
        return "s4"

    @staticmethod
    def _normalize_scene(scene: Optional[str]) -> str:
        key = str(scene or "").strip().lower()
        if key == "multi_source":
            return "multi_source"
        return "single_source"

    @staticmethod
    def _to_float(raw: object) -> Optional[float]:
        if raw is None:
            return None
        try:
            value = float(raw)
        except Exception:
            return None
        if not math.isfinite(value):
            return None
        return value

    @staticmethod
    def _to_int(raw: object) -> Optional[int]:
        if raw is None:
            return None
        try:
            value = int(raw)
        except Exception:
            return None
        if value <= 0:
            return None
        return value

    async def _resolve_scene(
        self,
        *,
        task_id: str,
        algorithm: str,
        file_id: str,
        scene: Optional[str],
        settings: Settings,
    ) -> str:
        if str(algorithm).strip().lower() == "avis":
            fixed = "single_source"
            await self._manager.update(task_id, resolved_scene=fixed)
            return fixed

        normalized = self._normalize_scene(scene)
        await self._manager.update(task_id, resolved_scene=normalized)
        return normalized

    def _load_report(self, *, task_id: str, settings: Settings) -> dict[str, Any]:
        p = settings.results_dir / f"{task_id}.report.json"
        if not p.exists():
            return {}
        try:
            payload = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if isinstance(payload, dict):
            return payload
        return {}

    def _metrics_from_report(self, report: dict[str, Any], *, fallback_cost_ms: int) -> Optional[TaskMetrics]:
        metrics = report.get("metrics") if isinstance(report.get("metrics"), dict) else {}
        processing = report.get("processing") if isinstance(report.get("processing"), dict) else {}

        jaccard = self._to_float(metrics.get("jaccard"))
        if jaccard is None:
            jaccard = self._to_float(metrics.get("J"))
        if jaccard is None:
            jaccard = self._to_float(metrics.get("mIoU"))
        if jaccard is None:
            jaccard = self._to_float(metrics.get("M_J"))
        if jaccard is None:
            jaccard = self._to_float(metrics.get("mJ"))

        f_measure = self._to_float(metrics.get("f_measure"))
        if f_measure is None:
            f_measure = self._to_float(metrics.get("F"))
        if f_measure is None:
            f_measure = self._to_float(metrics.get("F-score"))
        if f_measure is None:
            f_measure = self._to_float(metrics.get("M_F"))
        if f_measure is None:
            f_measure = self._to_float(metrics.get("mF"))

        jf_mean = self._to_float(metrics.get("jf_mean"))
        if jf_mean is None:
            jf_mean = self._to_float(metrics.get("J&F"))

        map_score = self._to_float(metrics.get("map"))
        if map_score is None:
            map_score = self._to_float(metrics.get("mAP"))

        hota = self._to_float(metrics.get("hota"))
        if hota is None:
            hota = self._to_float(metrics.get("HOTA"))

        fsla = self._to_float(metrics.get("fsla"))
        if fsla is None:
            fsla = self._to_float(metrics.get("FSLA"))

        total_inference_ms = self._to_int(processing.get("total_ms"))
        if total_inference_ms is None:
            total_inference_ms = self._to_int(metrics.get("total_inference_ms"))
        if total_inference_ms is None:
            total_inference_ms = fallback_cost_ms

        processed_frames = self._to_int(processing.get("processed_frames"))
        if processed_frames is None:
            processed_frames = self._to_int(metrics.get("processed_frames"))
        if processed_frames is None:
            processed_frames = self._to_int(report.get("frames"))
        if processed_frames is None:
            coverage = report.get("mask_coverage_pct_by_frame")
            if isinstance(coverage, list):
                processed_frames = len(coverage)

        avg_frame_ms = self._to_float(processing.get("avg_frame_ms"))
        if avg_frame_ms is None:
            avg_frame_ms = self._to_float(metrics.get("avg_frame_ms"))
        if avg_frame_ms is None and processed_frames:
            avg_frame_ms = float(total_inference_ms) / float(processed_frames)

        if (
            jaccard is None
            and f_measure is None
            and jf_mean is None
            and map_score is None
            and hota is None
            and fsla is None
            and not processed_frames
        ):
            return None

        return TaskMetrics(
            jaccard=jaccard,
            f_measure=f_measure,
            jf_mean=jf_mean,
            map=map_score,
            hota=hota,
            fsla=fsla,
            total_inference_ms=total_inference_ms,
            avg_frame_ms=avg_frame_ms,
            processed_frames=processed_frames,
        )

    def _get_algo_meta(self, algorithm: str) -> dict[str, Any]:
        try:
            items = self._algorithms_repo.list_all()
        except Exception:
            return {}
        for item in items:
            if str(item.get("id", "")).strip().lower() == algorithm.lower():
                return item
        return {}

    def _build_weight_candidates(
        self,
        *,
        algorithm: str,
        settings: Settings,
        scene: Optional[str],
        subset: str,
    ) -> list[str]:
        algo_meta = self._get_algo_meta(algorithm)
        version = str(algo_meta.get("version", "")).strip() or "v0"
        meta_weight_path = str(algo_meta.get("weight_path", "")).strip()
        has_scene = bool(str(scene or "").strip()) and algorithm != "avis"

        candidates: list[str] = []
        seen: set[str] = set()

        def add(path_value: str) -> None:
            value = str(path_value or "").strip()
            if not value or value in seen:
                return
            seen.add(value)
            candidates.append(value)

        # Env var overrides have highest priority.
        add(os.getenv(f"AVS_WEIGHT_{algorithm.upper()}_{subset.upper()}", ""))
        if not has_scene:
            add(os.getenv(f"AVS_WEIGHT_{algorithm.upper()}", ""))
        add(os.getenv("AVS_WEIGHT_PATH", ""))

        # Metadata path from algorithms.json should remain a fallback even when
        # scene selection is enabled, because admin uploads are persisted there.
        add(meta_weight_path)
        if meta_weight_path:
            basename = Path(meta_weight_path.replace("\\", "/")).name
            if basename:
                add(str(settings.models_dir / algorithm / version / basename))
                add(str(settings.models_dir / algorithm / "v0" / basename))

        # Conventional local locations.
        if subset == "s4":
            add(str(settings.models_dir / algorithm / version / "S4_res50.pth"))
            add(str(settings.models_dir / algorithm / "v0" / "S4_res50.pth"))
        elif subset == "ms3":
            add(str(settings.models_dir / algorithm / version / "MS3_res50.pth"))
            add(str(settings.models_dir / algorithm / "v0" / "MS3_res50.pth"))
        if not has_scene or subset == "s4":
            add(str(settings.models_dir / algorithm / "builtin" / "S4_res50.pth"))
        if has_scene:
            add(str(settings.models_dir / algorithm / subset / "model_best.pth"))
        else:
            add(str(settings.models_dir / algorithm / version / "model_best.pth"))
            add(str(settings.models_dir / algorithm / "v0" / "model_best.pth"))

        if algorithm == "combo":
            combo_root = os.getenv("AVS_COMBO_ROOT", "").strip() or "/root/autodl-tmp/COMBO-AVS"
            if subset == "s4":
                # Prefer PVTV2-B5 checkpoints for S4 when both backbones are available.
                add(str(Path(combo_root) / "checkpoints" / "avs_s4" / "COMBO_PVTV2B5_bs8_80k" / "model_best.pth"))
                add("/root/autodl-tmp/S4_res50.pth")
                add("/root/S4_res50.pth")
                add(str(Path(combo_root) / "checkpoints" / "avs_s4" / "COMBO_R50_bs8_80k" / "model_best.pth"))
                add(str(Path(combo_root) / "checkpoints" / "avs_s4_old" / "COMBO_R50_bs8_80k" / "model_best.pth"))
            elif subset == "ms3":
                add(str(Path(combo_root) / "checkpoints" / "avs_ms3" / "COMBO_R50_bs8_20k" / "model_best.pth"))
                ms3_dir = Path(combo_root) / "checkpoints" / "avs_ms3"
                if ms3_dir.exists():
                    for p in sorted(ms3_dir.rglob("model_best.pth")):
                        add(str(p))
        elif algorithm == "vct":
            vct_root = os.getenv("AVS_VCT_ROOT", "").strip()
            vct_root = vct_root or "/root/autodl-tmp/VCT_AVS"
            if subset == "s4":
                add(str(Path(vct_root) / "output" / "s4_swinb_384" / "model_best.pth"))
                add("/root/autodl-tmp/VCT_AVS/output/s4_swinb_384/model_best.pth")
                add("/root/VCT_AVS/output/s4_swinb_384/model_best.pth")
            elif subset == "ms3":
                add(str(Path(vct_root) / "output" / "ms3_swinb_384" / "model_best.pth"))
                add("/root/autodl-tmp/VCT_AVS/output/ms3_swinb_384/model_best.pth")
                add("/root/VCT_AVS/output/ms3_swinb_384/model_best.pth")
        elif algorithm == "avsegformer":
            project_root = Path(__file__).resolve().parent.parent.parent
            avsegformer_root = os.getenv("AVS_AVSEGFORMER_ROOT", "").strip()
            avsegformer_root = avsegformer_root or str(project_root / "api" / "third_party" / "AVSegFormer")
            if subset == "s4":
                add(str(settings.models_dir / algorithm / version / "S4_best.pth"))
                add(str(settings.models_dir / algorithm / "builtin" / "S4_best.pth"))
                add(str(settings.models_dir / algorithm / subset / "S4_best.pth"))
                add(str(Path(avsegformer_root) / "work_dir" / "AVSegFormer_pvt2_s4" / "S4_best.pth"))
                add(str(Path(avsegformer_root) / "work_dir" / "AVSegFormer_res50_s4" / "S4_best.pth"))
            elif subset == "ms3":
                add(str(settings.models_dir / algorithm / version / "MS3_best.pth"))
                add(str(settings.models_dir / algorithm / "builtin" / "MS3_best.pth"))
                add(str(settings.models_dir / algorithm / subset / "MS3_best.pth"))
                add(str(Path(avsegformer_root) / "work_dir" / "AVSegFormer_pvt2_ms3" / "MS3_best.pth"))
                add(str(Path(avsegformer_root) / "work_dir" / "AVSegFormer_res50_ms3" / "MS3_best.pth"))
        elif algorithm == "mavsnet":
            project_root = Path(__file__).resolve().parent.parent.parent
            mavsnet_root = os.getenv("AVS_MAVSNET_ROOT", "").strip()
            mavsnet_root = mavsnet_root or str(project_root / "api" / "third_party" / "mavsnet-avsegformer")
            if subset == "s4":
                add(str(settings.models_dir / algorithm / version / "S4_best.pth"))
                add(str(settings.models_dir / algorithm / "builtin" / "S4_best.pth"))
                add(str(settings.models_dir / algorithm / subset / "S4_best.pth"))
                add(str(Path(mavsnet_root) / "work_dir" / "MAVSNet_pvt2_s4" / "S4_best.pth"))
                add(str(Path(mavsnet_root) / "work_dir" / "MAVSNet_res50_s4" / "S4_best.pth"))
            elif subset == "ms3":
                add(str(settings.models_dir / algorithm / version / "MS3_best.pth"))
                add(str(settings.models_dir / algorithm / "builtin" / "MS3_best.pth"))
                add(str(settings.models_dir / algorithm / subset / "MS3_best.pth"))
                add(str(Path(mavsnet_root) / "work_dir" / "MAVSNet_pvt2_ms3" / "MS3_best.pth"))
                add(str(Path(mavsnet_root) / "work_dir" / "MAVSNet_res50_ms3" / "MS3_best.pth"))
        elif algorithm == "avis":
            project_root = Path(__file__).resolve().parent.parent.parent
            avis_root = os.getenv("AVS_AVIS_ROOT", "").strip()
            avis_root = avis_root or str(project_root / "api" / "third_party" / "avis")
            add(str(settings.models_dir / algorithm / version / "AVISM_SwinL_COCO.pth"))
            add(str(settings.models_dir / algorithm / version / "AVISM_SwinL_IN.pth"))
            add(str(settings.models_dir / algorithm / version / "AVISM_R50_COCO.pth"))
            add(str(settings.models_dir / algorithm / version / "AVISM_R50_IN.pth"))
            add(str(settings.models_dir / algorithm / "builtin" / "AVISM_SwinL_COCO.pth"))
            add(str(settings.models_dir / algorithm / "builtin" / "AVISM_SwinL_IN.pth"))
            add(str(settings.models_dir / algorithm / "builtin" / "AVISM_R50_COCO.pth"))
            add(str(settings.models_dir / algorithm / "builtin" / "AVISM_R50_IN.pth"))
            add(str(settings.models_dir / algorithm / "AVISM_SwinL_COCO.pth"))
            add(str(settings.models_dir / algorithm / "AVISM_SwinL_IN.pth"))
            add(str(settings.models_dir / algorithm / "AVISM_R50_COCO.pth"))
            add(str(settings.models_dir / algorithm / "AVISM_R50_IN.pth"))
            add(str(settings.models_dir / algorithm / "model_best.pth"))
            add(str(Path(avis_root) / "checkpoints" / "AVISM_SwinL_COCO.pth"))
            add(str(Path(avis_root) / "checkpoints" / "AVISM_SwinL_IN.pth"))
            add(str(Path(avis_root) / "checkpoints" / "AVISM_R50_COCO.pth"))
            add(str(Path(avis_root) / "checkpoints" / "AVISM_R50_IN.pth"))
            add(str(Path(avis_root) / "checkpoints" / "model_best.pth"))
            checkpoints_dir = Path(avis_root) / "checkpoints"
            if checkpoints_dir.exists():
                for p in sorted(checkpoints_dir.rglob("*.pth")):
                    add(str(p))

        algo_model_dir = settings.models_dir / algorithm
        if algo_model_dir.exists():
            if has_scene:
                subset_dir = algo_model_dir / subset
                if subset_dir.exists():
                    for p in sorted(subset_dir.rglob("*.pth")):
                        add(str(p))
            else:
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

    def _resolve_weight_path(
        self,
        *,
        algorithm: str,
        settings: Settings,
        scene: Optional[str],
        subset: str,
    ) -> tuple[str, list[str]]:
        checked_paths: list[str] = []
        seen_checked: set[str] = set()

        for raw_candidate in self._build_weight_candidates(
            algorithm=algorithm,
            settings=settings,
            scene=scene,
            subset=subset,
        ):
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
        subset: str,
    ) -> None:
        """Run local inference and keep task progress moving while subprocess works."""
        total_frames = None
        try:
            current = await self._manager.get(task_id)
            total_frames = current.total_frames
        except Exception:
            total_frames = None

        infer_task = asyncio.create_task(
            self._to_thread(
                self._inference.run_inference,
                task_id=task_id,
                file_id=file_id,
                algorithm=algorithm,
                weight_path=weight_path,
                subset=subset,
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

            current_frame = None
            if total_frames and progress > 20:
                current_frame = max(1, min(total_frames, int(round(total_frames * progress / 100.0))))
                msg = f"正在处理第 {current_frame} 帧 / 共 {total_frames} 帧"

            await self._manager.update(
                task_id,
                progress=progress,
                message=msg,
                current_frame=current_frame,
                total_frames=total_frames,
            )
            await asyncio.sleep(2)

        await infer_task

    async def run(self, *, task_id: str, file_id: str, algorithm: str, scene: Optional[str] = None) -> None:
        await self._manager.update(task_id, status="running", progress=0, message="开始预处理")
        start = time.time()

        settings = get_settings()
        resolved_scene = await self._resolve_scene(
            task_id=task_id,
            algorithm=algorithm,
            file_id=file_id,
            scene=scene,
            settings=settings,
        )
        subset = self._scene_to_subset(resolved_scene)

        weight_path, checked_weight_paths = self._resolve_weight_path(
            algorithm=algorithm,
            settings=settings,
            scene=resolved_scene,
            subset=subset,
        )

        try:
            # Logic:
            # 1. If remote_inference_url is set, ALWAYS try remote inference (regardless of local weight existence)
            # 2. Else, check local weight. If exists, run local subprocess.
            # 3. Else, fallback to placeholder simulation.
            
            should_use_remote = bool(settings.remote_inference_url)
            has_local_weight = bool(weight_path) and os.path.isfile(weight_path)
            supports_local_inference = algorithm in {"combo", "vct", "avsegformer", "mavsnet", "avis"}
            
            if should_use_remote:
                await self._manager.update(task_id, message=f"正在请求远程推理 ({algorithm})...")
                await self._to_thread(
                    self._inference.run_inference,
                    task_id=task_id,
                    file_id=file_id,
                    algorithm=algorithm,
                    weight_path=weight_path,  # Passed but might be ignored by remote logic
                    subset=subset,
                )
                
            elif supports_local_inference and has_local_weight:
                await self._manager.update(task_id, progress=2, message=f"正在加载本地模型 {algorithm}...")
                await self._run_local_with_heartbeat(
                    task_id=task_id,
                    file_id=file_id,
                    algorithm=algorithm,
                    weight_path=weight_path,
                    subset=subset,
                )

            elif supports_local_inference and not has_local_weight:
                checked_preview = "\n".join(f"- {p}" for p in checked_weight_paths[:8])
                raise FileNotFoundError(
                    f"未找到 {algorithm} 本地权重文件（场景: {resolved_scene}，子集: {subset}）。"
                    f"请设置 AVS_WEIGHT_{algorithm.upper()}_{subset.upper()}。\n"
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
                    await self._manager.update(
                        task_id,
                        progress=p,
                        current_frame=i,
                        message=f"正在处理第 {i} 帧 / 共 {total_frames} 帧",
                    )
                
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
        report = self._load_report(task_id=task_id, settings=settings)
        metrics = self._metrics_from_report(report, fallback_cost_ms=cost_ms)

        report_frames = self._to_int(report.get("frames")) if report else None
        if report_frames is None and metrics and metrics.processed_frames:
            report_frames = int(metrics.processed_frames)
        report_duration = self._to_float(report.get("duration_seconds")) if report else None
        report_fps = self._to_float(report.get("fps")) if report else None
        report_width = self._to_int(report.get("width")) if report else None
        report_height = self._to_int(report.get("height")) if report else None

        msg = f"完成耗时 {cost_ms}ms"
        await self._manager.update(
            task_id,
            status="completed",
            progress=100,
            message=msg,
            current_frame=report_frames,
            total_frames=report_frames,
            fps=report_fps,
            duration_seconds=report_duration,
            width=report_width,
            height=report_height,
            metrics=metrics,
        )
        log_json(self._logger, "INFO", "task_completed", {"task_id": task_id, "ms": cost_ms})
