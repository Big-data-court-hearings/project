"""
Checkpoint utilities for incremental ingestion.

Stores and loads the latest checkpoint dates per resource
to `logs/checkpoint.json`.
"""
from pathlib import Path
import json
from typing import Optional

from ingestion.config import PROJECT_ROOT


CHECKPOINT_PATH = PROJECT_ROOT / "logs" / "checkpoint.json"


def load_checkpoint(resource: str = "dockets") -> Optional[str]:
    """Load checkpoint ISO string for a given resource.

    Returns the ISO 8601 date string (as stored) or None if no
    checkpoint exists.
    """

    try:
        if not CHECKPOINT_PATH.exists():
            return None

        with open(CHECKPOINT_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        return data.get(resource)

    except Exception:
        return None


def save_checkpoint(resource: str, date_iso: str) -> None:
    """Save checkpoint ISO string for a given resource.

    The file is created if missing. Existing keys are preserved.
    """

    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)

    data = {}

    if CHECKPOINT_PATH.exists():
        try:
            with open(CHECKPOINT_PATH, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            data = {}

    data[resource] = date_iso

    with open(CHECKPOINT_PATH, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
