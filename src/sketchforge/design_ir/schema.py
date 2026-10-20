"""Backward-compatible exports for the versioned Design IR domain models.

The model definitions live in ``sketchforge.domain``; this module remains the stable import path
used by existing callers and serialisation code.
"""

from sketchforge.domain.component import (
    BBox, CodeMapping, Component, ComponentType, DetectionInfo, HexColor, ID_PATTERN,
    StrictModel, Style, Typography, is_valid_id,
)
from sketchforge.domain.interaction import Interaction
from sketchforge.domain.layout import CONTAINER_TYPES, LayoutSpec
from sketchforge.domain.project import (
    DesignDocument, DocumentMetadata, Page, SourceTransform, Viewport,
)

__all__ = [
    "CONTAINER_TYPES", "BBox", "CodeMapping", "Component", "ComponentType",
    "DesignDocument", "DetectionInfo", "DocumentMetadata", "HexColor", "ID_PATTERN",
    "Interaction", "LayoutSpec", "Page", "SourceTransform", "StrictModel", "Style",
    "Typography", "Viewport", "is_valid_id",
]
