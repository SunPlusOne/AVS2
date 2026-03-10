from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import torch


@dataclass(frozen=True)
class TorchRuntimeInfo:
    torch_version: str
    cuda_available: bool
    cuda_device_count: int
    cuda_visible_devices: str | None
    selected_device: str
    selected_device_name: str | None
    force_device_env: str
    require_cuda_env: bool


def _normalize_device_name(raw: str | None) -> str:
    value = str(raw or "").strip().lower()
    if not value or value == "auto":
        return "auto"
    if value.startswith("cuda"):
        return "cuda"
    if value == "cpu":
        return "cpu"
    return "auto"


def resolve_runtime_device(requested_device: str | None = None) -> str:
    forced = _normalize_device_name(os.getenv("AVS_FORCE_DEVICE", "auto"))
    requested = _normalize_device_name(requested_device)
    require_cuda = os.getenv("AVS_REQUIRE_CUDA", "0").strip() == "1"

    desired = requested if requested != "auto" else forced
    cuda_available = torch.cuda.is_available()

    if desired == "cpu":
        return "cpu"

    if desired == "cuda":
        if cuda_available:
            return "cuda"
        if require_cuda:
            raise RuntimeError(
                "CUDA was requested but torch.cuda.is_available() returned False. "
                "Please check the Python environment and CUDA runtime."
            )
        return "cpu"

    if cuda_available:
        return "cuda"

    if require_cuda:
        raise RuntimeError(
            "AVS_REQUIRE_CUDA=1 but CUDA is unavailable in the current process."
        )
    return "cpu"


def get_torch_runtime_info(selected_device: str) -> TorchRuntimeInfo:
    cuda_available = torch.cuda.is_available()
    selected_name: str | None = None
    if selected_device.startswith("cuda") and cuda_available and torch.cuda.device_count() > 0:
        try:
            selected_name = torch.cuda.get_device_name(0)
        except Exception:
            selected_name = None

    return TorchRuntimeInfo(
        torch_version=str(getattr(torch, "__version__", "unknown")),
        cuda_available=cuda_available,
        cuda_device_count=int(torch.cuda.device_count() if cuda_available else 0),
        cuda_visible_devices=os.getenv("CUDA_VISIBLE_DEVICES"),
        selected_device=selected_device,
        selected_device_name=selected_name,
        force_device_env=os.getenv("AVS_FORCE_DEVICE", "auto"),
        require_cuda_env=os.getenv("AVS_REQUIRE_CUDA", "0").strip() == "1",
    )


def format_runtime_info(info: TorchRuntimeInfo) -> str:
    return (
        f"torch={info.torch_version}, "
        f"cuda_available={info.cuda_available}, "
        f"cuda_device_count={info.cuda_device_count}, "
        f"cuda_visible_devices={info.cuda_visible_devices}, "
        f"force_device_env={info.force_device_env}, "
        f"require_cuda_env={info.require_cuda_env}, "
        f"selected_device={info.selected_device}, "
        f"selected_device_name={info.selected_device_name}"
    )


def model_parameter_device(model: Any) -> str:
    if model is None:
        return "none"
    try:
        return str(next(model.parameters()).device)
    except StopIteration:
        return "unknown"
    except Exception:
        return "unknown"


def ensure_model_on_device(model: Any, expected_device: str) -> str:
    current = model_parameter_device(model)
    expected = "cuda" if str(expected_device).startswith("cuda") else "cpu"
    if not current.startswith(expected):
        raise RuntimeError(
            f"Model parameters are on {current}, expected {expected_device}. "
            "This would make inference run on CPU or fail with device mismatch."
        )
    return current
