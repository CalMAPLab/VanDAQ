"""Load YAML config with optional gitignored ``.local`` overlay."""

from __future__ import annotations

import os
from typing import Any

import yaml


def local_overlay_path(path: str) -> str:
    """``config.yaml`` -> ``config.local.yaml`` (same for ``.yml``)."""
    base, ext = os.path.splitext(path)
    if ext in (".yaml", ".yml"):
        return f"{base}.local{ext}"
    return f"{path}.local"


def deep_merge(base: Any, override: Any) -> Any:
    """Recursively merge *override* into a copy of *base*."""
    if not isinstance(base, dict) or not isinstance(override, dict):
        return override
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_yaml_config(path: str, loader=None, Loader=None) -> dict:
    """Load YAML from *path* and merge ``<stem>.local.<ext>`` when present."""
    yaml_loader = loader if loader is not None else (Loader if Loader is not None else yaml.FullLoader)
    with open(path, encoding="utf-8") as handle:
        config = yaml.load(handle, Loader=yaml_loader) or {}
    local_path = local_overlay_path(path)
    if os.path.isfile(local_path):
        with open(local_path, encoding="utf-8") as handle:
            local_config = yaml.load(handle, Loader=yaml_loader) or {}
        config = deep_merge(config, local_config)
    return config
