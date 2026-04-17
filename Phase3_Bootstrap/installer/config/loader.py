"""YAML load/save for Phase3Config, with schema validation."""

from __future__ import annotations

from pathlib import Path

import yaml

from installer.config.schema import Phase3Config


def load_config(path: Path) -> Phase3Config:
    """Load and validate a config YAML file."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return Phase3Config.model_validate(raw)


def save_config(cfg: Phase3Config, path: Path) -> None:
    """Serialize config to YAML atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = cfg.model_dump(mode="json")
    tmp = path.with_suffix(".yaml.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(payload, fh, sort_keys=False, default_flow_style=False)
    tmp.replace(path)
