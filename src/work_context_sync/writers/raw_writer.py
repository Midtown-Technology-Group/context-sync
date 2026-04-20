from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
import json


def _json_serialize(obj: object) -> str:
    """Custom JSON serializer that handles datetime objects."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")


def write_raw_outputs(config, target_date: date, result: dict) -> None:
    if not config.output.write_raw_json:
        return

    base = Path(config.vault_path) / "work-context" / "raw" / "graph"
    base.mkdir(parents=True, exist_ok=True)

    for source_name, payload in result.items():
        if payload is None:
            continue
        output = {
            "syncedAt": datetime.now(timezone.utc).isoformat(),
            "targetDate": target_date.isoformat(),
            "source": f"graph-{source_name}",
            "status": "error" if payload.get("error") else "ok",
            "error": payload.get("error"),
            "items": payload.get("value", payload),
        }
        path = base / f"{target_date.isoformat()}-{source_name}.json"
        path.write_text(
            json.dumps(output, indent=2, default=_json_serialize),
            encoding="utf-8"
        )
