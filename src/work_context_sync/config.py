from __future__ import annotations

from pathlib import Path
import json

from .models.config import AppConfig


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path).expanduser().resolve()
    with config_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return AppConfig.model_validate(data)
