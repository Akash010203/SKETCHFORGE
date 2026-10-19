"""Training metrics: mAP, per-class AP, and confusion matrix for component detection."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence


@dataclass
class EpochMetrics:
    epoch: int
    phase: str          # "train" | "val" | "test"
    loss: float = 0.0
    cls_loss: float = 0.0
    box_loss: float = 0.0
    accuracy: float = 0.0   # top-1 classification accuracy
    mean_iou: float = 0.0   # mean IoU of detected boxes
    mAP: float = 0.0        # mean Average Precision
    samples: int = 0
    duration_s: float = 0.0

    def to_dict(self) -> dict:
        return {
            "epoch": self.epoch,
            "phase": self.phase,
            "loss": round(self.loss, 6),
            "cls_loss": round(self.cls_loss, 6),
            "box_loss": round(self.box_loss, 6),
            "accuracy": round(self.accuracy, 4),
            "mean_iou": round(self.mean_iou, 4),
            "mAP": round(self.mAP, 4),
            "samples": self.samples,
            "duration_s": round(self.duration_s, 2),
        }

    def summary(self) -> str:
        return (
            f"[{self.phase}] epoch={self.epoch} loss={self.loss:.4f} "
            f"acc={self.accuracy:.3f} IoU={self.mean_iou:.3f} mAP={self.mAP:.3f}"
        )


def compute_iou(pred_boxes: "list[tuple]", true_boxes: "list[tuple]") -> float:
    """Compute mean IoU between predicted and ground-truth boxes.

    Each box is (x, y, w, h) in pixel coordinates.
    Simplified: matches predictions to GT by index order (for smoke tests).
    """
    if not pred_boxes or not true_boxes:
        return 0.0
    ious: list[float] = []
    for pb, tb in zip(pred_boxes, true_boxes):
        px, py, pw, ph = pb
        tx, ty, tw, th = tb
        inter_x = max(0, min(px + pw, tx + tw) - max(px, tx))
        inter_y = max(0, min(py + ph, ty + th) - max(py, ty))
        inter   = inter_x * inter_y
        union   = pw * ph + tw * th - inter
        ious.append(inter / union if union > 0 else 0.0)
    return sum(ious) / len(ious) if ious else 0.0


def compute_accuracy(logits: "torch.Tensor", labels: "torch.Tensor") -> float:
    """Top-1 accuracy from class logits."""
    import torch
    preds = logits.argmax(dim=-1)
    return (preds == labels).float().mean().item()
