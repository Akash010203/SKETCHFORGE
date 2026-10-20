"""Project, page, and document metadata entities."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, PrivateAttr

from sketchforge.constants import PIPELINE_VERSION, SCHEMA_VERSION
from sketchforge.domain.base import StrictModel
from sketchforge.domain.component import Component, ID_PATTERN, HexColor

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
