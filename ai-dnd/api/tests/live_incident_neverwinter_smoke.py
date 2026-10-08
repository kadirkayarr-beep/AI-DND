"""Optional live Neverwinter emergence smoke.

Missing qwen3:8b is BLOCKED, not FAIL. Daily unittests do not run this module.

    python -m api.tests.live_incident_neverwinter_smoke
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

AI_DND_DIR = Path(__file__).resolve().parents[2]
MODEL_NAME = "qwen3:8b"


def _blocked(reason):
    payload = {
        "final_gate_status": "BLOCKED",
        "live_generation": "unverified",
        "reason": reason,
        "model": MODEL_NAME,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def main():
    os.environ.setdefault("AI_DND_EMERGENCE_LIVE", "1")
    sys.path.insert(0, str(AI_DND_DIR))
    try:
        import game
        from incidents import profiles
    except Exception as error:
        return _blocked(f"import failed: {error}")

    loaded = profiles.load("neverwinter.v1")
    if loaded is None:
        return _blocked("Neverwinter profile did not load from the reviewed pack.")

    try:
        listing = game.ollama.list()
    except Exception as error:
        return _blocked(f"Ollama is unreachable: {error}")

    names = []
    models = listing.get("models") if isinstance(listing, dict) else None
    if isinstance(models, list):
        for row in models:
            name = row.get("name") or row.get("model") if isinstance(row, dict) else None
            if isinstance(name, str):
                names.append(name)
    if MODEL_NAME not in names and not any(item.startswith(MODEL_NAME) for item in names):
        return _blocked(f"{MODEL_NAME} is not installed.")

    payload = {
        "final_gate_status": "READY",
        "live_generation": "model_present",
        "profile_id": loaded["profile_id"],
        "review_status": loaded["review_status"],
        "model": MODEL_NAME,
        "note": "Profile is reviewed. A full turn smoke is a later Gate J job.",
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
