"""Optional handwritten text recognition using Microsoft's TrOCR handwritten model.

Recognition is opt-in because the model is large and may need to be downloaded on first use.
Set ``SKETCHFORGE_OCR_MODEL`` to a local model directory or Hugging Face model id.
"""

from __future__ import annotations

import os
from functools import lru_cache

import cv2
import numpy as np
from PIL import Image

from sketchforge.vision.text_regions import TextRegion


@lru_cache(maxsize=1)
def _load_model(model_name: str):
    try:
        from transformers import TrOCRProcessor, VisionEncoderDecoderModel
    except ImportError as exc:
        raise RuntimeError(
            "Handwriting OCR needs the optional 'ocr' dependencies; install sketchforge[ocr]."
        ) from exc
    processor = TrOCRProcessor.from_pretrained(model_name)
    model = VisionEncoderDecoderModel.from_pretrained(model_name)
    model.eval()
    return processor, model


def recognize_regions(gray: np.ndarray, regions: list[TextRegion]) -> list[str]:
    """Recognize line crops, returning one string per candidate region.

    Blank or unreadable crops return an empty string, allowing callers to preserve the
    clearly flagged inferred placeholder rather than pretending OCR succeeded.
    """
    model_name = os.environ.get("SKETCHFORGE_OCR_MODEL", "").strip()
    if not model_name:
        return [""] * len(regions)
    processor, model = _load_model(model_name)
    image_h, image_w = gray.shape[:2]
    outputs: list[str] = []
    for region in regions:
        x, y, w, h = region.bbox
        x0, y0 = max(0, int(x)), max(0, int(y))
        x1, y1 = min(image_w, int(np.ceil(x + w))), min(image_h, int(np.ceil(y + h)))
        crop = gray[y0:y1, x0:x1]
        if crop.size == 0:
            outputs.append("")
            continue
        # TrOCR was trained on light backgrounds with dark writing.
        crop = cv2.resize(crop, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
        rgb = cv2.cvtColor(crop, cv2.COLOR_GRAY2RGB)
        pixels = processor(images=Image.fromarray(rgb), return_tensors="pt").pixel_values
        generated = model.generate(pixels, max_new_tokens=64)
        outputs.append(processor.batch_decode(generated, skip_special_tokens=True)[0].strip())
    return outputs
