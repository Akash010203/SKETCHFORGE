"""DataLoader factory for the component detector training pipeline.

Wraps the existing ComponentDetectorDataset (models/component_detector/dataset.py)
with train/val/test splits, augmentations, and reproducible shuffling.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from sketchforge.training.config import TrainingConfig
from sketchforge.training.seed import seed_everything

if TYPE_CHECKING:
    pass  # torch imports deferred


def make_loaders(cfg: TrainingConfig):
    """Return (train_loader, val_loader, test_loader) DataLoaders.

    Applies:
    - RandomHorizontalFlip, ColorJitter, random rotation  (train only)
    - Normalisation with ImageNet mean/std
    - Fixed seeds for reproducible splits
    """
    try:
        import torch
        from torch.utils.data import DataLoader, random_split
        import torchvision.transforms as T
    except ImportError as e:
        raise ImportError(
            "PyTorch and torchvision are required for training. "
            "Install with: pip install torch torchvision"
        ) from e

    from sketchforge.models.component_detector.dataset import ComponentDetectorDataset

    seed_everything(cfg.seed)

    # --- transforms -----------------------------------------------------------
    img_size = cfg.image_size
    mean = [0.485, 0.456, 0.406]
    std  = [0.229, 0.224, 0.225]

    train_tf = T.Compose([
        T.Resize((img_size, img_size)),
        T.RandomHorizontalFlip(p=0.3),
        T.ColorJitter(brightness=0.3, contrast=0.3, saturation=0.2),
        T.RandomRotation(degrees=5),
        T.ToTensor(),
        T.Normalize(mean, std),
    ])

    eval_tf = T.Compose([
        T.Resize((img_size, img_size)),
        T.ToTensor(),
        T.Normalize(mean, std),
    ])

    # --- dataset --------------------------------------------------------------
    data_dir = Path(cfg.data_dir)
    full_ds = ComponentDetectorDataset(data_dir, transform=None)

    n = len(full_ds)
    if n == 0:
        raise RuntimeError(
            f"No samples found in {data_dir}. Run scripts/generate_synthetic_data.py first."
        )

    n_train = int(n * cfg.train_split)
    n_val   = int(n * cfg.val_split)
    n_test  = n - n_train - n_val

    generator = torch.Generator().manual_seed(cfg.seed)
    train_ds, val_ds, test_ds = random_split(
        full_ds, [n_train, n_val, n_test], generator=generator
    )

    # Inject transforms after split (avoid data leakage)
    train_ds.dataset.transform = train_tf  # type: ignore[attr-defined]
    val_ds.dataset.transform   = eval_tf   # type: ignore[attr-defined]
    test_ds.dataset.transform  = eval_tf   # type: ignore[attr-defined]

    def _loader(ds, shuffle: bool) -> DataLoader:
        return DataLoader(
            ds,
            batch_size=cfg.batch_size,
            shuffle=shuffle,
            num_workers=cfg.num_workers,
            pin_memory=cfg.pin_memory and cfg.resolve_device() == "cuda",
            drop_last=shuffle,
        )

    return _loader(train_ds, True), _loader(val_ds, False), _loader(test_ds, False)
