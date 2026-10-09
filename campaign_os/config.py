"""Wczytywanie plików konfiguracyjnych YAML."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT_DIR / "config"
SAMPLE_DIR = ROOT_DIR / "data" / "sample"

ALIASES_PATH = CONFIG_DIR / "column_aliases.yaml"
SETTINGS_PATH = CONFIG_DIR / "settings.yaml"
RULES_PATH = CONFIG_DIR / "rules.yaml"


def load_yaml(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path.name}: oczekiwano słownika na najwyższym poziomie")
    return data


def load_settings(path: Path = SETTINGS_PATH) -> dict[str, Any]:
    settings = load_yaml(path)
    settings.setdefault("currency", "PLN")
    settings.setdefault("default_range_days", 30)
    settings.setdefault("thresholds", {})
    return settings
