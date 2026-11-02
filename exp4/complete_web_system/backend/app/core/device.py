from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def resolve_torch_device(preference: str = "auto") -> int | str:
    """Resolve the configured device for Ultralytics; auto prefers CUDA, then CPU."""
    value = (preference or "auto").strip().lower()
    if value == "cpu":
        return "cpu"

    try:
        import torch

        cuda_available = torch.cuda.is_available()
    except Exception as exc:  # pragma: no cover - defensive for broken torch installs
        logger.warning("Unable to inspect CUDA availability; falling back to CPU: %s", exc)
        return "cpu"

    if value in {"", "auto"}:
        return 0 if cuda_available else "cpu"
    if value.startswith("cuda"):
        if not cuda_available:
            logger.warning("CUDA device requested but unavailable; falling back to CPU")
            return "cpu"
        _, _, index = value.partition(":")
        return int(index) if index.isdigit() else 0
    if value.isdigit():
        if not cuda_available:
            logger.warning("GPU index requested but CUDA is unavailable; falling back to CPU")
            return "cpu"
        return int(value)
    return preference
