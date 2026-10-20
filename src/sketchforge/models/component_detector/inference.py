"""In-process inference wrapper for the trained ComponentDetector.

Loads a checkpoint, runs the model on a preprocessed image, decodes
detections, applies NMS, and returns a list of Detection objects.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass  # torch imported at call time


class ComponentDetectorInference:
    """Thin wrapper around the trained ComponentDetector for in-process inference."""

    def __init__(self, checkpoint_path: Path, device: str = "auto"):
        try:
            import torch
            from sketchforge.models.component_detector.architecture import ComponentDetector
            from sketchforge.models.device import get_device
        except ImportError as e:
            raise ImportError("PyTorch is required for model inference.") from e

        self._device = get_device(device if device != "auto" else None)
        ckpt = torch.load(str(checkpoint_path), map_location=self._device)

        num_classes = ckpt.get("config", {}).get("num_classes", 10)
        self._model = ComponentDetector(num_classes=num_classes)
        self._model.load_state_dict(ckpt["model_state_dict"])
        self._model.to(self._device)
        self._model.eval()
        self._checkpoint_meta = {
            "epoch": ckpt.get("epoch"),
            "metrics": ckpt.get("metrics", {}),
        }

    def predict(
        self,
        image_tensor: "torch.Tensor",
        conf_threshold: float = 0.3,
        nms_threshold: float = 0.5,
        image_wh: tuple[int, int] | None = None,
    ) -> list:
        """Run inference on a pre-normalised image tensor (C, H, W) or (1, C, H, W)."""
        import torch
        from sketchforge.models.component_detector.decoder import decode, nms

        if image_tensor.dim() == 3:
            image_tensor = image_tensor.unsqueeze(0)
        image_tensor = image_tensor.to(self._device)

        with torch.no_grad():
            outputs = self._model(image_tensor)

        class_logits = outputs.get("class_logits") if isinstance(outputs, dict) else outputs
        box_preds    = outputs.get("box_preds")    if isinstance(outputs, dict) else None

        dets = decode(class_logits, box_preds, conf_threshold, image_wh)
        return nms(dets, iou_threshold=nms_threshold)

    @property
    def checkpoint_meta(self) -> dict:
        return self._checkpoint_meta
