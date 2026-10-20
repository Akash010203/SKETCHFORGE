"""Source adapters: normalise each external dataset into a common sample format.

Each adapter knows the peculiarities of one upstream source — how its files
are organised, what column names it uses, and how to decode its labels — and
produces :class:`RawSample` objects that the rest of the pipeline works with.

Current adapters
----------------
* ``SyntheticAdapter``  — reads the local ``datasets/synthetic/`` set produced
  by ``synthetic_generator.py``.  Always available.
* ``WebSightAdapter``   — reads the HuggingFace WebSight parquet shards
  (CC-BY-4.0) after they have been placed in ``datasets/raw/websight/``.
* ``SaltSketch2CodeAdapter`` — reads the SALT-NLP Sketch2Code image/HTML pairs
  after they have been placed in ``datasets/raw/salt-sketch2code/``.
* ``ImageCLEFAdapter``  — reads the ImageCLEF DrawnUI 2021 wireframe set after
  manually placing gated data in ``datasets/raw/imageclef-drawnui-2021/``.

Downloading
-----------
Only ``download_pilot()`` performs network IO — and only for public,
licence-clear datasets.  Gated sets must be placed manually.
``download_pilot()`` is intentionally minimal: it fetches the smallest useful
shard, stops, and records provenance.

Architecture constraint
-----------------------
Adapters are offline-first.  If the raw directory is absent, the adapter
returns an empty iterator.  It never crashes the application.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

log = logging.getLogger(__name__)

# ---- Raw sample type -------------------------------------------------------


@dataclass
class RawSample:
    """Normalised single training example from any source."""
    sample_id: str
    source_dataset: str
    image_path: Path | None                   # None when only a URL is available
    html: str | None = None                   # ground-truth HTML (if available)
    label: str | None = None                  # coarse UI component type (if labelled)
    bboxes: list[dict] = field(default_factory=list)  # [{label, x, y, w, h}]
    provenance: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "sample_id": self.sample_id,
            "source_dataset": self.source_dataset,
            "image_path": str(self.image_path) if self.image_path else None,
            "has_html": self.html is not None,
            "label": self.label,
            "bbox_count": len(self.bboxes),
            "provenance": self.provenance,
        }


# ---- Base -------------------------------------------------------------------


class BaseAdapter:
    dataset_id: str = ""

    def samples(self) -> Iterator[RawSample]:
        """Yield :class:`RawSample` objects from the local raw directory."""
        raise NotImplementedError

    def is_available(self) -> bool:
        """Return True when local raw data exists for this adapter."""
        return False


# ---- Synthetic (always available) ------------------------------------------


class SyntheticAdapter(BaseAdapter):
    """Reads the locally-generated synthetic sketch set."""

    dataset_id = "synthetic"

    def __init__(self, data_dir: Path | str | None = None) -> None:
        from sketchforge.utilities.paths import repo_root
        self._dir = Path(data_dir) if data_dir else repo_root() / "datasets" / "synthetic"

    def is_available(self) -> bool:
        return self._dir.is_dir() and any(self._dir.glob("*.png"))

    def samples(self) -> Iterator[RawSample]:
        manifest_path = self._dir / "manifest.json"
        if manifest_path.is_file():
            try:
                records = json.loads(manifest_path.read_text(encoding="utf-8"))
                for rec in records:
                    img = self._dir / rec.get("filename", "")
                    yield RawSample(
                        sample_id=rec.get("sample_id", img.stem),
                        source_dataset=self.dataset_id,
                        image_path=img if img.is_file() else None,
                        bboxes=rec.get("annotations", []),
                        provenance={"layout": rec.get("layout"), "condition": rec.get("condition")},
                    )
                return
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                log.warning("SyntheticAdapter: could not parse manifest: %s", exc)

        # Fallback: iterate PNG files directly
        for img in sorted(self._dir.glob("*.png")):
            yield RawSample(
                sample_id=img.stem,
                source_dataset=self.dataset_id,
                image_path=img,
            )


# ---- WebSight (CC-BY-4.0, public, parquet shards) --------------------------


class WebSightAdapter(BaseAdapter):
    """HuggingFaceM4/WebSight — HTML+screenshot pairs in parquet shards.

    Expected layout after manual or script placement::

        datasets/raw/websight-v02/ (or datasets/raw/websight/)
            data/train-00000-of-00071-*.parquet
            ...
    """

    dataset_id = "websight-v02"

    def __init__(self, data_dir: Path | str | None = None) -> None:
        from sketchforge.utilities.paths import repo_root
        if data_dir:
            self._dir = Path(data_dir)
        else:
            p1 = repo_root() / "datasets" / "raw" / "websight-v02"
            p2 = repo_root() / "datasets" / "raw" / "websight"
            self._dir = p1 if p1.is_dir() else p2

    def is_available(self) -> bool:
        return self._dir.is_dir() and any(self._dir.rglob("*.parquet"))

    def samples(self) -> Iterator[RawSample]:
        try:
            import pyarrow.parquet as pq  # type: ignore[import]
        except ImportError:
            log.warning("WebSightAdapter: pyarrow not installed; run: pip install pyarrow")
            return

        for parquet_file in sorted(self._dir.rglob("*.parquet")):
            try:
                table = pq.read_table(str(parquet_file))
                df = table.to_pydict()
                n = len(df.get("html", [])) if "html" in df else len(df.get("text", []))
                html_col = df.get("html") or df.get("text", [])
                for i in range(n):
                    html = html_col[i] if i < len(html_col) else None
                    img_bytes = df.get("image", {})
                    sid = f"websight-{parquet_file.stem}-{i:06d}"
                    yield RawSample(
                        sample_id=sid,
                        source_dataset=self.dataset_id,
                        image_path=None,   # images are embedded bytes
                        html=html,
                        provenance={
                            "parquet": parquet_file.name,
                            "row": i,
                            "has_image_bytes": bool(img_bytes),
                        },
                    )
            except Exception as exc:  # noqa: BLE001
                log.warning("WebSightAdapter: error reading %s: %s", parquet_file.name, exc)


# ---- SALT-NLP Sketch2Code --------------------------------------------------


class SaltSketch2CodeAdapter(BaseAdapter):
    """SALT-NLP/Sketch2Code hand-drawn sketch → HTML pairs.

    Expected layout::

        datasets/raw/salt-sketch2code/
            sketches/ (or images/)    *.png (sketch photos)
            webpages/ (or html/)      *.html, *.png (ground-truth web designs)
    """

    dataset_id = "salt-sketch2code"

    def __init__(self, data_dir: Path | str | None = None) -> None:
        from sketchforge.utilities.paths import repo_root
        self._dir = (
            Path(data_dir) if data_dir
            else repo_root() / "datasets" / "raw" / "salt-sketch2code"
        )

    def is_available(self) -> bool:
        img_dir = self._resolve_img_dir()
        return img_dir is not None and any(img_dir.glob("*.png"))

    def _resolve_img_dir(self) -> Path | None:
        for candidate in ("sketches", "images", ""):
            d = self._dir / candidate if candidate else self._dir
            if d.is_dir() and any(d.glob("*.png")):
                return d
        return None

    def _resolve_html_dir(self) -> Path:
        for candidate in ("webpages", "html", ""):
            d = self._dir / candidate if candidate else self._dir
            if d.is_dir() and any(d.glob("*.html")):
                return d
        return self._dir / "webpages"

    def samples(self) -> Iterator[RawSample]:
        img_dir = self._resolve_img_dir()
        if not img_dir:
            return
        html_dir = self._resolve_html_dir()

        for img_path in sorted(img_dir.glob("*.png")):
            # Try exact stem match, then base webpage id (e.g. 10303_1 -> 10303)
            html_path = html_dir / (img_path.stem + ".html")
            if not html_path.is_file() and "_" in img_path.stem:
                base_id = img_path.stem.split("_")[0]
                html_path = html_dir / f"{base_id}.html"

            html = html_path.read_text(encoding="utf-8", errors="replace") if html_path.is_file() else None
            yield RawSample(
                sample_id=f"salt-{img_path.stem}",
                source_dataset=self.dataset_id,
                image_path=img_path,
                html=html,
                provenance={"has_html": html is not None, "source_stem": img_path.stem},
            )


# ---- WebCode2M -------------------------------------------------------------


class WebCode2MAdapter(BaseAdapter):
    """WebCode2M (xcodemind/webcode2m) — real-world webpage screenshots with HTML/CSS & bboxes.

    Expected layout::

        datasets/raw/webcode2m/
            data/*.parquet (or *.parquet)
    """

    dataset_id = "webcode2m"

    def __init__(self, data_dir: Path | str | None = None) -> None:
        from sketchforge.utilities.paths import repo_root
        self._dir = Path(data_dir) if data_dir else repo_root() / "datasets" / "raw" / "webcode2m"

    def is_available(self) -> bool:
        return self._dir.is_dir() and any(self._dir.rglob("*.parquet"))

    def samples(self) -> Iterator[RawSample]:
        try:
            import pyarrow.parquet as pq
        except ImportError:
            log.warning("WebCode2MAdapter: pyarrow not installed; run: pip install pyarrow")
            return

        for parquet_file in sorted(self._dir.rglob("*.parquet")):
            try:
                table = pq.read_table(str(parquet_file))
                df = table.to_pydict()
                text_col = df.get("text", [])
                n = len(text_col)
                for i in range(n):
                    html = text_col[i] if i < len(text_col) else None
                    sid = f"webcode2m-{parquet_file.stem}-{i:06d}"
                    bboxes = df.get("bbox", [[]])[i] if "bbox" in df and i < len(df["bbox"]) else []
                    yield RawSample(
                        sample_id=sid,
                        source_dataset=self.dataset_id,
                        image_path=None,
                        html=html,
                        bboxes=bboxes if isinstance(bboxes, list) else [],
                        provenance={"parquet": parquet_file.name, "row": i},
                    )
            except Exception as exc:  # noqa: BLE001
                log.warning("WebCode2MAdapter: error reading %s: %s", parquet_file.name, exc)


# ---- Teklia IAM-line -------------------------------------------------------


class TekliaIAMLineAdapter(BaseAdapter):
    """Teklia IAM-line handwriting OCR dataset.

    Expected layout::

        datasets/raw/teklia-iam-line/
            data/*.parquet (train.parquet, validation.parquet, test.parquet)
    """

    dataset_id = "teklia-iam-line"

    def __init__(self, data_dir: Path | str | None = None) -> None:
        from sketchforge.utilities.paths import repo_root
        self._dir = Path(data_dir) if data_dir else repo_root() / "datasets" / "raw" / "teklia-iam-line"

    def is_available(self) -> bool:
        return self._dir.is_dir() and any(self._dir.rglob("*.parquet"))

    def samples(self) -> Iterator[RawSample]:
        try:
            import pyarrow.parquet as pq
        except ImportError:
            log.warning("TekliaIAMLineAdapter: pyarrow not installed; run: pip install pyarrow")
            return

        for parquet_file in sorted(self._dir.rglob("*.parquet")):
            try:
                table = pq.read_table(str(parquet_file))
                df = table.to_pydict()
                text_col = df.get("text", [])
                for i, text in enumerate(text_col):
                    sid = f"iamline-{parquet_file.stem}-{i:06d}"
                    yield RawSample(
                        sample_id=sid,
                        source_dataset=self.dataset_id,
                        image_path=None,
                        label=str(text) if text is not None else None,
                        provenance={"split": parquet_file.stem, "row": i},
                    )
            except Exception as exc:  # noqa: BLE001
                log.warning("TekliaIAMLineAdapter: error reading %s: %s", parquet_file.name, exc)


# ---- Sketch2Diagram Benchmark ----------------------------------------------


class Sketch2DiagramAdapter(BaseAdapter):
    """DiagramAgent/Sketch2Diagram-Benchmark hand-drawn diagram dataset.

    Expected layout::

        datasets/raw/sketch2diagram/
            Sketch2Diagram Benchmark.zip (or extracted files/folders)
    """

    dataset_id = "sketch2diagram"

    def __init__(self, data_dir: Path | str | None = None) -> None:
        from sketchforge.utilities.paths import repo_root
        self._dir = Path(data_dir) if data_dir else repo_root() / "datasets" / "raw" / "sketch2diagram"

    def is_available(self) -> bool:
        if not self._dir.is_dir():
            return False
        return any(self._dir.rglob("*.png")) or any(self._dir.rglob("*.jpg")) or any(self._dir.glob("*.zip"))

    def samples(self) -> Iterator[RawSample]:
        for img_path in sorted(self._dir.rglob("*")):
            if img_path.suffix.lower() in {".png", ".jpg", ".jpeg"}:
                yield RawSample(
                    sample_id=f"diagram-{img_path.stem}",
                    source_dataset=self.dataset_id,
                    image_path=img_path,
                    provenance={"rel_path": str(img_path.relative_to(self._dir))},
                )


# ---- ImageCLEF DrawnUI 2021 ------------------------------------------------


class ImageCLEFAdapter(BaseAdapter):
    """ImageCLEF DrawnUI 2021 — gated dataset; must be placed manually.

    Expected layout::

        datasets/raw/imageclef-drawnui-2021/
            images/    *.jpg or *.png
            annotations/ *.xml (Pascal VOC bounding boxes, optional)
    """

    dataset_id = "imageclef-drawnui-2021"

    def __init__(self, data_dir: Path | str | None = None) -> None:
        from sketchforge.utilities.paths import repo_root
        self._dir = (
            Path(data_dir) if data_dir
            else repo_root() / "datasets" / "raw" / "imageclef-drawnui-2021"
        )

    def is_available(self) -> bool:
        img_dir = self._dir / "images"
        return img_dir.is_dir() and any(img_dir.glob("*.*"))

    def samples(self) -> Iterator[RawSample]:
        img_dir = self._dir / "images"
        ann_dir = self._dir / "annotations"
        if not img_dir.is_dir():
            return
        for img_path in sorted(img_dir.glob("*")):
            if img_path.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
                continue
            bboxes = _parse_voc_xml(ann_dir / (img_path.stem + ".xml"))
            yield RawSample(
                sample_id=f"imageclef-{img_path.stem}",
                source_dataset=self.dataset_id,
                image_path=img_path,
                bboxes=bboxes,
                provenance={"has_annotations": bool(bboxes)},
            )


# ---------------------------------------------------------------------------
# Pilot downloader (public, licence-clear datasets only)
# ---------------------------------------------------------------------------


def download_pilot(
    dataset_id: str,
    *,
    target_bytes: int = 100 * 1024 * 1024,   # 100 MB default pilot
    force: bool = False,
) -> dict:
    """Download the smallest useful shard of a public dataset.

    This function is the **only** place in the pipeline that initiates a
    network request for external data.  It:

    1. Checks that the dataset is in the manifest and access is ``"public"``.
    2. Refuses gated or rights-unclear datasets with a clear error message.
    3. Downloads exactly one shard / part up to ``target_bytes``.
    4. Records a provenance JSON alongside the downloaded file.

    Returns a summary dict; raises ``ValueError`` on bad input or policy
    violation; raises ``OSError`` / ``requests.RequestException`` on network
    failure.

    Currently only ``websight`` can be downloaded automatically (one parquet
    shard via direct HTTPS).  Add new public datasets here as rights are
    confirmed.
    """
    from sketchforge.utilities.paths import repo_root

    DOWNLOADABLE: dict[str, str] = {
        # dataset_id → direct URL for the first shard / zip file
        "websight": (
            "https://huggingface.co/datasets/HuggingFaceM4/WebSight"
            "/resolve/10d8285c49c88608dcf82f3f76ee58377a3a1216"
            "/data/train-00000-of-00060.parquet"
        ),
        # SALT-NLP Sketch2Code — first parquet shard from HuggingFace
        "salt-sketch2code": (
            "https://huggingface.co/datasets/SALT-NLP/Sketch2Code"
            "/resolve/main/data/train-00000-of-00001.parquet"
        ),
    }

    if dataset_id not in DOWNLOADABLE:
        raise ValueError(
            f"Dataset '{dataset_id}' is not available for automatic download.  "
            "Either it is gated (place files manually) or it has not been cleared "
            "for automatic retrieval.  Check docs/DATASET_AUDIT.md."
        )

    url = DOWNLOADABLE[dataset_id]
    dest_dir = repo_root() / "datasets" / "raw" / dataset_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file = dest_dir / "data" / Path(url.split("/")[-1])
    dest_file.parent.mkdir(parents=True, exist_ok=True)

    if dest_file.exists() and not force:
        return {
            "dataset_id": dataset_id,
            "status": "already_present",
            "path": str(dest_file),
            "bytes": dest_file.stat().st_size,
        }

    try:
        import requests  # type: ignore[import]
    except ImportError as exc:
        raise ImportError("Install requests: pip install requests") from exc

    log.info("Downloading pilot shard for %s from %s", dataset_id, url)
    with requests.get(url, stream=True, timeout=60) as response:
        response.raise_for_status()
        content_length = int(response.headers.get("Content-Length", 0))
        if content_length > target_bytes * 2:
            raise ValueError(
                f"Remote file is {content_length / 1e6:.0f} MB which exceeds the "
                f"{target_bytes * 2 / 1e6:.0f} MB safety limit.  "
                "Increase target_bytes explicitly if intentional."
            )
        downloaded = 0
        hasher = hashlib.sha256()
        with dest_file.open("wb") as fout:
            for chunk in response.iter_content(chunk_size=65536):
                if chunk:
                    fout.write(chunk)
                    hasher.update(chunk)
                    downloaded += len(chunk)
                    if downloaded > target_bytes:
                        log.warning(
                            "Stopped after %.1f MB (pilot limit)", downloaded / 1e6
                        )
                        break

    sha256 = hasher.hexdigest()
    provenance = {
        "dataset_id": dataset_id,
        "source_url": url,
        "sha256": sha256,
        "bytes": downloaded,
        "pilot": True,
    }
    (dest_file.with_suffix(".provenance.json")).write_text(
        json.dumps(provenance, indent=2), encoding="utf-8"
    )
    log.info("Pilot download complete: %s (%.1f MB)", dest_file.name, downloaded / 1e6)
    return {**provenance, "path": str(dest_file)}


# ---------------------------------------------------------------------------
# Adapter registry
# ---------------------------------------------------------------------------

_ADAPTERS: dict[str, type[BaseAdapter]] = {
    "synthetic": SyntheticAdapter,
    "websight": WebSightAdapter,
    "websight-v02": WebSightAdapter,
    "salt-sketch2code": SaltSketch2CodeAdapter,
    "webcode2m": WebCode2MAdapter,
    "teklia-iam-line": TekliaIAMLineAdapter,
    "sketch2diagram": Sketch2DiagramAdapter,
    "imageclef-drawnui-2021": ImageCLEFAdapter,
}


def get_adapter(dataset_id: str, data_dir: Path | str | None = None) -> BaseAdapter:
    """Return the adapter for *dataset_id*, raising ``KeyError`` if unknown."""
    cls = _ADAPTERS[dataset_id]
    return cls(data_dir=data_dir) if data_dir else cls()


def available_adapters() -> list[str]:
    """Return dataset IDs for which local data currently exists."""
    return [did for did, cls in _ADAPTERS.items() if cls().is_available()]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_voc_xml(path: Path) -> list[dict]:
    """Parse a Pascal VOC XML annotation file into a list of bbox dicts."""
    if not path.is_file():
        return []
    try:
        import xml.etree.ElementTree as ET
        tree = ET.parse(str(path))
        bboxes = []
        for obj in tree.findall("object"):
            name_el = obj.find("name")
            bndbox = obj.find("bndbox")
            if name_el is None or bndbox is None:
                continue
            xmin = float(bndbox.findtext("xmin", "0"))
            ymin = float(bndbox.findtext("ymin", "0"))
            xmax = float(bndbox.findtext("xmax", "0"))
            ymax = float(bndbox.findtext("ymax", "0"))
            bboxes.append({
                "label": name_el.text or "unknown",
                "x": xmin,
                "y": ymin,
                "w": xmax - xmin,
                "h": ymax - ymin,
            })
        return bboxes
    except Exception as exc:  # noqa: BLE001
        log.debug("Could not parse VOC XML %s: %s", path.name, exc)
        return []
