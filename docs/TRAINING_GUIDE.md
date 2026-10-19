# Training guide

Training is not an active milestone. Before starting it, validate the dataset manifest and license decisions, inspect available hardware and storage, and run a bounded smoke test covering data loading, forward pass, finite loss, backpropagation, checkpoint reload, and inference.

Use fixed seeds, source-level train/validation/test splits, bounded batch sizes, validation metrics, early stopping, and checkpoint metadata. Compare held-out performance with the deterministic baseline before claiming an improvement. Training configuration defaults are in `../config/training.yaml`.
