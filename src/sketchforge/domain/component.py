"""Public component contract exports.

The Design IR schema remains the canonical wire-format definition; this module is the domain
boundary for application code and keeps the domain API independent of schema internals.
"""

from sketchforge.design_ir.schema import (
    BBox,
    CodeMapping,
    Component,
    ComponentType,
    DetectionInfo,
    Style,
    Typography,
)

__all__ = ["BBox", "CodeMapping", "Component", "ComponentType", "DetectionInfo", "Style", "Typography"]
