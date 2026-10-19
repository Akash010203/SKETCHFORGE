"""Hierarchy inference from containment.

Decides which detection is the child of which, and in what reading order. Alignment, spacing and
repeated-pattern analysis operate on the Design IR (src/sketchforge/layout/) so the same rules run
on detected, edited and repaired documents alike.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sketchforge.vision.component_detection import CONTAINER_TYPES, Detection, area_fraction_inside


@dataclass
class LayoutInference:
    parent: dict[int, int | None]  # detection uid -> parent uid (None = child of the page)
    order: list[int]  # parents before children, siblings in reading order
    notes: list[str] = field(default_factory=list)

    def children_of(self, uid: int | None) -> list[int]:
        return [u for u in self.order if self.parent[u] == uid]


def _center_in(inner: tuple, outer: tuple) -> bool:
    cx, cy = inner[0] + inner[2] / 2, inner[1] + inner[3] / 2
    return outer[0] <= cx <= outer[0] + outer[2] and outer[1] <= cy <= outer[1] + outer[3]


def infer_hierarchy(detections: list[Detection]) -> LayoutInference:
    containers = [d for d in detections if d.type in CONTAINER_TYPES]
    parent: dict[int, int | None] = {}
    notes: list[str] = []
    for d in detections:
        best: Detection | None = None
        for c in containers:
            if c.uid == d.uid or c.area <= d.area:
                continue
            thin = min(d.bbox[2], d.bbox[3]) <= 8  # dividers: test by centre, not by area
            inside = _center_in(d.bbox, c.bbox) if thin else area_fraction_inside(d.bbox, c.bbox) >= 0.8
            if inside and (best is None or c.area < best.area):
                best = c
        parent[d.uid] = best.uid if best else None
        if d.type in CONTAINER_TYPES and best is None and d.type in ("card", "container"):
            notes.append(f"{d.type} #{d.uid} is not inside any other container")

    def reading_key(uid: int) -> tuple[int, float]:
        d = detections[uid]
        return (round(d.bbox[1] / 10), d.bbox[0])

    order: list[int] = []

    def walk(parent_uid: int | None) -> None:
        for uid in sorted((u for u, p in parent.items() if p == parent_uid), key=reading_key):
            order.append(uid)
            walk(uid)

    walk(None)
    return LayoutInference(parent, order, notes)
