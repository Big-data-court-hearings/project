"""
Checkpoint utilities for incremental ingestion.

Stores and loads the latest checkpoint dates per resource
to `logs/checkpoint.json`.
"""
from pathlib import Path
import json
from typing import Optional, Dict, Any

from ingestion.config import PROJECT_ROOT


CHECKPOINT_PATH = PROJECT_ROOT / "logs" / "checkpoint.json"


def load_checkpoint(resource: str = "dockets") -> Optional[Dict[str, Any]]:
    """Load checkpoint for a given resource.

    Returns a dict with keys `date` and optional `last_id`, or None.
    Backwards-compatible with older string-only checkpoints.
    """

    try:
        if not CHECKPOINT_PATH.exists():
            return None

        with open(CHECKPOINT_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        value = data.get(resource)

        # Backwards compatibility: string -> treat as date
        if isinstance(value, str):
            return {"date": value}

        return value

    except Exception:
        return None


def save_checkpoint(resource: str, date_iso: str, last_id: Optional[str] = None) -> None:
    """Save checkpoint for a given resource.

    Stores an object with `date` and optional `last_id`.
    The file is created if missing. Existing keys are preserved.
    """

    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)

    data: Dict[str, Any] = {}

    if CHECKPOINT_PATH.exists():
        try:
            with open(CHECKPOINT_PATH, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            data = {}

    entry: Dict[str, Any] = {"date": date_iso}

    if last_id is not None:
        entry["last_id"] = last_id

    data[resource] = entry

    with open(CHECKPOINT_PATH, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
