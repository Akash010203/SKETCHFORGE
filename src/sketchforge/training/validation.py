"""Validation loop: runs one evaluation epoch and returns EpochMetrics."""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

from sketchforge.training.metrics import EpochMetrics

if TYPE_CHECKING:
    import torch
    from torch.utils.data import DataLoader


def validate_epoch(
    model: "torch.nn.Module",
    loader: "DataLoader",
    criterion: "torch.nn.Module",
    device: "torch.device",
    epoch: int,
    phase: str = "val",
    num_classes: int = 15,
) -> EpochMetrics:
    """Run one pass over ``loader`` without gradients and return metrics."""
    import torch

    model.eval()
    total_loss = 0.0
    total_acc = 0.0
    n_batches = 0
    t0 = time.perf_counter()

    with torch.no_grad():
        for images, targets in loader:
            images = images.to(device, non_blocking=True)
            from sketchforge.training.trainer import _loss_and_metrics
            loss, accuracy = _loss_and_metrics(model, images, targets, num_classes)
            total_loss += loss.item()
            total_acc  += accuracy
            n_batches  += 1

    n = max(n_batches, 1)
    return EpochMetrics(
        epoch=epoch,
        phase=phase,
        loss=total_loss / n,
        accuracy=total_acc / n,
        samples=n_batches * loader.batch_size,  # type: ignore[operator]
        duration_s=time.perf_counter() - t0,
    )
