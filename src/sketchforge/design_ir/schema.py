"""Design IR schema (version 1.0.0).

The Design IR is the single contract between vision, layout, rendering, editing, evaluation,
repair and code generation. Coordinates are *design-space pixels* with the origin at the top-left
of the page, and every component stores its bounding box in absolute page coordinates (not
relative to its parent). Moving a container therefore requires moving its descendants too; the
editor's MoveCommand does that. See docs/DESIGN_IR_SPEC.md.
"""

from __future__ import annotations

import math
import re
from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    field_validator,
    model_validator,
)

from sketchforge.constants import DEFAULT_FONT_FAMILY, PIPELINE_VERSION, SCHEMA_VERSION

_HEX_RE = re.compile(r"^#(?:[0-9a-f]{6}|[0-9a-f]{8})$")
ID_PATTERN = r"^[a-z][a-z0-9_-]{0,63}$"
_ID_RE = re.compile(ID_PATTERN)


def _check_color(value: str) -> str:
    text = value.strip().lower()
    if text in {"transparent", "none"} or _HEX_RE.match(text):
        return text
    raise ValueError(f"invalid color {value!r}: use #rrggbb, #rrggbbaa, 'transparent' or 'none'")


HexColor = Annotated[str, AfterValidator(_check_color)]


class StrictModel(BaseModel):
    """Base for editable IR objects: unknown fields are rejected and assignments re-validated."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class ComponentType(str, Enum):
    PAGE = "page"
    CONTAINER = "container"
    HEADER = "header"
    SIDEBAR = "sidebar"
    FOOTER = "footer"
    CARD = "card"
    BUTTON = "button"
    INPUT = "input"
    TEXT = "text"
    HEADING = "heading"
    IMAGE = "image"
    DIVIDER = "divider"
    CHECKBOX = "checkbox"
    RADIO = "radio"
    UNKNOWN = "unknown"


# Types that normally contain other components.
CONTAINER_TYPES = frozenset(
    {
        ComponentType.PAGE,
        ComponentType.CONTAINER,
        ComponentType.HEADER,
        ComponentType.SIDEBAR,
        ComponentType.FOOTER,
        ComponentType.CARD,
    }
)


class BBox(BaseModel):
    """Axis-aligned box. Immutable: edits replace the whole box so every change is recorded."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    x: float
    y: float
    w: float
    h: float

    @field_validator("x", "y", "w", "h")
    @classmethod
    def _finite_and_rounded(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("coordinates must be finite numbers")
        return round(value, 3)

    @model_validator(mode="after")
    def _positive_size(self) -> BBox:
        if self.w <= 0 or self.h <= 0:
            raise ValueError(f"width and height must be > 0 (got w={self.w}, h={self.h})")
        return self

    @property
    def x2(self) -> float:
        return self.x + self.w

    @property
    def y2(self) -> float:
        return self.y + self.h

    @property
    def cx(self) -> float:
        return self.x + self.w / 2.0

    @property
    def cy(self) -> float:
        return self.y + self.h / 2.0

    @property
    def area(self) -> float:
        return self.w * self.h


class Typography(StrictModel):
    font_family: str = DEFAULT_FONT_FAMILY
    font_size: float = Field(16.0, ge=6.0, le=200.0)
    font_weight: int = Field(400, ge=100, le=900)
    line_height: float = Field(1.3, ge=0.8, le=3.0)
    text_align: Literal["left", "center", "right"] = "left"
    color: HexColor = "#111827"


class Style(StrictModel):
    fill: HexColor = "transparent"
    stroke: HexColor = "none"
    stroke_width: float = Field(0.0, ge=0.0, le=32.0)
    corner_radius: float = Field(0.0, ge=0.0, le=500.0)
    opacity: float = Field(1.0, ge=0.0, le=1.0)


class LayoutSpec(StrictModel):
    """How a container arranges its children. Geometry stays authoritative; this is a constraint
    and a code-generation hint. ``inferred`` marks values guessed from the sketch."""

    mode: Literal["absolute", "flex", "grid"] = "absolute"
    direction: Literal["row", "column"] = "column"
    gap: float = Field(0.0, ge=0.0)
    padding: float = Field(0.0, ge=0.0)
    align_items: Literal["start", "center", "end", "stretch"] = "start"
    justify_content: Literal["start", "center", "end", "space-between"] = "start"
    columns: int | None = Field(None, ge=1)
    inferred: bool = False


class Interaction(StrictModel):
    event: Literal["click", "submit", "change", "hover"] = "click"
    action: Literal["none", "navigate", "submit_form", "toggle", "open_modal"] = "none"
    target: str | None = None
    inferred: bool = True


class DetectionInfo(StrictModel):
    """Provenance and uncertainty for a component that came from an image."""

    confidence: float = Field(1.0, ge=0.0, le=1.0)
    source: Literal["heuristic", "model", "user", "synthetic", "remote"] = "heuristic"
    source_bbox: BBox | None = None  # box in original-image pixels
    type_scores: dict[str, float] = Field(default_factory=dict)
    evidence: list[str] = Field(default_factory=list)
    ambiguous: bool = False


class CodeMapping(StrictModel):
    """Where this component lands in generated code (filled in by the generation phase)."""

    component_name: str | None = None
    file_path: str | None = None


class Component(StrictModel):
    id: str = Field(pattern=ID_PATTERN)
    type: ComponentType
    name: str | None = Field(None, max_length=120)
    parent_id: str | None = Field(None, pattern=ID_PATTERN)
    bbox: BBox
    z_index: int = 0
    text: str | None = Field(None, max_length=2000)
    text_is_inferred: bool = False
    typography: Typography | None = None
    style: Style = Field(default_factory=Style)
    layout: LayoutSpec | None = None
    detection: DetectionInfo | None = None
    states: list[str] = Field(default_factory=lambda: ["default"])
    interactions: list[Interaction] = Field(default_factory=list)
    visible: bool = True
    locked: bool = False
    editable: list[str] = Field(default_factory=lambda: ["text", "bbox", "style", "typography"])
    codegen: CodeMapping | None = None


class Viewport(StrictModel):
    width: int = Field(1024, ge=1, le=20000)
    height: int = Field(768, ge=1, le=20000)
    device: Literal["desktop", "tablet", "mobile", "custom"] = "desktop"


class Page(StrictModel):
    width: float = Field(gt=0, le=20000)
    height: float = Field(gt=0, le=20000)
    background: HexColor = "#ffffff"
    viewport: Viewport = Field(default_factory=Viewport)


class SourceTransform(StrictModel):
    """Maps original-image pixels to design pixels: ``design = (source - offset) * scale``."""

    scale: float = Field(gt=0)
    offset_x: float = 0.0
    offset_y: float = 0.0


class DocumentMetadata(StrictModel):
    source_image_sha256: str | None = None
    source_size: tuple[int, int] | None = None  # (width, height) of the original image
    source_transform: SourceTransform | None = None
    pipeline_version: str = PIPELINE_VERSION
    notes: list[str] = Field(default_factory=list)


class DesignDocument(StrictModel):
    schema_version: str = SCHEMA_VERSION
    document_id: str = Field(pattern=ID_PATTERN)
    name: str = Field("Untitled design", max_length=200)
    page: Page
    root_id: str = Field(pattern=ID_PATTERN)
    components: list[Component]
    metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)

    _index: dict[str, Component] | None = PrivateAttr(default=None)
    _children: dict[str, list[str]] | None = PrivateAttr(default=None)

    # ------------------------------------------------------------------ equality & index
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DesignDocument):
            return NotImplemented
        return self.model_dump() == other.model_dump()

    __hash__ = None  # type: ignore[assignment]

    def invalidate_index(self) -> None:
        """Call after any structural change (add/remove/reparent/replace components)."""
        self._index = None
        self._children = None

    def _ensure_index(self) -> None:
        if self._index is not None and len(self._index) == len(self.components):
            return
        index: dict[str, Component] = {}
        for comp in self.components:
            index[comp.id] = comp
        children: dict[str, list[tuple[int, int, str]]] = {}
        for order, comp in enumerate(self.components):
            if comp.parent_id is not None:
                children.setdefault(comp.parent_id, []).append((comp.z_index, order, comp.id))
        self._index = index
        self._children = {pid: [cid for _, _, cid in sorted(items)] for pid, items in children.items()}

    # ------------------------------------------------------------------ accessors
    def get(self, component_id: str) -> Component | None:
        self._ensure_index()
        assert self._index is not None
        return self._index.get(component_id)

    def require(self, component_id: str) -> Component:
        comp = self.get(component_id)
        if comp is None:
            raise KeyError(f"no component with id {component_id!r}")
        return comp

    def children_ids(self, component_id: str) -> list[str]:
        self._ensure_index()
        assert self._children is not None
        return list(self._children.get(component_id, []))

    def children_of(self, component_id: str) -> list[Component]:
        return [self.require(cid) for cid in self.children_ids(component_id)]

    @property
    def root(self) -> Component:
        return self.require(self.root_id)

    def snapshot(self) -> dict[str, Any]:
        """Plain-data copy for undo/rollback. Restore with :meth:`restore`."""
        return self.model_dump(mode="python")

    def restore(self, snapshot: dict[str, Any]) -> None:
        restored = DesignDocument.model_validate(snapshot)
        self.schema_version = restored.schema_version
        self.name = restored.name
        self.page = restored.page
        self.root_id = restored.root_id
        self.components = restored.components
        self.metadata = restored.metadata
        self.invalidate_index()


def is_valid_id(value: str) -> bool:
    return bool(_ID_RE.match(value))
