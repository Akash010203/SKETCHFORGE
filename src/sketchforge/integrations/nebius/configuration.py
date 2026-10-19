"""Nebius Token Factory configuration: file defaults, environment credentials, explicit consent."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from sketchforge.integrations.provider_interface import ProviderAuthError
from sketchforge.utilities.paths import repo_root


class PrivacyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allow_images: bool = False
    include_user_text: bool = False
    max_prompt_chars: int = Field(12_000, gt=0)
    max_components: int = Field(120, gt=0)


class NebiusConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    base_url: str = "https://api.tokenfactory.nebius.com/v1/"
    api_key_env: str = "NEBIUS_API_KEY"
    default_model: str = "nvidia/Nemotron-3_5-Lightning"
    candidate_models: list[str] = Field(default_factory=lambda: ["nvidia/Nemotron-3_5-Lightning"])
    timeout_s: float = Field(30.0, gt=0, le=300)
    max_retries: int = Field(2, ge=0, le=5)
    backoff_base_s: float = Field(0.8, ge=0)
    backoff_cap_s: float = Field(8.0, ge=0)
    privacy: PrivacyConfig = Field(default_factory=PrivacyConfig)

    def api_key(self, environ: dict[str, str] | None = None) -> str:
        """The key from the environment. Never read from any file in the repository."""
        key = (environ if environ is not None else os.environ).get(self.api_key_env, "").strip()
        if not key:
            raise ProviderAuthError(f"no API key: set the {self.api_key_env} environment variable")
        return key


def load_nebius_config(path: str | Path | None = None, overrides: dict[str, Any] | None = None) -> NebiusConfig:
    file = Path(path) if path else repo_root() / "config" / "providers.yaml"
    data: dict[str, Any] = {}
    if file.is_file():
        data = (yaml.safe_load(file.read_text(encoding="utf-8")) or {}).get("nebius", {}) or {}
    data = {**data, **(overrides or {})}
    return NebiusConfig.model_validate(data)
